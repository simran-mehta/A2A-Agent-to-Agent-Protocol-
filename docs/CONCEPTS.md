# A2A Protocol Concepts, Explained Through This Sample

This walks through every core A2A concept, pointing at the exact code in this repo
that demonstrates it. Read it alongside the files it references.

---

## 1. What A2A is, and what it isn't

**A2A (Agent2Agent)** is an open protocol for **agent-to-agent** communication:
one autonomous agent discovering, calling, and delegating work to a *different*,
independently-built agent — possibly written in another language, run by another
team, on another machine — without either side seeing the other's source code.

It's easy to confuse with **MCP (Model Context Protocol)**, which solves a related but
different problem:

| | Connects... | Example |
|---|---|---|
| **MCP** | an LLM/agent to *tools and data sources* | an agent calling a "read file" or "query database" tool |
| **A2A** | an agent to *another agent* | your Trip Planner delegating to a separately-run Weather Agent |

In this sample, the Trip Planner doesn't call a "weather function" — it calls a whole
other agent, which happens to expose exactly one skill. That agent could later gain
five more skills, switch its internal implementation from a REST call to an LLM, or
move to a different server, and the Trip Planner's code would not change at all. That
decoupling is the entire point of A2A.

Transport-wise, A2A runs JSON-RPC 2.0 over HTTP(S), with Server-Sent Events (SSE) for
streaming responses and optional webhook push notifications for long-running async
tasks.

---

## 2. The Agent Card: how an agent introduces itself

Before you can talk to an agent, you need to know what it can do and where to send
requests. A2A solves this with the **Agent Card** — a JSON document every A2A server
publishes at the well-known path `/.well-known/agent-card.json`.

See it built in [`agents/weather_agent/__main__.py`](../agents/weather_agent/__main__.py):

```python
agent_card = AgentCard(
    name='Weather Agent',
    description='Tells you the current weather for any city, worldwide.',
    version='0.1.0',
    capabilities=AgentCapabilities(streaming=True),
    supported_interfaces=[
        AgentInterface(protocol_binding='JSONRPC', url=f'http://{HOST}:{PORT}', protocol_version='1.0')
    ],
    skills=[skill],
)
```

And fetched from the client side in
[`host/trip_planner_client.py`](../host/trip_planner_client.py)'s `discover()`:

```python
resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
card = await resolver.get_agent_card()
```

Try it yourself while an agent is running:

```bash
curl http://127.0.0.1:9001/.well-known/agent-card.json
```

This is **discovery**: no shared registry, no hardcoded interface definitions on the
client. Point an A2A client at any base URL and it learns everything it needs — name,
description, supported transport(s), and skills — from that one document. (v1.0 of the
spec added optional cryptographic signing of Agent Cards via JWS, so a client can also
*verify* who published a card, not just read it.)

---

## 3. Agent Skills and Capabilities

Inside the Agent Card, an **AgentSkill** describes one distinct thing the agent can do —
its id, a human-readable name/description, example inputs, and which media types
(`text/plain`, etc.) it accepts and returns. Ours are trivially single-skill agents:

- `agents/weather_agent/__main__.py` → skill `get_weather`
- `agents/budget_agent/__main__.py` → skill `convert_budget`

A real agent often exposes several skills in one card. **AgentCapabilities** is
separate — it flags protocol-level features the *agent itself* supports, like
`streaming=True` (can it emit incremental status/results over SSE?) or extended-card
support for authenticated clients.

---

## 4. Messages and Parts

A **Message** is one turn in a conversation between a client and an agent. It has a
`role` (`user` or `agent`) and a list of **Parts** — a Part being one piece of content:
text, structured data, or a file/URL reference. Ours only ever use a single
`text/plain` Part, built with the SDK helper `new_text_part` /
`new_text_message` (see either `agent_executor.py`).

Because every Part is typed, the same Message envelope can carry plain chat text, a
JSON payload, or a file reference — an agent that returns a PDF report and one that
returns a one-line string use the exact same protocol machinery.

---

## 5. Tasks and the Task lifecycle

A **Task** is the unit of work the A2A server tracks for a request — it has a unique
id and moves through a defined lifecycle:

```
submitted → working → completed
                     → failed
                     → canceled
                     → rejected
              ↕
      input-required / auth-required   (pauses without ending the task)
```

You can watch this happen in either `agent_executor.py`:

```python
task = new_task_from_user_message(context.message)      # created (submitted)
...
await task_updater.update_status(state=TaskState.TASK_STATE_WORKING, ...)   # working
...
await task_updater.add_artifact(...)                     # the actual result
await task_updater.update_status(state=TaskState.TASK_STATE_COMPLETED, ...) # completed
```

Why bother with a stateful Task instead of a plain request/response? Because A2A is
built for work that can be *slow* — minutes or hours, not milliseconds. A client can
disconnect and later poll `tasks/get` for the same task id, or an agent mid-task can
flip to `input-required` to ask a clarifying question before continuing. None of that
is representable in a stateless HTTP call; it requires a durable Task with an id and a
state machine, which is exactly what this section is.

---

## 6. AgentExecutor: where your logic plugs into the protocol

`AgentExecutor` is the SDK's seam between generic protocol handling and your agent's
actual behavior. You implement two methods:

- `execute(context, event_queue)` — do the work, emit status/results
- `cancel(context, event_queue)` — handle a cancellation request

