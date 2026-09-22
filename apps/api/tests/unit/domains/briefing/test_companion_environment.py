"""The companion may borrow fresh weather, never initiate a provider read."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session, get_session_store
from src.domains.briefing.companion import project_weather
from src.domains.briefing.constants import SECTION_WEATHER_TTL_SECONDS
from src.domains.briefing.router import router
from src.domains.briefing.schemas import CardSection, CardStatus, WeatherData
from src.domains.briefing.service import BriefingService
from src.domains.users.models import User
from src.infrastructure.cache.session_store import SessionStore

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


def section(**updates: object) -> CardSection:
    values: dict[str, object] = {
        "temperature_c": 8,
        "condition_code": "Rain",
        "description": "private description",
        "icon_emoji": "rain",
        "location_city": "private location",
        "wind_speed_kmh": 30,
    }
    values.update(updates)
    return CardSection(
        status=CardStatus.OK, generated_at=NOW, data=WeatherData.model_validate(values)
    )


def test_projects_only_current_conditions_with_their_original_expiry() -> None:
    projected = project_weather(section(), NOW + timedelta(minutes=20))
    assert projected is not None
    assert projected.temperature_c == 8
    assert projected.condition_code == "Rain"
    assert projected.wind_speed_kmh == 30
    assert projected.observed_at == NOW
    assert projected.expires_at == NOW + timedelta(seconds=SECTION_WEATHER_TTL_SECONDS)
    assert "private" not in projected.model_dump_json()


@pytest.mark.parametrize("age", [-1, SECTION_WEATHER_TTL_SECONDS, SECTION_WEATHER_TTL_SECONDS + 1])
def test_missing_stale_and_future_weather_do_not_drive_the_face(age: int) -> None:
    assert project_weather(None, NOW) is None
    assert project_weather(section(), NOW + timedelta(seconds=age)) is None


@pytest.mark.parametrize("temperature", [float("nan"), float("inf"), -150, 100])
def test_malformed_weather_is_ignored(temperature: float) -> None:
    assert project_weather(section(temperature_c=temperature), NOW) is None


def test_error_with_last_known_good_is_not_current_weather() -> None:
    cached = section()
    cached.status = CardStatus.ERROR
    assert project_weather(cached, NOW) is None


async def test_a_hidden_weather_card_does_not_even_read_redis() -> None:
    user = User(
        id=uuid4(), language="en", timezone="UTC", briefing_preferences={"hidden": ["weather"]}
    )
    with patch.object(BriefingService, "_read_cache", new_callable=AsyncMock) as read:
        assert await BriefingService(user).read_cached_weather() is None
        read.assert_not_awaited()


async def test_only_the_current_accounts_weather_cache_is_read() -> None:
    user = User(id=uuid4(), language="fr", timezone="Europe/Paris")
    cached = section()
    with patch.object(
        BriefingService, "_read_cache", new_callable=AsyncMock, return_value=cached
    ) as read:
        assert await BriefingService(user).read_cached_weather() is cached
        assert read.await_count == 1
        key = read.call_args.args[0]
        assert str(user.id) in key and ":fr:weather" in key


def test_undated_and_non_weather_cards_are_not_evidence() -> None:
    cached = section()
    cached.generated_at = NOW.replace(tzinfo=None)
    assert project_weather(cached, NOW) is None
    assert project_weather(CardSection(status=CardStatus.OK, generated_at=NOW), NOW) is None


@pytest.mark.parametrize("raw", [None, "{broken", '{"data": "unexpected"}'])
def test_endpoint_cache_misses_and_malformed_data_never_fetch_weather(raw: str | None) -> None:
    app = FastAPI()
    app.include_router(router)
    user = User(id=uuid4(), language="fr", timezone="Europe/Paris")
    app.dependency_overrides[get_current_active_session] = lambda: user
    cache = MagicMock()
    cache.get = AsyncMock(return_value=raw)
    with (
        patch("src.domains.briefing.service.get_redis_cache", AsyncMock(return_value=cache)),
        patch("src.domains.briefing.service.fetch_weather", new_callable=AsyncMock) as fetch,
        TestClient(app) as client,
    ):
        result = client.get("/briefing/companion-context")
    assert result.status_code == 200
    assert result.json() == {"timezone": "Europe/Paris", "weather": None}
    cache.get.assert_awaited_once()
    fetch.assert_not_awaited()


def test_endpoint_projects_a_fresh_observation_without_location_or_a_second_read() -> None:
    app = FastAPI()
    app.include_router(router)
    user = User(id=uuid4(), language="fr", timezone="Europe/Paris")
    app.dependency_overrides[get_current_active_session] = lambda: user
    cached = section()
    cached.generated_at = datetime.now(UTC)
    cache = MagicMock()
    cache.get = AsyncMock(return_value=cached.model_dump_json().encode())
    with (
        patch("src.domains.briefing.service.get_redis_cache", AsyncMock(return_value=cache)),
        TestClient(app) as client,
    ):
        result = client.get("/briefing/companion-context")
    assert result.status_code == 200
    assert result.json()["weather"]["temperature_c"] == 8
    assert "private" not in result.text
    cache.get.assert_awaited_once()


def test_redis_failure_degrades_to_the_accounts_clock() -> None:
    app = FastAPI()
    app.include_router(router)
    user = User(id=uuid4(), language="en", timezone="Pacific/Auckland")
    app.dependency_overrides[get_current_active_session] = lambda: user
    with (
        patch("src.domains.briefing.service.get_redis_cache", AsyncMock(side_effect=TimeoutError)),
        TestClient(app) as client,
    ):
        result = client.get("/briefing/companion-context")
    assert result.status_code == 200
    assert result.json() == {"timezone": "Pacific/Auckland", "weather": None}


def test_anonymous_requests_never_reach_the_weather_cache() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_store] = lambda: MagicMock(spec=SessionStore)
    app.dependency_overrides[get_db] = lambda: AsyncMock(spec=AsyncSession)
    with (
        patch.object(BriefingService, "read_cached_weather", new_callable=AsyncMock) as read,
        TestClient(app) as client,
    ):
        result = client.get("/briefing/companion-context")
    assert result.status_code == 401
    read.assert_not_awaited()
