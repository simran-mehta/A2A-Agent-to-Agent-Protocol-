"""Business logic + AgentExecutor for the Budget Agent.

Same shape as the Weather Agent's executor on purpose: once you learn the
AgentExecutor / TaskUpdater / Artifact pattern once, every A2A agent you
write (or read) follows the same skeleton, regardless of what it actually
does.
"""

import re

import httpx

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

QUERY_PATTERN = re.compile(
    r'^\s*([\d,.]+)\s*([A-Za-z]{3})\s*(?:to|->|in)\s*([A-Za-z]{3})\s*$'
)


class BudgetAgent:
    """Converts a travel budget between currencies via the free Frankfurter API (no key required)."""

    async def invoke(self, query: str) -> str:
        match = QUERY_PATTERN.match(query)
        if not match:
            return "Ask me like this: '500 USD to EUR'."

        amount_str, base, target = match.groups()
        amount = float(amount_str.replace(',', ''))
        base, target = base.upper(), target.upper()

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    'https://api.frankfurter.dev/v1/latest',
                    params={'base': base, 'symbols': target},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            # Calling an external API is a boundary: it can time out or fail
            # for reasons that have nothing to do with our logic, so we turn
            # that into a normal (non-crashing) agent reply instead of an
            # unhandled exception.
            return f'The currency lookup failed ({exc.__class__.__name__}). Please try again.'

        rate = (data.get('rates') or {}).get(target)
        if rate is None:
            return f"Sorry, I don't have an exchange rate for {base} -> {target}."

        converted = amount * rate
        return (
            f'{amount:,.2f} {base} ~ {converted:,.2f} {target} '
            f'(rate: 1 {base} = {rate} {target})'
        )


class BudgetAgentExecutor(AgentExecutor):
    """Wires BudgetAgent into the A2A Task lifecycle."""

    def __init__(self) -> None:
        self.agent = BudgetAgent()

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        task_updater = TaskUpdater(
            event_queue=event_queue, task_id=task.id, context_id=task.context_id
        )
        await task_updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message('Fetching exchange rates...'),
        )

        query = get_message_text(context.message) or ''
        result = await self.agent.invoke(query)

        await task_updater.add_artifact(
            parts=[new_text_part(text=result, media_type='text/plain')]
        )
        await task_updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message('Currency conversion complete.'),
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise NotImplementedError('Cancel is not supported by the Budget Agent.')
