"""Answering an invitation on the three calendars — one contract (ADR-369, lot 5).

Three shapes of one gesture: Google keeps the person's answer on their own attendee and
tells the organiser when asked to; Graph has an act per answer; CalDAV changes the
person's own ``PARTSTAT`` and leaves the rest to the server (RFC 6638). None of them
answers for anybody else, and an event the person organises has nothing to answer.
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
from src.domains.connectors.clients.calendar_answers import NotInvitedError
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials

pytestmark = pytest.mark.unit

ME = "me@icloud.com"


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
    ATTENDEES = (
        {"email": "ana@example.org", "responseStatus": "accepted"},
        {"email": "me@example.org", "self": True, "responseStatus": "needsAction"},
    )

    @pytest.fixture
    def client(self) -> Iterator[GoogleCalendarClient]:
        client = GoogleCalendarClient(uuid4(), _credentials(), MagicMock())
        with patch(
            "src.domains.connectors.clients.google_calendar_client.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
            create=True,
        ):
            yield client

    def _answer(self, attendees: Any) -> Callable[[httpx.Request], httpx.Response]:
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"id": "e1", "attendees": list(attendees), "start": {}, "end": {}},
            )

        return answer

    @pytest.mark.parametrize("response", ["accepted", "declined", "tentative"])
    async def test_the_person_s_own_attendee_answers_and_the_organiser_is_told(
        self, client: GoogleCalendarClient, response: str
    ) -> None:
        recorder = _Recorder(self._answer(self.ATTENDEES))

        await _drive(client, recorder, lambda: client.respond_to_event("e1", response))

        method, url, body = recorder.calls[-1]
        assert method == "PATCH"
        assert "sendUpdates=all" in url
        assert body == {
            "attendees": [
                {"email": "ana@example.org", "responseStatus": "accepted"},
                {"email": "me@example.org", "self": True, "responseStatus": response},
            ]
        }

    async def test_an_event_that_does_not_name_the_person_has_nothing_to_answer(
        self, client: GoogleCalendarClient
    ) -> None:
        recorder = _Recorder(self._answer([{"email": "ana@example.org"}]))

        with pytest.raises(NotInvitedError):
            await _drive(client, recorder, lambda: client.respond_to_event("e1", "accepted"))

        assert {method for method, _, _ in recorder.calls} == {"GET"}


class TestOutlook:
    @pytest.fixture
    def client(self) -> MicrosoftCalendarClient:
        return MicrosoftCalendarClient(uuid4(), _credentials(), MagicMock())

    @pytest.mark.parametrize(
        ("response", "act"),
        [("accepted", "accept"), ("declined", "decline"), ("tentative", "tentativelyAccept")],
    )
    async def test_each_answer_is_graph_s_own_act_and_the_organiser_is_told(
        self, client: MicrosoftCalendarClient, response: str, act: str
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(202))

        await _drive(client, recorder, lambda: client.respond_to_event("e1", response))

        assert recorder.calls == [
            ("POST", f"https://graph.microsoft.com/v1.0/me/events/e1/{act}", {"sendResponse": True})
        ]


class TestApple:
    @staticmethod
    def _event(attendee: str = f"mailto:{ME}") -> Any:
        calendar = vobject.iCalendar()
        vevent = calendar.add("vevent")
        vevent.add("uid").value = "e1"
        vevent.add("summary").value = "Weekly sync"
        other = vevent.add("attendee")
        other.value = "mailto:ana@example.org"
        other.params["PARTSTAT"] = ["ACCEPTED"]
        mine = vevent.add("attendee")
        mine.value = attendee
        mine.params["PARTSTAT"] = ["NEEDS-ACTION"]
        mine.params["RSVP"] = ["TRUE"]
        return SimpleNamespace(vobject_instance=calendar, save=AsyncMock())

    @pytest.fixture
    def client(self) -> AppleCalendarClient:
        return AppleCalendarClient(
            uuid4(),
            AppleCredentials(apple_id=ME, app_password="abcd-efgh-ijkl-mnop"),
            MagicMock(),
        )

    def _found(self, client: AppleCalendarClient, event: Any) -> Any:
        return patch.multiple(
            client,
            _get_calendar=AsyncMock(return_value=MagicMock()),
            _find_event_by_uid=AsyncMock(return_value=event),
            _own_addresses=AsyncMock(return_value={ME, "alias@icloud.com"}),
        )

    @pytest.mark.parametrize(
        ("response", "status"),
        [("accepted", "ACCEPTED"), ("declined", "DECLINED"), ("tentative", "TENTATIVE")],
    )
    async def test_the_person_s_own_partstat_changes_and_nobody_else_s(
        self, client: AppleCalendarClient, response: str, status: str
    ) -> None:
        event = self._event()

        with self._found(client, event):
            await client.respond_to_event("e1", response)

        other, mine = event.vobject_instance.vevent.attendee_list
        assert other.params["PARTSTAT"] == ["ACCEPTED"]
        assert mine.params["PARTSTAT"] == [status]
        assert "RSVP" not in mine.params
        event.save.assert_awaited_once()

    @pytest.mark.parametrize("address", ["mailto:ME@ICLOUD.COM", "MAILTO:alias@icloud.com"])
    async def test_an_address_of_the_account_is_found_whatever_its_case(
        self, client: AppleCalendarClient, address: str
    ) -> None:
        event = self._event(address)

        with self._found(client, event):
            await client.respond_to_event("e1", "accepted")

        assert event.vobject_instance.vevent.attendee_list[1].params["PARTSTAT"] == ["ACCEPTED"]

    async def test_an_event_that_does_not_name_the_person_has_nothing_to_answer(
        self, client: AppleCalendarClient
    ) -> None:
        event = self._event("mailto:stranger@example.org")

        with self._found(client, event), pytest.raises(NotInvitedError):
            await client.respond_to_event("e1", "accepted")

        event.save.assert_not_awaited()

    async def test_an_event_gone_is_said(self, client: AppleCalendarClient) -> None:
        with self._found(client, None), pytest.raises(ValueError):
            await client.respond_to_event("e1", "accepted")
