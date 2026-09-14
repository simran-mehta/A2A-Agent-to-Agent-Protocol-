"""Trip Planner: an A2A *client* that discovers and talks to two remote
agents (Weather Agent, Budget Agent) and merges their answers into one
trip briefing.

This script deliberately contains almost no "business logic" of its own -
that is the point of A2A. The orchestrator does not need to know *how*
either remote agent works internally, only how to discover it (Agent
Card) and how to talk to it (JSON-RPC message/send). Swap either agent
for a completely different implementation, in a different language, on a
different machine, and this file would not need to change.

Run with: python host/trip_planner_client.py
(after both agents are running - see README.md)
"""

import asyncio

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_stream_response_text, new_text_message
from a2a.types import AgentCard, Role, SendMessageRequest

WEATHER_AGENT_URL = 'http://127.0.0.1:9001'
BUDGET_AGENT_URL = 'http://127.0.0.1:9002'


async def discover(base_url: str) -> AgentCard:
    """Fetch an Agent Card: the machine-readable "business card" every
    A2A agent publishes at /.well-known/agent-card.json, describing its
    name, skills, and where to send requests. This is the entire
    discovery step - no shared registry or hardcoded schema needed."""
    async with httpx.AsyncClient() as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        card = await resolver.get_agent_card()
    print(f"  discovered '{card.name}' -> {card.description}")
    return card


async def ask(card: AgentCard, text: str) -> str:
    """Send one message to a remote agent via the JSON-RPC message/send
    method and collect the resulting text back out of the task's
    artifacts. From here, this is a black box: we never see or need the
    other agent's source code."""
    client = await create_client(agent=card, client_config=ClientConfig(streaming=False))
    message = new_text_message(text, role=Role.ROLE_USER)
    request = SendMessageRequest(message=message)

    reply_parts = []
    async for chunk in client.send_message(request):
        piece = get_stream_response_text(chunk)
        if piece:
            reply_parts.append(piece)
    await client.close()
    return '\n'.join(reply_parts)


async def plan_trip(
    city: str, home_currency: str, dest_currency: str, budget: float
) -> None:
    print('Discovering agents...')
    weather_card, budget_card = await asyncio.gather(
        discover(WEATHER_AGENT_URL), discover(BUDGET_AGENT_URL)
    )

    print('\nDelegating to both agents in parallel...')
    weather_report, budget_report = await asyncio.gather(
        ask(weather_card, city),
        ask(budget_card, f'{budget} {home_currency} to {dest_currency}'),
    )

    print('\n' + '=' * 50)
    print(f'TRIP BRIEFING - {city.title()}')
    print('=' * 50)
    print(f'Weather : {weather_report}')
    print(f'Budget  : {budget_report}')
    print('=' * 50)


def main() -> None:
    print('Trip Planner (host agent) - talks to the Weather and Budget agents over A2A.\n')
    city = input('Destination city [Paris]: ').strip() or 'Paris'
    home_currency = (input('Your home currency [USD]: ').strip() or 'USD').upper()
    dest_currency = (input('Destination currency [EUR]: ').strip() or 'EUR').upper()
    budget_raw = input('Trip budget in your home currency [500]: ').strip() or '500'
    budget = float(budget_raw)

    asyncio.run(plan_trip(city, home_currency, dest_currency, budget))


if __name__ == '__main__':
    main()
