"""Unit tests for BriefingService — orchestration, status mapping, cache fallback."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.briefing.exceptions import (
    ConnectorAccessError,
    ConnectorNotConfiguredError,
)
from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    BriefingResponse,
    CardStatus,
    LLMUsage,
    MailsData,
    RemindersData,
    WeatherData,
)
from src.domains.briefing.service import BriefingService, _has_content

# =============================================================================
# Test fixtures (lightweight stand-ins for User + DB)
# =============================================================================


def _make_user(*, language: str = "fr", timezone: str = "Europe/Paris") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        full_name="Jean",
        email="jean@example.com",
        language=language,
        timezone=timezone,
        health_metrics_agents_enabled=False,
    )


def _make_weather() -> WeatherData:
    return WeatherData(
        temperature_c=18.0,
        condition_code="Clear",
        description="Ensoleillé",
        icon_emoji="☀️",
        location_city="Paris",
        forecast_alert=None,
    )


def _make_agenda_with_events() -> AgendaData:
    return AgendaData(events=[AgendaEventItem(title="Réunion", start_local="14:00", location=None)])


# =============================================================================
# _has_content
# =============================================================================


@pytest.mark.unit
class TestHasContent:
    def test_none_is_no_content(self) -> None:
        assert _has_content(None) is False

    def test_empty_events_is_no_content(self) -> None:
        assert _has_content(AgendaData(events=[])) is False

    def test_non_empty_events_is_content(self) -> None:
        assert _has_content(_make_agenda_with_events()) is True

    def test_empty_items_is_no_content(self) -> None:
        assert _has_content(MailsData(items=[], total_unread_today=0)) is False

    def test_weather_data_is_always_content(self) -> None:
        assert _has_content(_make_weather()) is True


# =============================================================================
# BriefingService._section — exception → status mapping
# =============================================================================


def _patch_redis_off():
    """Patch get_redis_cache to raise — forces all reads/writes to fail gracefully."""
    return patch(
        "src.domains.briefing.service.get_redis_cache",
        side_effect=ConnectionError("redis-down"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestSectionStatusMapping:
    async def test_ok_with_content(self) -> None:
        svc = BriefingService(user=_make_user())
        with _patch_redis_off():
            section = await svc._section(
                "weather",
                lambda: _coro(_make_weather()),
                ttl=3600,
                force=False,
            )
        assert section.status == CardStatus.OK
        assert section.data is not None

    async def test_empty_when_no_items(self) -> None:
        svc = BriefingService(user=_make_user())
        with _patch_redis_off():
            section = await svc._section(
                "agenda",
                lambda: _coro(AgendaData(events=[])),
                ttl=600,
                force=False,
            )
        assert section.status == CardStatus.EMPTY
        assert section.data is None

    async def test_not_configured_on_connector_not_configured(self) -> None:
        svc = BriefingService(user=_make_user())

        async def fetcher_raising():
            raise ConnectorNotConfiguredError("openweathermap")

        with _patch_redis_off():
            section = await svc._section("weather", fetcher_raising, ttl=3600, force=False)
        assert section.status == CardStatus.NOT_CONFIGURED
        assert section.error_code == "connector_not_configured"

    async def test_error_on_connector_access_error(self) -> None:
        svc = BriefingService(user=_make_user())

        async def fetcher_raising():
            raise ConnectorAccessError("calendar", "connector_oauth_expired", "Token expired")

        with _patch_redis_off():
            section = await svc._section("agenda", fetcher_raising, ttl=600, force=False)
        assert section.status == CardStatus.ERROR
        assert section.error_code == "connector_oauth_expired"
        assert section.error_message == "Token expired"

    async def test_error_on_unexpected_exception(self) -> None:
        svc = BriefingService(user=_make_user())

        async def fetcher_raising():
            raise ValueError("boom")

        with _patch_redis_off():
            section = await svc._section("mails", fetcher_raising, ttl=300, force=False)
        assert section.status == CardStatus.ERROR
        assert section.error_code == "internal"


# =============================================================================
# BriefingService.build_today — end-to-end orchestration with mocked LLM + fetchers
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_today_assembles_full_payload() -> None:
    svc = BriefingService(user=_make_user())

    # Patch all fetchers + LLM helpers + redis to avoid real I/O.
    with (
        _patch_redis_off(),
        patch(
            "src.domains.briefing.service.fetch_weather", AsyncMock(return_value=_make_weather())
        ),
        patch(
            "src.domains.briefing.service.fetch_agenda",
            AsyncMock(return_value=_make_agenda_with_events()),
        ),
        patch(
            "src.domains.briefing.service.fetch_mails",
            AsyncMock(return_value=MailsData(items=[], total_unread_today=0)),
        ),
        patch(
            "src.domains.briefing.service.fetch_birthdays",
            AsyncMock(side_effect=ConnectorNotConfiguredError("google_contacts")),
        ),
        patch(
            "src.domains.briefing.service.fetch_reminders",
            AsyncMock(return_value=RemindersData(items=[])),
        ),
        patch(
            "src.domains.briefing.service.fetch_health",
            AsyncMock(side_effect=ConnectorNotConfiguredError("health")),
        ),
        patch(
            "src.domains.briefing.service.generate_greeting",
            AsyncMock(return_value=("Bonjour Jean.", None)),
        ),
        patch(
            "src.domains.briefing.service.generate_synthesis",
            AsyncMock(return_value=(None, None)),
        ),
    ):
        response = await svc.build_today()

    assert isinstance(response, BriefingResponse)
    assert response.greeting.text == "Bonjour Jean."
    assert response.synthesis is None
    assert response.cards.weather.status == CardStatus.OK
    assert response.cards.agenda.status == CardStatus.OK
    assert response.cards.mails.status == CardStatus.EMPTY
    assert response.cards.birthdays.status == CardStatus.NOT_CONFIGURED
    assert response.cards.reminders.status == CardStatus.EMPTY
    assert response.cards.health.status == CardStatus.NOT_CONFIGURED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_today_force_refresh_all_bypasses_cache() -> None:
    svc = BriefingService(user=_make_user())

    fetchers = {
        "fetch_weather": AsyncMock(return_value=_make_weather()),
        "fetch_agenda": AsyncMock(return_value=_make_agenda_with_events()),
        "fetch_mails": AsyncMock(return_value=MailsData(items=[], total_unread_today=0)),
        "fetch_birthdays": AsyncMock(side_effect=ConnectorNotConfiguredError("g")),
        "fetch_reminders": AsyncMock(return_value=RemindersData(items=[])),
        "fetch_health": AsyncMock(side_effect=ConnectorNotConfiguredError("h")),
    }

    with (
        _patch_redis_off(),
        patch.multiple(
            "src.domains.briefing.service",
            **fetchers,  # type: ignore[arg-type]
            generate_greeting=AsyncMock(return_value=("Hi.", None)),
            generate_synthesis=AsyncMock(return_value=(None, None)),
        ),
    ):
        await svc.build_today(force_refresh={"all"})

    # Each forceable fetcher must have been called exactly once.
    assert fetchers["fetch_weather"].await_count == 1
    assert fetchers["fetch_agenda"].await_count == 1
    assert fetchers["fetch_reminders"].await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_today_propagates_llm_usage_into_text_sections() -> None:
    """LLMUsage returned by generate_greeting/synthesis lands on TextSection.usage."""
    svc = BriefingService(user=_make_user())

    greeting_usage = LLMUsage(
        tokens_in=120,
        tokens_out=15,
        tokens_cache=0,
        cost_eur=0.000045,
        model_name="gpt-4.1-nano",
    )
    synthesis_usage = LLMUsage(
        tokens_in=480,
        tokens_out=80,
        tokens_cache=64,
        cost_eur=0.000312,
        model_name="gpt-4.1-nano",
    )

    fetchers = {
        "fetch_weather": AsyncMock(return_value=_make_weather()),
        "fetch_agenda": AsyncMock(return_value=_make_agenda_with_events()),
        "fetch_mails": AsyncMock(return_value=MailsData(items=[], total_unread_today=0)),
        "fetch_birthdays": AsyncMock(side_effect=ConnectorNotConfiguredError("g")),
        "fetch_reminders": AsyncMock(return_value=RemindersData(items=[])),
        "fetch_health": AsyncMock(side_effect=ConnectorNotConfiguredError("h")),
    }

    with (
        _patch_redis_off(),
        patch.multiple(
            "src.domains.briefing.service",
            **fetchers,  # type: ignore[arg-type]
            generate_greeting=AsyncMock(return_value=("Bonjour Jean.", greeting_usage)),
            generate_synthesis=AsyncMock(return_value=("Belle journée à venir.", synthesis_usage)),
        ),
    ):
        response = await svc.build_today()

    assert response.greeting.text == "Bonjour Jean."
    assert response.greeting.usage == greeting_usage
    assert response.greeting.usage is not None
    assert response.greeting.usage.cost_eur == pytest.approx(0.000045)
    assert response.synthesis is not None
    assert response.synthesis.text == "Belle journée à venir."
    assert response.synthesis.usage == synthesis_usage


# =============================================================================
# Helpers
# =============================================================================


async def _coro(value):
    """Wrap a value in an awaitable for fetcher mocks."""
    return value
