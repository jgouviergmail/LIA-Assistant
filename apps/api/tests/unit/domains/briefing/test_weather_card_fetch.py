"""The weather card reads its air-quality/pollen extras BESIDE the weather, never before it.

The extras used to be awaited before the weather calls started, adding their
whole latency to the card's (spec 2026-10-21 §0ter W1). They now run inside the
same ``gather``; their failure still yields a card without them.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.fetchers import fetch_weather

pytestmark = pytest.mark.unit

_FETCHERS = "src.domains.briefing.fetchers"


@asynccontextmanager
async def _db() -> AsyncIterator[object]:
    yield MagicMock()


def _client(current: Any) -> MagicMock:
    client = MagicMock()
    client.get_current_weather = current
    client.get_forecast = AsyncMock(return_value={"list": []})
    client.close = AsyncMock()
    return client


def _card_patches(client: MagicMock, extras: Any, formatted: dict[str, Any]) -> list[Any]:
    locator = MagicMock()
    locator.get_effective_location_for_proactive = AsyncMock(
        return_value=SimpleNamespace(lat=48.85, lon=2.35)
    )

    def capture(**kwargs: Any) -> str:
        formatted.update(kwargs)
        return "card"

    return [
        patch(f"{_FETCHERS}.get_db_context", _db),
        patch(f"{_FETCHERS}.resolve_weather_client", AsyncMock(return_value=client)),
        patch(f"{_FETCHERS}.UserLocationService", MagicMock(return_value=locator)),
        patch(f"{_FETCHERS}.environment_enrichment_active", AsyncMock(return_value=True)),
        patch(f"{_FETCHERS}.resolve_city_name", AsyncMock(return_value="Paris")),
        patch(f"{_FETCHERS}.extras_when_active", extras),
        patch(f"{_FETCHERS}.format_weather_data", capture),
    ]


async def _fetch(patches: list[Any]) -> Any:
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        return await asyncio.wait_for(
            fetch_weather(user=SimpleNamespace(id=uuid4()), user_tz=ZoneInfo("UTC"), language="fr"),
            timeout=2.0,
        )


async def test_extras_start_before_weather_finishes() -> None:
    """The extras wait on the weather call: awaited first, the card would never return."""
    weather_started = asyncio.Event()

    async def current(**_: Any) -> dict[str, Any]:
        weather_started.set()
        return {"weather": [{"main": "Clear"}]}

    async def extras(*_: Any) -> dict[str, Any]:
        await weather_started.wait()
        return {"aqi": 42}

    formatted: dict[str, Any] = {}
    client = _client(current)

    assert await _fetch(_card_patches(client, extras, formatted)) == "card"
    assert formatted["environment"] == {"aqi": 42}
    assert formatted["city"] == "Paris"
    client.close.assert_awaited_once()


async def test_extras_failure_keeps_weather_card() -> None:
    """A failing environment provider leaves the card whole, without the extras."""

    opened: list[BrokenEnvironment] = []

    class BrokenEnvironment:
        def __init__(self, user_id: object) -> None:
            self.closed = False
            opened.append(self)

        async def get_air_quality(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("air quality down")

        async def get_pollen_forecast(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError("pollen down")

        async def close(self) -> None:
            self.closed = True

    from src.domains.agents.tools import weather_environment_enrichment as enrichment

    formatted: dict[str, Any] = {}
    client = _client(AsyncMock(return_value={"weather": [{"main": "Rain"}]}))
    with (
        patch.object(enrichment, "GoogleEnvironmentClient", BrokenEnvironment),
        patch.object(enrichment, "_get_redis", AsyncMock(side_effect=ConnectionError)),
    ):
        card = await _fetch(_card_patches(client, enrichment.extras_when_active, formatted))

    assert card == "card"
    assert formatted["environment"] is None
    assert formatted["current"] == {"weather": [{"main": "Rain"}]}
    # The environment client is closed even though both of its reads failed.
    assert [env.closed for env in opened] == [True]


#: The provider's own days, as ``GoogleWeatherClient.get_daily_summaries`` returns them.
_DAYS = [{"date": "2026-10-29", "temp_min": 4.5, "temp_max": 12.0, "conditions": ["Clouds"]}]


async def test_a_provider_with_daily_summaries_reads_one_day_of_slots_and_its_days() -> None:
    """W1b: 1 hourly page and 1 daily request, where the 5-day strip cost 5 hourly pages."""
    from src.core.config import settings

    formatted: dict[str, Any] = {}
    client = _client(AsyncMock(return_value={"weather": [{"main": "Clear"}]}))
    client.native_daily_summaries = True
    client.get_daily_summaries = AsyncMock(return_value=_DAYS)

    await _fetch(_card_patches(client, AsyncMock(return_value=None), formatted))

    assert client.get_forecast.await_args.kwargs["cnt"] == 8  # the alert's 24 hours, 3-hourly
    client.get_daily_summaries.assert_awaited_once_with(
        48.85, 2.35, lang="fr", days=settings.briefing_weather_daily_forecast_days
    )
    assert formatted["daily_summaries"] == _DAYS


async def test_a_provider_without_them_keeps_its_five_day_slots() -> None:
    """OpenWeatherMap serves five days of slots in ONE request: nothing changes for it."""
    formatted: dict[str, Any] = {}
    client = _client(AsyncMock(return_value={"weather": [{"main": "Clear"}]}))

    await _fetch(_card_patches(client, AsyncMock(return_value=None), formatted))

    assert client.get_forecast.await_args.kwargs["cnt"] == 40
    assert formatted["daily_summaries"] is None


async def test_a_failing_weather_call_waits_for_its_siblings_before_the_card_fails() -> None:
    """Fresh review B3: one weather call failing fast made ``gather`` raise at once and
    left the air-quality and pollen requests running — they finished after the act's
    spend was filed (their billed calls appended to an exited tracker) and after the
    weather client was closed under the forecast still using it."""
    from src.core.exceptions import ConnectorAPIError
    from src.domains.briefing.exceptions import ConnectorAccessError

    settled: list[str] = []

    async def current(**_: Any) -> dict[str, Any]:
        raise ConnectorAPIError(connector_type="google_weather", status_code=403, detail="no")

    async def extras(*_: Any) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        settled.append("extras")
        return {"aqi": 42}

    client = _client(current)

    async def forecast(**_: Any) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        settled.append("forecast")
        return {"list": []}

    client.get_forecast = forecast
    client.close = AsyncMock(side_effect=lambda: settled.append("close"))

    with pytest.raises(ConnectorAccessError):
        await _fetch(_card_patches(client, extras, {}))

    assert sorted(settled[:2]) == ["extras", "forecast"]
    assert settled[-1] == "close"
