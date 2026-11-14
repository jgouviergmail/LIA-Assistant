"""A passive, location-free projection of weather LIA already obtained, for the companion.

Two sources, never a fetch: the dashboard card's cached weather, and the newest
observation any other read of the person's place left (``connectors.companion_weather``:
the heartbeat, the proactive discussions, the weather routines, the chat's own-place
weather). The companion shows the newer of the two while it is still the present
(ADR-294, follow-up of 2026-11-13).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

from src.core.constants import PRESENT_WEATHER_FRESH_SECONDS
from src.domains.briefing.constants import SECTION_WEATHER
from src.domains.briefing.schemas import CardSection, CardStatus, WeatherData
from src.domains.connectors.clients.weather_normalization import canonical_weather_main
from src.domains.connectors.companion_weather import (
    CompanionObservation,
    is_present,
    read_companion_observation,
)

if TYPE_CHECKING:
    from src.domains.briefing.service import BriefingService


class CompanionWeather(CompanionObservation):
    """What the companion is shown: an observation, and when it stops being the present.

    It extends the observation rather than restating it, so the bounds a read is
    held to and the bounds the endpoint answers with are one declaration.
    """

    expires_at: datetime = Field(description="When it stops being the present (UTC).")


class CompanionEnvironment(BaseModel):
    timezone: str
    weather: CompanionWeather | None = None


def project_weather(section: CardSection | None, now: datetime) -> CompanionWeather | None:
    """Never turn stale fallback data or a forecast into present conditions."""
    if section is None or section.status != CardStatus.OK:
        return None
    if not isinstance(section.data, WeatherData) or section.generated_at.tzinfo is None:
        return None
    if not is_present(section.generated_at, now):
        return None
    data = section.data
    try:
        return CompanionWeather(
            temperature_c=data.temperature_c,
            condition_code=canonical_weather_main(data.condition_code),
            wind_speed_kmh=data.wind_speed_kmh,
            observed_at=section.generated_at,
            expires_at=section.generated_at + timedelta(seconds=PRESENT_WEATHER_FRESH_SECONDS),
        )
    except ValidationError:
        return None


def project_observation(
    observation: CompanionObservation | None, now: datetime
) -> CompanionWeather | None:
    """Another read's observation, while it is still the present."""
    if observation is None or not is_present(observation.observed_at, now):
        return None
    return CompanionWeather(
        **observation.model_dump(),
        expires_at=observation.observed_at + timedelta(seconds=PRESENT_WEATHER_FRESH_SECONDS),
    )


async def read_present_weather(service: BriefingService, now: datetime) -> CompanionWeather | None:
    """The newest present weather LIA read at the person's place, or ``None``.

    A hidden weather card hides the weather from the companion whoever read it:
    nothing is even read then.

    Args:
        service: The person's briefing service (their cache and preferences).
        now: The instant of the request.

    Returns:
        The newer of the card's weather and any other read's observation, while
        it is still the present.
    """
    if SECTION_WEATHER in service.hidden_sections:
        return None
    card, observation = await asyncio.gather(
        service.read_cached_weather(), read_companion_observation(service.user.id)
    )
    present = [
        weather
        for weather in (project_weather(card, now), project_observation(observation, now))
        if weather is not None
    ]
    return max(present, key=lambda weather: weather.observed_at, default=None)
