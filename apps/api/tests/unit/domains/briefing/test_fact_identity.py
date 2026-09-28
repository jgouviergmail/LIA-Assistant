"""The briefing's items carry WHAT they are, beside how they are shown (ADR-322).

A condition routine checked every ten minutes must know which mail, task,
event or file it has already announced. The display strings cannot say it:
« 09:00 tomorrow » becomes « 09:00 » at midnight, « 14:05 » becomes
« yesterday 14:05 » the next day. So each item carries the provider's id, an
event its start instant, and a forecast alert the instant of its slot — while
the card keeps rendering exactly what it rendered.

The weather routine also gets a read of its own: the card's full fetch bills a
city name, air quality and pollen that a condition never reads.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.domains.briefing.exceptions import ConnectorAccessError, ConnectorNotConfiguredError
from src.domains.briefing.fetchers import _task_to_item, fetch_agenda, fetch_forecast_alert
from src.domains.briefing.formatters import (
    _detect_forecast_alert,
    event_instant,
    format_agenda_event,
    format_email_item,
    is_event_past,
)
from src.domains.users.user_location_service import NoLocationAvailableError

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
_FETCHERS = "src.domains.briefing.fetchers"


class TestTheItemsSayWhatTheyAre:
    def test_a_mail_carries_its_message_id(self) -> None:
        item = format_email_item(
            {"id": "18c2f", "from": "Marie <m@acme.fr>", "subject": "Devis"}, PARIS, "fr"
        )

        assert item.id == "18c2f"

    def test_a_task_carries_its_id(self) -> None:
        item = _task_to_item(
            {"id": "t-9", "title": "Facture", "status": "needsAction"}, datetime.now(PARIS).date()
        )

        assert item is not None
        assert item.id == "t-9"

    @pytest.mark.parametrize(
        ("start", "expected"),
        [
            ({"dateTime": "2026-09-26T09:00:00+02:00"}, datetime(2026, 9, 26, 7, 0, tzinfo=UTC)),
            (
                {"dateTime": "2026-09-26T09:00:00", "timeZone": "America/New_York"},
                datetime(2026, 9, 26, 13, 0, tzinfo=UTC),
            ),
            # CalDAV's naive datetime is the person's own wall clock.
            ({"dateTime": "2026-09-26T09:00:00"}, datetime(2026, 9, 26, 7, 0, tzinfo=UTC)),
            # An all-day event starts at local midnight.
            ({"date": "2026-09-26"}, datetime(2026, 9, 25, 22, 0, tzinfo=UTC)),
        ],
        ids=["google-offset", "microsoft-zone", "apple-naive", "all-day"],
    )
    def test_an_event_carries_its_id_and_start_instant(
        self, start: dict[str, str], expected: datetime
    ) -> None:
        item = format_agenda_event({"id": "ev-1", "summary": "Vol", "start": start}, PARIS, "fr")

        assert item.id == "ev-1"
        assert item.start_at == expected
        assert item.start_at is not None and item.start_at.tzinfo == UTC

    def test_an_unreadable_start_keeps_the_card_and_drops_only_the_instant(self) -> None:
        item = format_agenda_event(
            {"summary": "Vol", "start": {"dateTime": "not-a-date"}}, PARIS, "fr"
        )

        assert item.start_at is None
        assert item.id is None
        assert item.start_local == "not-a-date"

    def test_a_forecast_alert_carries_its_slot_instant(self) -> None:
        slot = datetime(2026, 9, 25, 16, 0, tzinfo=UTC)
        alert = _detect_forecast_alert(
            current={"weather": [{"main": "Clear"}]},
            forecast={"list": [{"dt": int(slot.timestamp()), "weather": [{"main": "Rain"}]}]},
            user_tz=PARIS,
        )

        assert alert is not None
        assert alert.time == "18:00"
        assert alert.starts_at == slot


class TestOneReadingOfAnEventTime:
    """``event_instant`` replaced two copies; the end test must not move."""

    def test_garbage_reads_as_no_instant(self) -> None:
        assert event_instant("2026-09-26", PARIS) is None
        assert event_instant({}, PARIS) is None
        assert event_instant({"dateTime": 12}, PARIS) is None

    def test_an_all_day_event_ending_today_is_past_at_midnight(self) -> None:
        now = datetime(2026, 9, 25, 22, 30, tzinfo=UTC)  # 00:30 on the 26th in Paris
        event = {"end": {"date": "2026-09-26"}}

        assert is_event_past(event, now, PARIS) is True

    def test_an_event_without_a_readable_end_is_kept(self) -> None:
        now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)

        assert is_event_past({"end": "tomorrow"}, now, PARIS) is False
        assert is_event_past({}, now, PARIS) is False


def _weather_env(*, client: Any, location: Any = None, no_location: bool = False) -> Any:
    """Patch the session-bound half of the weather read."""

    @asynccontextmanager
    async def _ctx() -> Any:
        yield MagicMock()

    locator = MagicMock()
    locator.get_effective_location_for_proactive = AsyncMock(
        side_effect=NoLocationAvailableError() if no_location else None,
        return_value=location,
    )
    return (
        patch(f"{_FETCHERS}.get_db_context", _ctx),
        patch(f"{_FETCHERS}.resolve_weather_client", AsyncMock(return_value=client)),
        patch(f"{_FETCHERS}.UserLocationService", MagicMock(return_value=locator)),
        patch(f"{_FETCHERS}.environment_enrichment_active", AsyncMock(return_value=True)),
    )


def _weather_client() -> MagicMock:
    client = MagicMock()
    client.get_current_weather = AsyncMock(return_value={"weather": [{"main": "Clear"}]})
    client.get_forecast = AsyncMock(return_value={"list": []})
    client.close = AsyncMock()
    return client


class TestTheWeatherRoutinesOwnRead:
    async def test_it_asks_for_the_forecast_and_nothing_billed_beside_it(self) -> None:
        client = _weather_client()
        city = AsyncMock()
        extras = AsyncMock()
        env = _weather_env(client=client, location=SimpleNamespace(lat=48.85, lon=2.35))
        with (
            env[0],
            env[1],
            env[2],
            env[3],
            patch(f"{_FETCHERS}.resolve_city_name", city),
            patch(f"{_FETCHERS}.fetch_environment_extras", extras),
        ):
            alert = await fetch_forecast_alert(
                user=SimpleNamespace(id=uuid4()), user_tz=PARIS, language="fr"
            )

        assert alert is None
        client.get_current_weather.assert_awaited_once()
        client.get_forecast.assert_awaited_once()
        city.assert_not_awaited()
        extras.assert_not_awaited()
        client.close.assert_awaited_once()

    async def test_a_refusing_provider_is_a_classified_access_error_and_the_client_closes(
        self,
    ) -> None:
        client = _weather_client()
        client.get_forecast = AsyncMock(side_effect=httpx.ConnectError("down"))
        env = _weather_env(client=client, location=SimpleNamespace(lat=1.0, lon=2.0))
        with env[0], env[1], env[2], env[3], pytest.raises(ConnectorAccessError):
            await fetch_forecast_alert(
                user=SimpleNamespace(id=uuid4()), user_tz=PARIS, language="fr"
            )

        client.close.assert_awaited_once()

    async def test_no_location_is_not_configured_and_no_client_is_left_open(self) -> None:
        # The card's path used to leak the client here.
        client = _weather_client()
        env = _weather_env(client=client, no_location=True)
        with env[0], env[1], env[2], env[3], pytest.raises(ConnectorNotConfiguredError):
            await fetch_forecast_alert(
                user=SimpleNamespace(id=uuid4()), user_tz=PARIS, language="fr"
            )

        client.close.assert_awaited_once()
        client.get_forecast.assert_not_awaited()


class TestTheAgendaWindow:
    async def test_a_reader_with_its_own_window_is_served_it(self) -> None:
        from src.domains.connectors.calendar_access import CalendarAccess

        client = MagicMock()
        client.list_events = AsyncMock(return_value={"items": []})
        access = CalendarAccess(client=client, calendar_id="primary", connector_type=None)

        @asynccontextmanager
        async def _open(_user_id: Any) -> Any:
            yield access

        before = datetime.now(UTC)
        with patch("src.domains.connectors.calendar_access.open_active_calendar", _open):
            await fetch_agenda(
                user=SimpleNamespace(id=uuid4()), user_tz=PARIS, language="fr", lookahead_hours=4
            )

        kwargs = client.list_events.await_args.kwargs
        window = datetime.fromisoformat(kwargs["time_max"]) - datetime.fromisoformat(
            kwargs["time_min"]
        )
        assert window == timedelta(hours=4)
        assert datetime.fromisoformat(kwargs["time_min"]) >= before
