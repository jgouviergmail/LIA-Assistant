"""What an event says beyond its time, on the three calendars (ADR-369, lot 5).

A reminder, whether the time shows as busy, whether the event is private, and a video
call added to an event that has none: one contract, three spellings. What is left out
is kept: a provider's own default is nobody's to overwrite by accident.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
import vobject

from src.domains.connectors.clients.calendar_options import (
    NO_REMINDER,
    EventOptions,
    apply_ical_options,
    google_options,
    graph_options,
    ical_options,
)
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_event,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, str(request.url), body))
        return self.answer(request)


async def _drive(client: Any, recorder: _Recorder, call: Callable[[], Any]) -> Any:
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


class TestGoogleSpelling:
    @pytest.mark.parametrize(
        ("options", "expected"),
        [
            (EventOptions(), {}),
            (
                EventOptions(reminder_minutes=15),
                {
                    "reminders": {
                        "useDefault": False,
                        "overrides": [{"method": "popup", "minutes": 15}],
                    }
                },
            ),
            (
                EventOptions(reminder_minutes=NO_REMINDER),
                {"reminders": {"useDefault": False, "overrides": []}},
            ),
            (EventOptions(busy=True), {"transparency": "opaque"}),
            (EventOptions(busy=False), {"transparency": "transparent"}),
            (EventOptions(private=True), {"visibility": "private"}),
            (EventOptions(private=False), {"visibility": "default"}),
        ],
    )
    def test_each_option_is_google_s_word(
        self, options: EventOptions, expected: dict[str, Any]
    ) -> None:
        assert google_options(options) == expected


class TestGraphSpelling:
    @pytest.mark.parametrize(
        ("options", "expected"),
        [
            (EventOptions(), {}),
            (
                EventOptions(reminder_minutes=30),
                {"isReminderOn": True, "reminderMinutesBeforeStart": 30},
            ),
            (EventOptions(reminder_minutes=NO_REMINDER), {"isReminderOn": False}),
            (EventOptions(busy=True), {"showAs": "busy"}),
            (EventOptions(busy=False), {"showAs": "free"}),
            (EventOptions(private=True), {"sensitivity": "private"}),
            (EventOptions(private=False), {"sensitivity": "normal"}),
        ],
    )
    def test_each_option_is_graph_s_word(
        self, options: EventOptions, expected: dict[str, Any]
    ) -> None:
        assert graph_options(options) == expected


class TestGraphOwnZone:
    """Graph keeps an event's times in UTC and its zone beside them, in Windows' names."""

    @staticmethod
    def _read(zone: str | None) -> dict[str, Any]:
        at = {"dateTime": "2026-11-05T09:00:00.0000000", "timeZone": "UTC"}
        said = {"originalStartTimeZone": zone} if zone else {}
        return normalize_graph_event({"id": "e1", "start": at, "end": at, **said})

    @pytest.mark.parametrize(
        ("zone", "expected"),
        [
            ("Romance Standard Time", "Europe/Paris"),
            ("Pacific Standard Time", "America/Los_Angeles"),
            ("Asia/Tokyo", "Asia/Tokyo"),
        ],
    )
    def test_it_reads_in_iana_names(self, zone: str, expected: str) -> None:
        assert self._read(zone)["ownZone"] == expected

    def test_an_event_that_says_none_adds_nothing(self) -> None:
        assert "ownZone" not in self._read(None)


class TestICalendar:
    @staticmethod
    def _vevent() -> Any:
        calendar = vobject.iCalendar()
        vevent = calendar.add("vevent")
        vevent.add("uid").value = "e1"
        return vevent

    def test_a_reminder_is_one_alarm_before_the_event(self) -> None:
        vevent = self._vevent()

        apply_ical_options(vevent, EventOptions(reminder_minutes=45))

        assert ical_options(vevent) == {"reminderMinutes": 45}

    def test_a_new_reminder_replaces_the_old_one(self) -> None:
        vevent = self._vevent()
        apply_ical_options(vevent, EventOptions(reminder_minutes=45))

        apply_ical_options(vevent, EventOptions(reminder_minutes=10))

        assert len(vevent.valarm_list) == 1
        assert ical_options(vevent) == {"reminderMinutes": 10}

    def test_no_reminder_takes_the_alarm_off(self) -> None:
        vevent = self._vevent()
        apply_ical_options(vevent, EventOptions(reminder_minutes=45))

        apply_ical_options(vevent, EventOptions(reminder_minutes=NO_REMINDER))

        assert not hasattr(vevent, "valarm")

    @pytest.mark.parametrize(
        ("options", "read"),
        [
            (EventOptions(busy=True), {"transparency": "opaque"}),
            (EventOptions(busy=False), {"transparency": "transparent"}),
            (EventOptions(private=True), {"visibility": "private"}),
            (EventOptions(private=False), {"visibility": "default"}),
        ],
    )
    def test_what_is_written_reads_back_in_the_one_vocabulary(
        self, options: EventOptions, read: dict[str, Any]
    ) -> None:
        vevent = self._vevent()

        apply_ical_options(vevent, options)

        assert ical_options(vevent) == read

    def test_what_is_left_out_is_kept(self) -> None:
        vevent = self._vevent()
        apply_ical_options(vevent, EventOptions(reminder_minutes=45, busy=False))

        apply_ical_options(vevent, EventOptions(private=True))

        assert ical_options(vevent) == {
            "reminderMinutes": 45,
            "transparency": "transparent",
            "visibility": "private",
        }


class TestTheClients:
    @pytest.fixture
    def google(self) -> Iterator[GoogleCalendarClient]:
        client = GoogleCalendarClient(uuid4(), _credentials(), MagicMock())
        with patch(
            "src.domains.connectors.clients.google_calendar_client.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
            create=True,
        ):
            yield client

    async def test_google_adds_a_call_to_an_event_that_has_none(
        self, google: GoogleCalendarClient
    ) -> None:
        recorder = _Recorder(
            lambda request: httpx.Response(200, json={"id": "e1", "start": {}, "end": {}})
        )

        await _drive(google, recorder, lambda: google.update_event("e1", add_conference=True))

        method, url, body = recorder.calls[-1]
        assert method == "PATCH"
        assert "conferenceDataVersion=1" in url
        assert body["conferenceData"]["createRequest"]["conferenceSolutionKey"] == {
            "type": "hangoutsMeet"
        }

    async def test_google_writes_the_options_given_on_an_update(
        self, google: GoogleCalendarClient
    ) -> None:
        recorder = _Recorder(
            lambda request: httpx.Response(200, json={"id": "e1", "start": {}, "end": {}})
        )

        await _drive(
            google,
            recorder,
            lambda: google.update_event("e1", options=EventOptions(busy=False)),
        )

        assert recorder.calls[-1][2]["transparency"] == "transparent"

    async def test_graph_adds_a_call_and_the_options_on_an_update(self) -> None:
        client = MicrosoftCalendarClient(uuid4(), _credentials(), MagicMock())
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "e1"}))

        await _drive(
            client,
            recorder,
            lambda: client.update_event(
                "e1", add_conference=True, options=EventOptions(private=True)
            ),
        )

        body = recorder.calls[-1][2]
        assert body["isOnlineMeeting"] is True
        assert body["onlineMeetingProvider"] == "teamsForBusiness"
        assert body["sensitivity"] == "private"
