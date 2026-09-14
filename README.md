# A2A (Agent2Agent) Protocol — Trip Planner Sample

A working, runnable example of the [Agent2Agent (A2A) protocol](https://a2a-protocol.org/) —
the open, vendor-neutral standard (donated by Google to the Linux Foundation in 2025,
now at v1.0.1) that lets independent AI agents discover each other, delegate tasks, and
exchange results over JSON-RPC 2.0, regardless of what framework or language each agent
is built with.

For a concept-by-concept explanation of *why* the code below is shaped the way it is,
see **[docs/CONCEPTS.md](docs/CONCEPTS.md)**.

## The use case

A **Trip Planner** that needs to answer "what's the weather in \<city\> and what's my
budget worth there?" — without knowing anything about weather APIs or exchange rates
itself. It delegates both jobs to two independent A2A agents running as separate
processes:

```
                        ┌─────────────────────┐
              ┌────────▶│   Weather Agent      │  :9001
              │         │  (skill: get_weather) │
┌─────────────┴───┐     └─────────────────────┘
│  Trip Planner    │
│  (A2A client /   │
│   orchestrator)  │     ┌─────────────────────┐
└─────────────┬───┘     │   Budget Agent        │  :9002
              └────────▶│  (skill: convert_budget)│
                        └─────────────────────┘
```

Each remote agent is a real A2A **server**: it publishes an Agent Card, accepts
`message/send` JSON-RPC calls, and runs the request through the standard A2A Task
lifecycle. The Trip Planner is a real A2A **client**: it discovers each agent's Agent
Card at runtime and calls both **in parallel** — it never imports their code.

- **Weather Agent** — calls the free [Open-Meteo](https://open-meteo.com/) API (no key
  needed) to report current conditions for a city.
- **Budget Agent** — calls the free [Frankfurter](https://frankfurter.dev/) exchange-rate
  API (no key needed) to convert a budget between currencies.

No LLM or API key is required to run this — the point of the sample is the protocol
mechanics, not the "intelligence" inside each agent. (In a real system, either agent's
`invoke()` could just as easily call an LLM instead of a plain REST API — A2A doesn't
care what's inside the box.)

## Project layout

```
agents/
  weather_agent/
    __main__.py          # A2A server: Agent Card + skill + wiring
    agent_executor.py     # Business logic (Open-Meteo) + AgentExecutor
  budget_agent/
    __main__.py          # A2A server: Agent Card + skill + wiring
    agent_executor.py     # Business logic (Frankfurter) + AgentExecutor
host/
  trip_planner_client.py  # A2A client: discovery + parallel delegation
docs/
  CONCEPTS.md              # Deep dive on every A2A concept used here
requirements.txt
```

## Running it

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Open **three terminals** (all from the repo root, with the venv activated):

```bash
# Terminal 1
python -m agents.weather_agent

# Terminal 2
python -m agents.budget_agent

# Terminal 3
python host/trip_planner_client.py
```

Terminal 3 will prompt you for a destination, currencies, and budget, then print a
combined trip briefing pulled from both agents. Try it, then try killing one of the
agents and re-running the client to see how a delegated call fails when its target is
unreachable.

You can also inspect either agent's identity directly in a browser or with curl, which
is exactly what the client does under the hood:

```bash
curl http://127.0.0.1:9001/.well-known/agent-card.json
curl http://127.0.0.1:9002/.well-known/agent-card.json
```

## Where to go next

- Read [docs/CONCEPTS.md](docs/CONCEPTS.md) for what an Agent Card, a Task, a Message,
  and an Artifact actually are, and why the SDK's `AgentExecutor` / `TaskUpdater`
  classes exist.
- Try adding a third agent (e.g. a "packing list" agent) and wiring it into
  `trip_planner_client.py` — that's the whole exercise of "agent-to-agent" composition.
- Try turning on streaming (`ClientConfig(streaming=True)`) and watch the
  `TASK_STATE_WORKING` status update arrive before the final result.
