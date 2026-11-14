"""The chat's own-place weather feeds the companion; a city someone names never does.

ADR-294 (follow-up of 2026-11-13): every read of the present conditions at the
person's place is offered to the companion through one door. The chat's weather
tool reads the person's place when it is asked without a place (``auto``, resolved
from their position, last known place or home) — and anyone's weather when a city
is named, which is not the person's present and must never dress their companion.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.weather_tools import _get_current_weather_tool_impl

pytestmark = pytest.mark.unit

MODULE = "src.domains.agents.tools.weather_tools"
CURRENT: dict[str, Any] = {
    "dt": 1_763_035_200,
    "main": {"temp": 6.0, "humidity": 70},
    "weather": [{"main": "Clouds", "description": "nuageux"}],
    "wind": {"speed": 3.0},
    "sys": {"country": "FR"},
    "name": "Somewhere",
}


async def _ask(location: str | None, *, resolved: object) -> tuple[AsyncMock, Any]:
    client = AsyncMock()
    client.get_current_weather = AsyncMock(return_value=CURRENT)
    user_id = uuid4()
    with (
        patch(
            "src.domains.agents.tools.location_resolution.resolve_location",
            AsyncMock(return_value=(resolved, None)),
        ),
        patch(
            f"{MODULE}._geocode_with_city_fallback",
            AsyncMock(return_value=(45.7, 4.8, "Lyon", "FR")),
        ),
        patch(f"{MODULE}._person_timezone_and_language", AsyncMock(return_value=("UTC", "fr"))),
        patch(f"{MODULE}.attach_environment_extras", AsyncMock(return_value=None)),
        patch(f"{MODULE}.publish_companion_weather", AsyncMock(return_value=True)) as offer,
    ):
        await _get_current_weather_tool_impl.execute_api_call(
            client,
            user_id,
            location=location,
            runtime=None,
            units="metric",
            user_message="quel temps fait-il",
        )
    return offer, user_id


@pytest.mark.parametrize("location", [None, "auto", "AUTO"])
async def test_the_persons_own_place_feeds_the_companion(location: str | None) -> None:
    here = SimpleNamespace(lat=48.85, lon=2.35, source="browser", address=None)

    offer, user_id = await _ask(location, resolved=here)

    offer.assert_awaited_once_with(user_id, CURRENT)


async def test_a_city_someone_names_is_not_the_persons_present() -> None:
    offer, _ = await _ask("Lyon", resolved=None)

    offer.assert_not_awaited()


async def test_an_auto_place_nothing_resolved_is_not_the_persons_present() -> None:
    # ``auto`` that resolves to nothing falls back to geocoding the word: whatever
    # it finds is not where the person is.
    offer, _ = await _ask("auto", resolved=None)

    offer.assert_not_awaited()