Look at `WeatherAgentExecutor.execute` in
[`agents/weather_agent/agent_executor.py`](../agents/weather_agent/agent_executor.py):
everything before the call to `self.agent.invoke(city)` is protocol bookkeeping (get or
create the Task, announce "working"); everything after is protocol bookkeeping again
(publish the Artifact, announce "completed"). The one line in the middle —
`WeatherAgent.invoke()` — is the only part that's actually *about weather*. This
separation is deliberate: swap `WeatherAgent` for an LLM-backed implementation and
`WeatherAgentExecutor` doesn't change.

The `EventQueue` is how `execute()` communicates back through the running Task: every
status update and artifact you emit is pushed onto it, and the SDK's request handler
drains it to build the JSON-RPC response (or SSE stream, if the client asked to
stream). `TaskUpdater` is a small convenience wrapper around `EventQueue` so you don't
hand-construct status/artifact events yourself.

---

## 7. Artifacts vs. status messages

Two different kinds of output flow out of a Task, and it's worth keeping them
separate:

- **Status messages** (`update_status(..., message=...)`) are human-readable progress
  narration — "Checking the forecast...", "Currency conversion complete." A UI can show
  these as a live progress indicator.
- **Artifacts** (`add_artifact(...)`) are the actual deliverable — the weather report,
  the converted amount. This is the payload a caller actually wants back.

In our agents you can see both: a `TASK_STATE_WORKING` status fires first as a "still
going" signal, then the artifact carries the real answer, then a `TASK_STATE_COMPLETED`
status closes out the task.

---

## 8. Sending a message: the client side

`host/trip_planner_client.py`'s `ask()` function is the client half of the protocol:

```python
client = await create_client(agent=card, client_config=ClientConfig(streaming=False))
message = new_text_message(text, role=Role.ROLE_USER)
request = SendMessageRequest(message=message)

async for chunk in client.send_message(request):
    piece = get_stream_response_text(chunk)
```

`SendMessageRequest` wraps a `Message` and is sent via the **`message/send`** JSON-RPC
method — suitable for a single request where you're happy to wait for (or poll for) the
final result. There's a sibling streaming method (`message/stream`, using SSE) for
watching intermediate status updates arrive live; our client code is written to work
unchanged with either (`ClientConfig(streaming=True)` is the only line you'd flip) —
`client.send_message()` always returns an async iterator, it just yields more
intermediate events when streaming is on.

---

## 9. Multi-agent orchestration: the actual point of this sample

`plan_trip()` in the host script is the payoff:

```python
weather_report, budget_report = await asyncio.gather(
    ask(weather_card, city),
    ask(budget_card, f'{budget} {home_currency} to {dest_currency}'),
)
```

This is what "agent-to-agent" *composition* looks like: a coordinating agent (or, here,
a plain client script standing in for one) fans out to multiple independent agents
concurrently and merges their answers. Nothing here is weather- or currency-specific —
the exact same pattern is how a production system might have one orchestrator agent
delegate to a dozen specialist agents owned by different teams, written in different
languages, deployed independently. The orchestrator only ever needs an Agent Card
(discovery) and JSON-RPC `message/send` (invocation); it never needs the other agent's
source.

A natural next step (not built here, but worth trying) is wrapping the Trip Planner
itself as an A2A **server** with its own Agent Card and skill — turning a two-hop
client→agent call into an arbitrarily deep chain of agents calling agents.

---

## 10. Error handling as a protocol concern

Look at the `try`/`except httpx.HTTPError` blocks added in both agents' `invoke()`
methods. This isn't incidental — it demonstrates a real failure mode you'll hit
immediately once agents call out to anything external: if `execute()` raises an
unhandled exception mid-task, the Task can be left in a state where the server never
cleanly emits a terminal status, and the *client* ends up hanging until its own HTTP
timeout instead of getting a fast, legible error. Catching expected failures at the
boundary (the external API call) and turning them into a normal artifact/text response
keeps the Task lifecycle well-formed no matter what the remote dependency does.

---

## 11. Security notes (not implemented here, worth knowing)

This sample runs everything unauthenticated on localhost to keep the focus on protocol
mechanics. A production Agent Card would also declare:

- **Authentication schemes** the agent requires (API key, OAuth2, mTLS, etc.), so a
  client knows how to authenticate before it ever calls a skill.
- **Signed Agent Cards** (v1.0+) — a JWS signature over the card (RFC 7515, with RFC
  8785 JSON canonicalization) so a client can cryptographically verify the card wasn't
  tampered with and really was published by the domain it claims.
- An **extended agent card** (see the official `helloworld` sample) visible only to
  authenticated callers, for skills you don't want publicly advertised.

---

## Quick reference: concept → file

| Concept | Where to look |
|---|---|
| Agent Card construction | `agents/*/__main__.py` |
| Agent Card discovery | `host/trip_planner_client.py` → `discover()` |
| AgentSkill / AgentCapabilities | `agents/*/__main__.py` |
| AgentExecutor pattern | `agents/*/agent_executor.py` → `execute()` / `cancel()` |
| Task lifecycle states | `agents/*/agent_executor.py` (`TaskState.*`) |
| TaskUpdater / EventQueue | `agents/*/agent_executor.py` |
| Messages & Parts | `new_text_message` / `new_text_part` calls throughout |
| Artifacts | `task_updater.add_artifact(...)` |
| message/send (client) | `host/trip_planner_client.py` → `ask()` |
| Multi-agent orchestration | `host/trip_planner_client.py` → `plan_trip()` |
| Boundary error handling | `try/except httpx.HTTPError` in both `agent_executor.py` files |
