"""The companion may borrow fresh weather, never initiate a provider read."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import PRESENT_WEATHER_FRESH_SECONDS
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session, get_session_store
from src.domains.briefing.companion import project_weather
from src.domains.briefing.constants import SECTION_WEATHER_TTL_SECONDS
from src.domains.briefing.router import router
from src.domains.briefing.schemas import AgendaData, CardSection, CardStatus, WeatherData
from src.domains.briefing.service import BriefingService
from src.domains.connectors.companion_weather import CompanionObservation
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


def test_projects_cached_google_rain_written_before_condition_normalization() -> None:
    cached = section(condition_code="RAIN")

    projected = project_weather(cached, NOW + timedelta(minutes=20))

    assert projected is not None
    assert projected.condition_code == "Rain"
    assert projected.expires_at == NOW + timedelta(seconds=SECTION_WEATHER_TTL_SECONDS)


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
        patch(
            "src.domains.briefing.section_outcomes.get_redis_cache", AsyncMock(return_value=cache)
        ),
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
        patch(
            "src.domains.briefing.section_outcomes.get_redis_cache", AsyncMock(return_value=cache)
        ),
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
        patch(
            "src.domains.briefing.section_outcomes.get_redis_cache",
            AsyncMock(side_effect=TimeoutError),
        ),
        TestClient(app) as client,
    ):
        result = client.get("/briefing/companion-context")
    assert result.status_code == 200
    assert result.json() == {"timezone": "Pacific/Auckland", "weather": None}


@pytest.mark.parametrize("endpoint", ["/briefing/companion-context", "/briefing/cached-weather"])
def test_anonymous_requests_never_reach_the_weather_cache(endpoint: str) -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_store] = lambda: MagicMock(spec=SessionStore)
    app.dependency_overrides[get_db] = lambda: AsyncMock(spec=AsyncSession)
    with (
        patch.object(BriefingService, "read_cached_weather", new_callable=AsyncMock) as read,
        TestClient(app) as client,
    ):
        result = client.get(endpoint)
    assert result.status_code == 401
    read.assert_not_awaited()


def test_cached_weather_widget_reads_only_the_owner_cache_without_starting_sources() -> None:
    app = FastAPI()
    app.include_router(router)
    user = User(id=uuid4(), language="en", timezone="UTC")
    app.dependency_overrides[get_current_active_session] = lambda: user
    cached = section()
    with (
        patch.object(
            BriefingService, "read_cached_weather", AsyncMock(return_value=cached)
        ) as read,
        patch.object(BriefingService, "build_cards", new_callable=AsyncMock) as build,
        patch("src.domains.briefing.service.fetch_weather", new_callable=AsyncMock) as fetch,
        TestClient(app) as client,
    ):
        result = client.get("/briefing/cached-weather")
    assert result.status_code == 200
    assert result.json()["data"]["temperature_c"] == 8
    read.assert_awaited_once()
    build.assert_not_awaited()
    fetch.assert_not_awaited()


def test_cached_weather_widget_refuses_another_valid_card_payload() -> None:
    app = FastAPI()
    app.include_router(router)
    user = User(id=uuid4(), language="en", timezone="UTC")
    app.dependency_overrides[get_current_active_session] = lambda: user
    wrong_card = CardSection(status=CardStatus.OK, generated_at=NOW, data=AgendaData(events=[]))
    with (
        patch.object(BriefingService, "read_cached_weather", AsyncMock(return_value=wrong_card)),
        patch("src.domains.briefing.service.fetch_weather", new_callable=AsyncMock) as fetch,
        TestClient(app) as client,
    ):
        result = client.get("/briefing/cached-weather")
    assert result.status_code == 200
    assert result.json() is None
    assert "no-store" in result.headers["Cache-Control"]
    fetch.assert_not_awaited()


def _endpoint(user: User, card: CardSection | None, observation: object) -> dict[str, object]:
    """The companion endpoint with a card cache and another read's observation."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session] = lambda: user
    cache = MagicMock()
    cache.get = AsyncMock(return_value=card.model_dump_json().encode() if card else None)
    with (
        patch(
            "src.domains.briefing.section_outcomes.get_redis_cache", AsyncMock(return_value=cache)
        ),
        patch(
            "src.domains.briefing.companion.read_companion_observation",
            AsyncMock(return_value=observation),
        ) as observed,
        patch("src.domains.briefing.service.fetch_weather", new_callable=AsyncMock) as fetch,
        TestClient(app) as client,
    ):
        result = client.get("/briefing/companion-context")
    fetch.assert_not_awaited()
    assert result.status_code == 200
    return {"json": result.json(), "observed": observed}


def _observation(minutes_ago: float, **values: object) -> CompanionObservation:
    fields: dict[str, object] = {
        "temperature_c": -2.0,
        "condition_code": "Snow",
        "wind_speed_kmh": 12.0,
        "observed_at": datetime.now(UTC) - timedelta(minutes=minutes_ago),
    }
    fields.update(values)
    return CompanionObservation.model_validate(fields)


def test_the_face_takes_the_newest_present_weather_any_read_left() -> None:
    user = User(id=uuid4(), language="fr", timezone="Europe/Paris")
    card = section()
    card.generated_at = datetime.now(UTC) - timedelta(minutes=40)
    observation = _observation(5)

    weather = _endpoint(user, card, observation)["json"]["weather"]

    # The heartbeat read five minutes ago; the card is forty minutes old.
    assert weather["temperature_c"] == -2.0
    assert weather["condition_code"] == "Snow"
    observed_at = datetime.fromisoformat(weather["observed_at"])
    assert observed_at == observation.observed_at
    assert datetime.fromisoformat(weather["expires_at"]) == observed_at + timedelta(
        seconds=PRESENT_WEATHER_FRESH_SECONDS
    )


def test_an_older_read_does_not_hide_a_newer_card() -> None:
    user = User(id=uuid4(), language="fr", timezone="Europe/Paris")
    card = section()
    card.generated_at = datetime.now(UTC) - timedelta(minutes=2)

    weather = _endpoint(user, card, _observation(30))["json"]["weather"]

    assert weather["temperature_c"] == 8
    assert weather["condition_code"] == "Rain"


def test_another_read_keeps_the_face_in_its_weather_once_the_card_aged_out() -> None:
    user = User(id=uuid4(), language="fr", timezone="Europe/Paris")
    card = section()
    card.generated_at = datetime.now(UTC) - timedelta(seconds=PRESENT_WEATHER_FRESH_SECONDS + 60)

    weather = _endpoint(user, card, _observation(10))["json"]["weather"]

    assert weather is not None and weather["condition_code"] == "Snow"


def test_an_aged_observation_is_not_the_present_either() -> None:
    user = User(id=uuid4(), language="fr", timezone="Europe/Paris")
    aged = _observation(PRESENT_WEATHER_FRESH_SECONDS / 60 + 1)

    assert _endpoint(user, None, aged)["json"]["weather"] is None


def test_a_hidden_weather_card_hides_every_read_from_the_face() -> None:
    user = User(
        id=uuid4(),
        language="fr",
        timezone="Europe/Paris",
        briefing_preferences={"hidden": ["weather"]},
    )

    outcome = _endpoint(user, None, _observation(1))

    assert outcome["json"]["weather"] is None
    outcome["observed"].assert_not_awaited()
