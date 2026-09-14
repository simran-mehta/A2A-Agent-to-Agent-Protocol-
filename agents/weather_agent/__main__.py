"""A2A server exposing the Weather Agent.

Run with: python -m agents.weather_agent   (from the repo root)
Agent Card served at: http://127.0.0.1:9001/.well-known/agent-card.json
"""

import uvicorn
from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from agents.weather_agent.agent_executor import WeatherAgentExecutor

HOST = '127.0.0.1'
PORT = 9001

if __name__ == '__main__':
    # An AgentSkill advertises one thing this agent can do. Clients (or the
    # humans/LLMs driving them) read these to decide which agent to call.
    skill = AgentSkill(
        id='get_weather',
        name='Get Current Weather',
        description='Reports the current temperature and conditions for a named city.',
        input_modes=['text/plain'],
        output_modes=['text/plain'],
        tags=['weather', 'travel'],
        examples=['Paris', 'Tokyo', 'New York'],
    )

    # The Agent Card is this agent's public, machine-readable identity:
    # who it is, what it can do, and where to send requests. It is served
    # at the well-known path so any A2A client can discover it by URL alone.
    agent_card = AgentCard(
        name='Weather Agent',
        description='Tells you the current weather for any city, worldwide.',
        version='0.1.0',
        default_input_modes=['text/plain'],
        default_output_modes=['text/plain'],
        capabilities=AgentCapabilities(streaming=True),
        supported_interfaces=[
            AgentInterface(
                protocol_binding='JSONRPC',
                url=f'http://{HOST}:{PORT}',
                protocol_version='1.0',
            )
        ],
        skills=[skill],
    )

    # The RequestHandler is the SDK's protocol engine: it turns incoming
    # JSON-RPC calls into Task objects and drives our AgentExecutor.
    request_handler = DefaultRequestHandler(
        agent_executor=WeatherAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    routes = []
    routes.extend(create_agent_card_routes(agent_card))
    routes.extend(create_jsonrpc_routes(request_handler, '/'))

    app = Starlette(routes=routes)

    print(f'Weather Agent listening on http://{HOST}:{PORT}')
    print(f'Agent Card: http://{HOST}:{PORT}/.well-known/agent-card.json')
    uvicorn.run(app, host=HOST, port=PORT)
