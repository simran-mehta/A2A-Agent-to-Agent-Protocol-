"""Business logic + AgentExecutor for the Weather Agent.

AgentExecutor is the bridge between the generic A2A server (request
parsing, task bookkeeping, event streaming) and this agent's actual
skill logic. The SDK calls `execute()` for every incoming task; only
`WeatherAgent.invoke()` is specific to what this agent does.
"""

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

WEATHER_CODES = {
    0: 'clear sky',
    1: 'mainly clear',
    2: 'partly cloudy',
    3: 'overcast',
    45: 'fog',
    48: 'depositing rime fog',
    51: 'light drizzle',
    53: 'moderate drizzle',
    55: 'dense drizzle',
    61: 'slight rain',
    63: 'moderate rain',
    65: 'heavy rain',
    71: 'slight snow',
    73: 'moderate snow',
    75: 'heavy snow',
    80: 'rain showers',
    81: 'moderate rain showers',
    82: 'violent rain showers',
    95: 'thunderstorm',
}


class WeatherAgent:
    """Looks up current weather for a city via the free Open-Meteo API (no key required)."""

    async def invoke(self, city: str) -> str:
        city = city.strip()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                geo = await client.get(
                    'https://geocoding-api.open-meteo.com/v1/search',
                    params={'name': city, 'count': 1},
                )
                geo.raise_for_status()
                results = geo.json().get('results') or []
                if not results:
                    return f"I couldn't find a location named '{city}'."

                place = results[0]
                lat, lon = place['latitude'], place['longitude']
                label = f"{place['name']}, {place.get('country', '')}".strip(', ')

                forecast = await client.get(
                    'https://api.open-meteo.com/v1/forecast',
                    params={
                        'latitude': lat,
                        'longitude': lon,
                        'current': 'temperature_2m,weather_code',
                        'timezone': 'auto',
                    },
                )
                forecast.raise_for_status()
                current = forecast.json().get('current', {})
        except httpx.HTTPError as exc:
            # Calling an external API is a boundary: it can time out or fail
            # for reasons that have nothing to do with our logic, so we turn
            # that into a normal (non-crashing) agent reply instead of an
            # unhandled exception.
            return f'The weather lookup failed ({exc.__class__.__name__}). Please try again.'

        temp = current.get('temperature_2m')
        condition = WEATHER_CODES.get(
            current.get('weather_code'), 'unknown conditions'
        )
        return f'{label}: {temp}°C, {condition}.'


class WeatherAgentExecutor(AgentExecutor):
    """Wires WeatherAgent into the A2A Task lifecycle."""

    def __init__(self) -> None:
        self.agent = WeatherAgent()

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        # A Task is the unit of work the A2A server tracks for this request.
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        task_updater = TaskUpdater(
            event_queue=event_queue, task_id=task.id, context_id=task.context_id
        )
        # Moving to "working" lets a streaming client show live progress
        # instead of a silent wait until the final result.
        await task_updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message('Checking the forecast...'),
        )

        city = get_message_text(context.message) or ''
        if city:
            result = await self.agent.invoke(city)
        else:
            result = 'Please tell me which city you want the weather for.'

        # The Artifact is the actual output payload, distinct from the
        # human-readable status messages sent along the way.
        await task_updater.add_artifact(
            parts=[new_text_part(text=result, media_type='text/plain')]
        )
        await task_updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message('Weather lookup complete.'),
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        raise NotImplementedError('Cancel is not supported by the Weather Agent.')
