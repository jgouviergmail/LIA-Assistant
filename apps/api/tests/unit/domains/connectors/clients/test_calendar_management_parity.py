"""Changing an event's calendar and managing calendars, on the three (ADR-369, lot 5).

Google moves an event by name. Graph has no such act and CalDAV has none its servers share:
there the event is copied, then the original removed, which reaches attendees and loses what
a copy cannot carry. So a provider that copies refuses an event with guests, of a series or,
on Graph, with attachments, before anything is sent; and an event whose original could not
be removed is said to stand in both, never left to be found twice.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
import vobject

from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.calendar_management import (
    EventLeftBehindError,
    EventNotMovableError,
)
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials

pytestmark = pytest.mark.unit

GRAPH = "https://graph.microsoft.com/v1.0"


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


class TestGoogle:
    @pytest.fixture
    def client(self) -> Iterator[GoogleCalendarClient]:
        client = GoogleCalendarClient(uuid4(), _credentials(), MagicMock())
        with patch(
            "src.domains.connectors.clients.google_calendar_client.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
            create=True,
        ):
            yield client

    async def test_an_event_moves_by_name_and_keeps_its_id(
        self, client: GoogleCalendarClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "e1"}))

        moved = await _drive(client, recorder, lambda: client.move_event("e1", "a@x", "b@x"))

        assert moved["id"] == "e1"
        method, url, body = recorder.calls[-1]
        assert (method, body) == ("POST", None)
        assert "/calendars/a@x/events/e1/move" in url.replace("%40", "@")
        assert "destination=b%40x" in url

    async def test_a_calendar_is_created_in_the_account_s_zone(
        self, client: GoogleCalendarClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "c1"}))

        await _drive(client, recorder, lambda: client.create_calendar("Trips", "Europe/Paris"))

        assert recorder.calls[-1] == (
            "POST",
            "https://www.googleapis.com/calendar/v3/calendars",
            {"summary": "Trips", "timeZone": "Europe/Paris"},
        )

    async def test_a_calendar_is_renamed(self, client: GoogleCalendarClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "c1"}))

        await _drive(client, recorder, lambda: client.rename_calendar("c1", "Holidays"))

        method, url, body = recorder.calls[-1]
        assert (method, body) == ("PATCH", {"summary": "Holidays"})
        assert url.endswith("/calendars/c1")

    async def test_a_calendar_is_deleted(self, client: GoogleCalendarClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        await _drive(client, recorder, lambda: client.delete_calendar("c1"))

        method, url, _body = recorder.calls[-1]
        assert method == "DELETE"
        assert url.endswith("/calendars/c1")


class TestOutlook:
    EVENT = {
        "id": "e1",
        "subject": "Dentist",
        "body": {"contentType": "text", "content": "Bring the file"},
        "start": {"dateTime": "2026-11-05T09:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-11-05T10:00:00.0000000", "timeZone": "UTC"},
        "location": {"displayName": "Room 4"},
        "isAllDay": False,
        "showAs": "free",
        "sensitivity": "private",
        "isReminderOn": True,
        "reminderMinutesBeforeStart": 30,
        "categories": ["Health"],
        "importance": "high",
        "attendees": [],
        "type": "singleInstance",
        "hasAttachments": False,
        "webLink": "https://outlook.office.com/x",
    }

    @pytest.fixture
    def client(self) -> MicrosoftCalendarClient:
        return MicrosoftCalendarClient(uuid4(), _credentials(), MagicMock())

    def _answer(self, event: dict[str, Any], *, deleted: int = 204) -> Any:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, json=event)
            if request.method == "POST":
                return httpx.Response(201, json={**event, "id": "copy"})
            return httpx.Response(deleted)

        return answer

    async def test_an_event_is_copied_then_its_original_removed(
        self, client: MicrosoftCalendarClient
    ) -> None:
        recorder = _Recorder(self._answer(self.EVENT))

        moved = await _drive(client, recorder, lambda: client.move_event("e1", "a", "b"))

        assert moved["id"] == "copy"
        assert [method for method, _, _ in recorder.calls] == ["GET", "POST", "DELETE"]
        _, url, body = recorder.calls[1]
        assert url == f"{GRAPH}/me/calendars/b/events"
        assert recorder.calls[2][1] == f"{GRAPH}/me/events/e1"
        kept = {
            key: self.EVENT[key]
            for key in (
                "subject",
                "body",
                "start",
                "end",
                "location",
                "isAllDay",
                "showAs",
                "sensitivity",
                "isReminderOn",
                "reminderMinutesBeforeStart",
                "categories",
                "importance",
            )
        }
        assert {key: body[key] for key in kept} == kept
        assert body["transactionId"]

    async def test_the_copy_of_one_move_keeps_one_transaction(
        self, client: MicrosoftCalendarClient
    ) -> None:
        recorder = _Recorder(self._answer(self.EVENT))

        await _drive(client, recorder, lambda: client.move_event("e1", "a", "b"))
        await _drive(client, recorder, lambda: client.move_event("e1", "a", "b"))

        first, second = (body for method, _, body in recorder.calls if method == "POST")
        assert first["transactionId"] == second["transactionId"]

    @pytest.mark.parametrize(
        "change",
        [
            {"attendees": [{"emailAddress": {"address": "ana@example.org"}}]},
            {"type": "occurrence", "seriesMasterId": "s1"},
            {"type": "seriesMaster"},
            {"hasAttachments": True},
        ],
    )
    async def test_what_a_copy_would_reach_or_lose_is_refused_unsent(
        self, client: MicrosoftCalendarClient, change: dict[str, Any]
    ) -> None:
        recorder = _Recorder(self._answer({**self.EVENT, **change}))

        with pytest.raises(EventNotMovableError):
            await _drive(client, recorder, lambda: client.move_event("e1", "a", "b"))

        assert [method for method, _, _ in recorder.calls] == ["GET"]

    async def test_an_original_already_gone_is_the_move_done(
        self, client: MicrosoftCalendarClient
    ) -> None:
        """A removal resent after its answer was lost finds nothing: it was removed."""
        recorder = _Recorder(self._answer(self.EVENT, deleted=404))

        moved = await _drive(client, recorder, lambda: client.move_event("e1", "a", "b"))

        assert moved["id"] == "copy"

    async def test_an_original_that_stays_is_said(self, client: MicrosoftCalendarClient) -> None:
        recorder = _Recorder(self._answer(self.EVENT, deleted=403))

        with pytest.raises(EventLeftBehindError):
            await _drive(client, recorder, lambda: client.move_event("e1", "a", "b"))

    async def test_a_calendar_is_created_renamed_and_deleted(
        self, client: MicrosoftCalendarClient
    ) -> None:
        recorder = _Recorder(
            lambda request: (
                httpx.Response(204)
                if request.method == "DELETE"
                else httpx.Response(200, json={"id": "c1", "name": "Trips", "canEdit": True})
            )
        )

        created = await _drive(client, recorder, lambda: client.create_calendar("Trips"))
        await _drive(client, recorder, lambda: client.rename_calendar("c1", "Holidays"))
        await _drive(client, recorder, lambda: client.delete_calendar("c1"))

        assert created["id"] == "c1"
        assert recorder.calls == [
            ("POST", f"{GRAPH}/me/calendars", {"name": "Trips"}),
            ("PATCH", f"{GRAPH}/me/calendars/c1", {"name": "Holidays"}),
            ("DELETE", f"{GRAPH}/me/calendars/c1", None),
        ]


class TestApple:
    @staticmethod
    def _event(**properties: str) -> Any:
        calendar = vobject.iCalendar()
        vevent = calendar.add("vevent")
        vevent.add("uid").value = "e1"
        vevent.add("summary").value = "Dentist"
        for name, value in properties.items():
            vevent.add(name).value = value
        return SimpleNamespace(
            vobject_instance=calendar, data=calendar.serialize(), delete=AsyncMock()
        )

    @pytest.fixture
    def client(self) -> AppleCalendarClient:
        return AppleCalendarClient(
            uuid4(),
            AppleCredentials(apple_id="me@icloud.com", app_password="abcd-efgh-ijkl-mnop"),
            MagicMock(),
        )

    def _calendars(self, client: AppleCalendarClient, event: Any, target: Any) -> Any:
        source = MagicMock()
        calendars = {"a": source, "b": target}

        async def found(calendar_id: str) -> Any:
            return calendars[calendar_id]

        return patch.multiple(
            client,
            _get_calendar=AsyncMock(side_effect=found),
            _find_event_by_uid=AsyncMock(return_value=event),
        )

    async def test_an_event_is_copied_whole_then_its_original_removed(
        self, client: AppleCalendarClient
    ) -> None:
        event = self._event(location="Room 4")
        target = MagicMock(save_event=AsyncMock(return_value=event))

        with (
            self._calendars(client, event, target),
            patch(
                "src.domains.connectors.clients.apple_calendar_acts_mixin.normalize_vevent",
                return_value={"id": "e1"},
            ),
        ):
            moved = await client.move_event("e1", "a", "b")

        assert moved == {"id": "e1"}
        assert target.save_event.await_args.kwargs["ical"] == event.data
        assert "LOCATION:Room 4" in event.data
        event.delete.assert_awaited_once()

    @pytest.mark.parametrize(
        "properties", [{"attendee": "mailto:ana@example.org"}, {"rrule": "FREQ=WEEKLY"}]
    )
    async def test_what_a_copy_would_reach_is_refused_unsent(
        self, client: AppleCalendarClient, properties: dict[str, str]
    ) -> None:
        event = self._event(**properties)
        target = MagicMock(save_event=AsyncMock())

        with self._calendars(client, event, target), pytest.raises(EventNotMovableError):
            await client.move_event("e1", "a", "b")

        target.save_event.assert_not_awaited()
        event.delete.assert_not_awaited()

    async def test_an_event_gone_is_said(self, client: AppleCalendarClient) -> None:
        target = MagicMock(save_event=AsyncMock())

        with self._calendars(client, None, target), pytest.raises(ValueError):
            await client.move_event("e1", "a", "b")

        target.save_event.assert_not_awaited()

    async def test_an_original_that_stays_is_said_and_nothing_is_tried_twice(
        self, client: AppleCalendarClient
    ) -> None:
        event = self._event()
        event.delete = AsyncMock(side_effect=OSError("gone away"))
        target = MagicMock(save_event=AsyncMock(return_value=event))

        with (
            self._calendars(client, event, target),
            patch("asyncio.sleep", AsyncMock()),
            pytest.raises(EventLeftBehindError),
        ):
            await client.move_event("e1", "a", "b")

        target.save_event.assert_awaited_once()

    async def test_a_calendar_is_created_under_the_account(
        self, client: AppleCalendarClient
    ) -> None:
        made = MagicMock(url="https://caldav.icloud.com/c1/")
        principal = MagicMock(make_calendar=AsyncMock(return_value=made))

        with patch.object(client, "_get_principal", AsyncMock(return_value=principal)):
            created = await client.create_calendar("Trips")

        principal.make_calendar.assert_awaited_once_with(name="Trips")
        assert created["id"] == "https://caldav.icloud.com/c1/"
        assert created["summary"] == "Trips"

    async def test_a_calendar_is_renamed_in_place(self, client: AppleCalendarClient) -> None:
        calendar = MagicMock(url="https://caldav.icloud.com/c1/", set_properties=AsyncMock())

        with patch.object(client, "_get_calendar", AsyncMock(return_value=calendar)):
            await client.rename_calendar("https://caldav.icloud.com/c1/", "Holidays")

        (props,) = calendar.set_properties.await_args.args
        assert [prop.value for prop in props] == ["Holidays"]

    async def test_a_calendar_is_really_deleted_never_emptied(
        self, client: AppleCalendarClient
    ) -> None:
        calendar = MagicMock(delete=AsyncMock())

        with patch.object(client, "_get_calendar", AsyncMock(return_value=calendar)):
            await client.delete_calendar("https://caldav.icloud.com/c1/")

        calendar.delete.assert_awaited_once_with(wipe=False)
