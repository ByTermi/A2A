# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent
from dotenv import load_dotenv

load_dotenv()

"""
A2A Calculator Client

Demonstrates three communication patterns from the A2A protocol:
  1. Non-streaming  — send a request, await the complete response.
  2. Streaming      — receive incremental updates via SSE as the agent works.
  3. Background     — fire-and-forget with continuation token, then poll.

Prerequisites:
  Start the server first:
      python server.py

Then run this client:
      python client.py

Or point at a different host via env var:
      A2A_AGENT_HOST=http://localhost:5001/ python client.py
"""

SERVER_URL = os.getenv("A2A_AGENT_HOST", "http://localhost:5001/")


async def main() -> None:
    print(f"Connecting to A2A agent at: {SERVER_URL}")

    # -----------------------------------------------------------------------
    # 0. Discover the agent — resolve its AgentCard
    # -----------------------------------------------------------------------
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=SERVER_URL)
        agent_card = await resolver.get_agent_card()

    print(f"Found agent : {agent_card.name}")
    print(f"Description : {agent_card.description}")
    print(f"Skills      : {[s.name for s in agent_card.skills]}")
    print()

    async with A2AAgent(
        name=agent_card.name,
        description=agent_card.description,
        agent_card=agent_card,
        url=SERVER_URL,
    ) as agent:

        # -------------------------------------------------------------------
        # 1. Non-streaming — agent.run() blocks until the task is done.
        #    Even though the server uses a Task workflow internally, A2AAgent
        #    waits for completion transparently (background=False by default).
        # -------------------------------------------------------------------
        print("=" * 50)
        print("Pattern 1: Non-streaming")
        print("=" * 50)

        queries = [
            "42 + 58",
            "What is 3.14 * 2?",
            "Calculate: (100 - 37) * 4",
            "1024 / 32",
        ]

        for query in queries:
            response = await agent.run(query)
            print(f"  Q: {query}")
            print(f"  A: {response.text}")
        print()

        # -------------------------------------------------------------------
        # 2. Streaming — receive tokens as they arrive via Server-Sent Events.
        #    Same as agent_with_a2a.py but the response contains arithmetic.
        # -------------------------------------------------------------------
        print("=" * 50)
        print("Pattern 2: Streaming (SSE)")
        print("=" * 50)

        expression = "999 * 999"
        print(f"  Q: {expression}")
        print("  A: ", end="", flush=True)

        stream = agent.run(expression, stream=True)
        async for update in stream:
            for content in update.contents:
                if content.text:
                    print(content.text, end="", flush=True)
        print()  # newline after stream

        final = await stream.get_final_response()
        print(f"  Final: {final.text}")
        print()

        # -------------------------------------------------------------------
        # 3. Background + polling — mirrors a2a_polling.py.
        #    background=True returns immediately with a continuation token
        #    if the task is still running; we poll until completion.
        # -------------------------------------------------------------------
        print("=" * 50)
        print("Pattern 3: Background + polling")
        print("=" * 50)

        expression = "2 ** 32"
        print(f"  Q: {expression} (started as background task)")

        response = await agent.run(expression, background=True)

        if response.continuation_token is None:
            print(f"  Completed immediately: {response.text}")
        else:
            token = response.continuation_token
            poll_count = 0
            while token is not None:
                poll_count += 1
                print(f"  Poll #{poll_count} — task in progress...")
                await asyncio.sleep(0.5)
                response = await agent.poll_task(token)
                token = response.continuation_token

            print(f"  Completed after {poll_count} poll(s): {response.text}")
        print()


if __name__ == "__main__":
    asyncio.run(main())


"""
Expected output:

Connecting to A2A agent at: http://localhost:5001/
Found agent : CalculatorAgent
Description : Evaluates arithmetic expressions: +  -  *  /  **  %  ( )
Skills      : ['Calculate']

==================================================
Pattern 1: Non-streaming
==================================================
  Q: 42 + 58
  A: 42 + 58 = 100
  Q: What is 3.14 * 2?
  A: 3.14 * 2 = 6.28
  Q: Calculate: (100 - 37) * 4
  A: (100 - 37) * 4 = 252
  Q: 1024 / 32
  A: 1024 / 32 = 32

==================================================
Pattern 2: Streaming (SSE)
==================================================
  Q: 999 * 999
  A: 999 * 999 = 998001
  Final: 999 * 999 = 998001

==================================================
Pattern 3: Background + polling
==================================================
  Q: 2 ** 32 (started as background task)
  Poll #1 — task in progress...
  Completed after 1 poll(s): 2 ** 32 = 4294967296
"""
