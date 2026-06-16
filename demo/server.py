# Copyright (c) Microsoft. All rights reserved.

import asyncio
import ast
import operator
import re
import uuid

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Artifact,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from starlette.applications import Starlette

"""
A2A Calculator Agent Server

Hosts a rule-based agent that evaluates arithmetic expressions.
No LLM or Azure credentials required — runs standalone.

Supports: +  -  *  /  **  %  ( )  and integer/float literals.

Usage:
    python server.py [--host localhost] [--port 5001]

The agent card is served at:
    GET http://localhost:5001/.well-known/agent.json
"""

HOST = "localhost"
PORT = 5001
URL = f"http://{HOST}:{PORT}/"

# ---------------------------------------------------------------------------
# Safe arithmetic evaluator (no eval(), AST-only)
# ---------------------------------------------------------------------------

_SAFE_OPS: dict = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.expr) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))
    raise ValueError(f"Unsupported node: {type(node).__name__}")


def safe_eval(expression: str) -> float:
    tree = ast.parse(expression.strip(), mode="eval")
    return _eval_node(tree.body)


def extract_expression(text: str) -> str:
    """Pull a math expression from free-form text.

    Strips common English lead-ins ("what is", "calculate:", etc.) then
    finds the first token sequence that begins with a digit or parenthesis.
    """
    cleaned = re.sub(
        r"^(?:what\s+is\s*|calculate[:\s]*|compute[:\s]*|eval[:\s]*)",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    ).strip().rstrip("?").strip()

    match = re.search(r"[\d(][\d\s\+\-\*\/\%\.\(\)]*", cleaned)
    if match:
        candidate = match.group(0).strip()
        if candidate:
            return candidate
    return cleaned


# ---------------------------------------------------------------------------
# Agent executor
# ---------------------------------------------------------------------------

class CalculatorExecutor(AgentExecutor):
    """
    Custom AgentExecutor — no LLM, pure Python arithmetic.

    Workflow:
      1. Enqueue a Task (WORKING) so the framework starts a task object.
      2. Stream the result character-by-character via TaskArtifactUpdateEvent.
      3. Enqueue TaskStatusUpdateEvent (COMPLETED) to close the task.
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())
        user_text = context.get_user_input()

        # 1. Signal task start
        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            )
        )

        # 2. Evaluate expression
        try:
            expression = extract_expression(user_text)
            result = safe_eval(expression)
            # Format: drop trailing .0 for clean integers
            if result == int(result):
                result_str = f"{expression} = {int(result)}"
            else:
                result_str = f"{expression} = {result:.6g}"
        except Exception as exc:
            result_str = f"Error: {exc}"

        # 3. Stream result character-by-character (demonstrates SSE / streaming)
        artifact_id = str(uuid.uuid4())
        for i, char in enumerate(result_str):
            is_last = i == len(result_str) - 1
            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    task_id=task_id,
                    context_id=context_id,
                    artifact=Artifact(
                        artifact_id=artifact_id,
                        parts=[Part(text=char)],
                    ),
                    append=(i > 0),
                    last_chunk=is_last,
                )
            )
            await asyncio.sleep(0.04)  # simulate incremental output

        # 4. Mark task complete
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_CANCELED),
            )
        )


# ---------------------------------------------------------------------------
# AgentCard
# ---------------------------------------------------------------------------

AGENT_CARD = AgentCard(
    name="CalculatorAgent",
    description="Evaluates arithmetic expressions: +  -  *  /  **  %  ( )",
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=True, push_notifications=False),
    supported_interfaces=[AgentInterface(url=URL, protocol_binding="JSONRPC")],
    skills=[
        AgentSkill(
            id="calculate",
            name="Calculate",
            description="Evaluate an arithmetic expression and return the result.",
            tags=["math", "calculator"],
            examples=["42 + 58", "What is 3.14 * 2?", "Calculate: (100 - 37) * 4"],
        )
    ],
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    executor = CalculatorExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        agent_card=AGENT_CARD,
    )

    app = Starlette(
        routes=[
            *create_agent_card_routes(AGENT_CARD),
            *create_jsonrpc_routes(request_handler, "/"),
        ]
    )

    print(f"CalculatorAgent — A2A server")
    print(f"  Listening : {URL}")
    print(f"  Agent card: {URL}.well-known/agent.json")
    print()

    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
