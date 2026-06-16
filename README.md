# A2A — Agent-to-Agent Protocol Examples

Ejemplos de comunicación cliente-servidor usando el protocolo [A2A](https://a2a-protocol.org), basados en las muestras oficiales de [microsoft/agent-framework](https://github.com/microsoft/agent-framework).

## Estructura

```
a2a/
├── demo/                    # Demo standalone — sin credenciales, sin LLM
│   ├── server.py            # CalculatorAgent: servidor A2A con executor propio
│   ├── client.py            # Cliente A2A — 3 patrones: sync, stream, polling
│   └── requirements.txt
│
├── 02-agents_a2a/           # Clientes A2A de microsoft/agent-framework
│   ├── agent_with_a2a.py    # Non-streaming + streaming
│   ├── a2a_polling.py       # Background + polling
│   ├── a2a_stream_reconnection.py  # Reconexión a stream interrumpido
│   └── a2a_agent_as_function_tools.py  # Skills del agente como tools de LLM
│
├── 04-hosting_a2a/          # Servidor A2A de microsoft/agent-framework (requiere Azure)
│   ├── a2a_server.py        # Servidor con agentes invoice/policy/logistics
│   ├── agent_definitions.py # Definiciones de AgentCard y agentes
│   ├── invoice_data.py      # Datos mock de facturas
│   └── requirements.txt
│
├── a2a-explainer.html       # Guía visual completa del protocolo A2A
├── .env.example             # Variables de entorno — copia a .env y rellena
└── .gitignore
```

## Inicio rápido — demo (sin credenciales)

```bash
# 1. Instalar dependencias
pip install -r demo/requirements.txt

# 2. Terminal 1 — servidor
python demo/server.py

# 3. Terminal 2 — cliente (demuestra los 3 patrones A2A)
python demo/client.py
```

El demo corre un `CalculatorAgent` que evalúa expresiones aritméticas.
Demuestra los tres patrones de comunicación A2A sin necesitar Azure ni API keys.

## Los 3 patrones A2A

| Patrón | Cuándo usarlo | Código |
|--------|--------------|--------|
| **Non-streaming** | Respuestas cortas, espera el resultado completo | `await agent.run("42 + 58")` |
| **Streaming (SSE)** | Ver el resultado en tiempo real, token a token | `agent.run("...", stream=True)` |
| **Background + polling** | Tareas largas, el cliente puede desconectarse | `agent.run("...", background=True)` |

## Ejemplos de Azure (04-hosting_a2a/)

Requieren cuenta Azure con AI Foundry y `az login`:

```bash
# Copiar y rellenar variables de entorno
cp .env.example .env
# Editar FOUNDRY_PROJECT_ENDPOINT y FOUNDRY_MODEL en .env

# Servidor de facturas (puerto 5000)
cd 04-hosting_a2a
pip install -r requirements.txt
python a2a_server.py --agent-type invoice --port 5000

# Cliente (en otra terminal, con A2A_AGENT_HOST=http://localhost:5000/)
cd 02-agents_a2a
python agent_with_a2a.py
```

Tipos de agente disponibles: `invoice` (5000), `policy` (5001), `logistics` (5002).

## Documentación visual

Abre `a2a-explainer.html` en el navegador para una guía completa con:
- Qué es A2A y por qué existe
- Arquitectura y flujo de una tarea
- Los 3 patrones con diagramas
- Cómo leer el código del demo
- Glosario de 15 términos clave

## Variables de entorno

Copia `.env.example` a `.env` (ignorado por git) y rellena tus valores.
`python-dotenv` lo encuentra automáticamente desde cualquier subcarpeta.

## Créditos

Muestras `02-agents/a2a` y `04-hosting/a2a` © Microsoft Corporation — [apache-2.0](https://github.com/microsoft/agent-framework/blob/main/LICENSE).
