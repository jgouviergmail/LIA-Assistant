"""The current weather is one object per place; a forecast point is its instant, planned."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from src.domains.connectors import discussion_weather
from src.domains.connectors.discussion_weather import WeatherDiscussionSource
from src.domains.shared.discussion_sources import (
    ResearchRequest,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
)
from src.domains.users.discussion_location import LocationFocus

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)
OWNER = uuid4()
# Measured on the provider: two reads 46 s apart stamp the current conditions 46 s
# apart, every value unchanged.
READ_GAP_SECONDS = 46


class StampingWeather:
    """A weather client that stamps the current conditions with the instant it answers."""

    def __init__(self, temperatures: list[float]) -> None:
        self.temperatures = temperatures
        self.answers = 0

    async def get_current_weather(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str | None = None,
    ) -> object:
        self.answers += 1
        return {
            "dt": int(NOW.timestamp()) + READ_GAP_SECONDS * self.answers,
            "main": {"temp": self.temperatures[self.answers - 1], "humidity": 70.0},
            "weather": [{"main": "Clouds", "description": "overcast"}],
        }

    async def get_forecast(
        self,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
        units: str = "metric",
        lang: str | None = None,
        cnt: int = 40,
    ) -> object:
        return {
            "list": [
                {"dt": int((NOW + timedelta(hours=hour)).timestamp()), "main": {"temp": 9.0}}
                for hour in (1, 2)
            ]
        }

    async def close(self) -> None:
        return None


@pytest.fixture
def weather(monkeypatch: pytest.MonkeyPatch):
    def install(client: StampingWeather) -> None:
        async def focus(owner: UUID, *, now: datetime) -> LocationFocus:
            return LocationFocus(
                lat=48.1, lon=2.1, origin="home", expires_at=now + timedelta(minutes=15)
            )

        @asynccontextmanager
        async def opened(owner: UUID) -> AsyncIterator[StampingWeather]:
            yield client

        monkeypatch.setattr(discussion_weather, "read_location_focus", focus)
        monkeypatch.setattr(discussion_weather, "open_discussion_weather", opened)

    return install


async def read(operation: str = "recent") -> SourceSnapshot:
    research = (
        ResearchRequest(
            source=SourceKey.WEATHER, operation="future", start=NOW, end=NOW + timedelta(days=2)
        )
        if operation == "future"
        else ResearchRequest(source=SourceKey.WEATHER, operation="recent")
    )
    return await WeatherDiscussionSource().read(
        SourceReadRequest(
            owner_id=OWNER,
            run_id=uuid4(),
            policy_revision=1,
            request=research,
            allowed_sources=(SourceKey.WEATHER, SourceKey.LOCATION),
            now=NOW,
            window_start=research.start or NOW - timedelta(days=7),
            window_end=research.end or NOW + timedelta(days=7),
            item_limit=5,
            item_max_chars=2000,
            call_limit=8,
            timeout_seconds=10,
        )
    )


async def test_unchanged_conditions_read_twice_are_one_object_at_one_version(weather):
    # Production 2026-10-21: identified by the instant the provider answered, the
    # current conditions were a new object at every read, so every revalidation
    # stopped the run before its first call.
    weather(StampingWeather([12.0, 12.0]))
    first, second = (await read()).items[0], (await read()).items[0]
    assert first.object_id == second.object_id == "current"
    assert first.reference == second.reference
    assert first.version == second.version
    assert first.occurred_at != second.occurred_at


async def test_the_current_conditions_are_observed_even_stamped_after_the_read(weather):
    weather(StampingWeather([12.0]))
    (item,) = (await read()).items
    assert item.occurred_at is not None and item.occurred_at > NOW
    assert item.assertion == "observed"


async def test_changed_conditions_are_a_new_version_of_the_same_object(weather):
    weather(StampingWeather([12.0, 13.5]))
    first, second = (await read()).items[0], (await read()).items[0]
    assert first.reference == second.reference
    assert first.version != second.version


async def test_a_forecast_point_is_identified_by_its_instant_and_planned(weather):
    weather(StampingWeather([]))
    items = (await read("future")).items
    assert len({item.reference for item in items}) == 2
    assert all(item.object_id != "current" for item in items)
    assert {item.assertion for item in items} == {"planned"}


@pytest.mark.parametrize("drift", [0.1, 0.3, -0.4])
async def test_a_drift_no_sentence_would_mention_keeps_the_version(weather, drift):
    # Measured 2026-10-21: the provider refreshed its current conditions within four
    # minutes on a felt-temperature drift; versioned on every decimal, the weather was
    # interpreted again at every run and a re-read after a refresh stopped the run.
    weather(StampingWeather([12.0, 12.0 + drift]))
    first, second = (await read()).items[0], (await read()).items[0]
    assert first.version == second.version
    # The model still reads every value: only the version is rounded.
    assert first.excerpt != second.excerpt


async def test_a_whole_degree_is_a_new_version(weather):
    weather(StampingWeather([12.0, 13.0]))
    first, second = (await read()).items[0], (await read()).items[0]
    assert first.version != second.version
