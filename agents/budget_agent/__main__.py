"""A2A server exposing the Budget Agent.

Run with: python -m agents.budget_agent   (from the repo root)
Agent Card served at: http://127.0.0.1:9002/.well-known/agent-card.json
"""

import uvicorn
from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from agents.budget_agent.agent_executor import BudgetAgentExecutor

HOST = '127.0.0.1'
PORT = 9002

if __name__ == '__main__':
    skill = AgentSkill(
        id='convert_budget',
        name='Convert Travel Budget',
        description=(
            "Converts an amount from one currency to another. "
            "Ask like: '500 USD to EUR'."
        ),
        input_modes=['text/plain'],
        output_modes=['text/plain'],
        tags=['currency', 'budget', 'travel'],
        examples=['500 USD to EUR', '1000 INR to JPY'],
    )

    agent_card = AgentCard(
        name='Budget Agent',
        description='Converts travel budgets between currencies using live exchange rates.',
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

    request_handler = DefaultRequestHandler(
        agent_executor=BudgetAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    routes = []
    routes.extend(create_agent_card_routes(agent_card))
    routes.extend(create_jsonrpc_routes(request_handler, '/'))

    app = Starlette(routes=routes)

    print(f'Budget Agent listening on http://{HOST}:{PORT}')
    print(f'Agent Card: http://{HOST}:{PORT}/.well-known/agent-card.json')
    uvicorn.run(app, host=HOST, port=PORT)
