"""Calendar ids as ONE path segment, and attendees told on an update (ADR-369, D2).

A Google calendar id may carry a ``#`` (a holiday calendar's does): interpolated
raw, the rest of the URL became a fragment and the request read another
endpoint. Every id the workbench hands a calendar client now travels quoted,
on Google and on Graph alike, a folded segment refused before any request.

An update now says whether attendees are told: Google takes ``sendUpdates``
(nobody was told before — the assistant's own deletes told everyone); Graph
tells attendees on its own and has no way to keep quiet, CalDAV neither — both
accept the argument and say so.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.event_bounds import bounds_of
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

HOLIDAYS = "fr.french#holiday@group.v.calendar.google.com"
QUOTED = "fr.french%23holiday%40group.v.calendar.google.com"
_AN_HOUR = bounds_of(
    "2026-11-02T10:00:00", "2026-11-02T11:00:00", ZoneInfo("Europe/Paris"), all_day=False
)


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


async def _drive(
    client: Any, answer: Callable[[httpx.Request], httpx.Response], call: Callable[[], Any]
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return answer(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await call()
    return seen


def _event(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": "e1", "summary": "Fête", "start": {}, "end": {}})


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

    @pytest.mark.parametrize(
        ("call", "method", "path"),
        [
            (
                lambda c: c.get_event("e/1", HOLIDAYS),
                "GET",
                f"/calendar/v3/calendars/{QUOTED}/events/e%2F1",
            ),
            (
                lambda c: c.update_event("e/1", summary="x", calendar_id=HOLIDAYS),
                "PATCH",
                f"/calendar/v3/calendars/{QUOTED}/events/e%2F1",
            ),
            (
                lambda c: c.delete_event("e/1", HOLIDAYS),
                "DELETE",
                f"/calendar/v3/calendars/{QUOTED}/events/e%2F1",
            ),
            (
                lambda c: c.create_event("x", _AN_HOUR, calendar_id=HOLIDAYS),
                "POST",
                f"/calendar/v3/calendars/{QUOTED}/events",
            ),
        ],
    )
    async def test_every_id_travels_as_one_segment(
        self,
        client: GoogleCalendarClient,
        call: Callable[[GoogleCalendarClient], Any],
        method: str,
        path: str,
    ) -> None:
        seen = await _drive(client, _event, lambda: call(client))

        # An update reads the event first (its all-day shape is kept): the act is the last call.
        assert (seen[-1].method, seen[-1].url.raw_path.decode().split("?")[0]) == (method, path)

    async def test_a_folded_id_is_refused_before_any_request(
        self, client: GoogleCalendarClient
    ) -> None:
        seen: list[httpx.Request] = []
        with pytest.raises(ConnectorAPIError):
            seen = await _drive(client, _event, lambda: client.get_event("..", "primary"))
        assert seen == []

    @pytest.mark.parametrize(("send_updates", "expected"), [("all", "all"), ("none", "none")])
    async def test_an_update_says_whether_attendees_are_told(
        self, client: GoogleCalendarClient, send_updates: str, expected: str
    ) -> None:
        seen = await _drive(
            client,
            _event,
            lambda: client.update_event("e1", summary="x", send_updates=send_updates),
        )

        assert (seen[-1].method, seen[-1].url.params["sendUpdates"]) == ("PATCH", expected)
        assert json.loads(seen[-1].content)["summary"] == "x"

    async def test_an_update_that_says_nothing_keeps_google_s_default(
        self, client: GoogleCalendarClient
    ) -> None:
        seen = await _drive(client, _event, lambda: client.update_event("e1", summary="x"))

        assert seen[-1].method == "PATCH" and "sendUpdates" not in seen[-1].url.params


class TestGraph:
    @pytest.fixture
    def client(self) -> MicrosoftCalendarClient:
        return MicrosoftCalendarClient(uuid4(), _credentials(), MagicMock())

    @pytest.mark.parametrize(
        ("call", "method", "path"),
        [
            (lambda c: c.get_event("AA/k=", "primary"), "GET", "/v1.0/me/events/AA%2Fk%3D"),
            (
                lambda c: c.update_event("AA/k=", summary="x", send_updates="none"),
                "PATCH",
                "/v1.0/me/events/AA%2Fk%3D",
            ),
            (lambda c: c.delete_event("AA/k="), "DELETE", "/v1.0/me/events/AA%2Fk%3D"),
            (
                lambda c: c.create_event("x", _AN_HOUR, calendar_id="Cal/1="),
                "POST",
                "/v1.0/me/calendars/Cal%2F1%3D/events",
            ),
        ],
    )
    async def test_every_id_travels_as_one_segment(
        self,
        client: MicrosoftCalendarClient,
        call: Callable[[MicrosoftCalendarClient], Any],
        method: str,
        path: str,
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(200, json={"id": "AA", "subject": "x"})

        seen = await _drive(client, answer, lambda: call(client))

        assert (seen[0].method, seen[0].url.raw_path.decode().split("?")[0]) == (method, path)
