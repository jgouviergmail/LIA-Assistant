"""Golden net: what the clients send today for what the workbench must not change.

The workbench programme (``docs/superpowers/plans/2026-10-31-workbench.md``) gives
the provider clients all-day events, multi-valued contacts, a read state and
paging. Those additions must leave the existing requests byte for byte: a TIMED
event created or updated, a contact's name / organisation / notes updated, the first
page of tasks and of Graph contacts, and Gmail's label batch. This file records
those requests at the HTTP transport (or the CalDAV object for Apple's calendar)
and compares them with the frozen copy. ``UPDATE_GOLDEN=1`` rewrites it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import httpx
import pytest
import vobject

from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.apple_contacts_client import AppleContactsClient
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.clients.microsoft_tasks_client import MicrosoftTasksClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_GOLDEN = Path(__file__).parent / "golden" / "workbench_client_requests.json"
_GENERATION_REDIS = "src.domains.connectors.clients.google_gmail_client.get_redis_cache"
_USER = UUID("00000000-0000-4000-8000-000000000001")
_TIMED = {
    "summary": "Dentist",
    "start_datetime": "2026-11-02T10:00:00",
    "end_datetime": "2026-11-02T11:00:00",
    "timezone": "UTC",
}
#: The identity a confirmed draft carries; without one the provider id is random.
_KEY = "draft:golden"
_CONTACT_FIELDS = {"name": "Ada Lovelace", "organization": "Analytical", "notes": "Met at a talk"}
_VCARD = (
    "BEGIN:VCARD\r\nVERSION:3.0\r\nUID:ada-1\r\nFN:Ada Byron\r\nN:Byron;Ada;;;\r\n"
    "EMAIL;TYPE=HOME:ada@example.com\r\nEMAIL;TYPE=WORK:ada@work.example.com\r\n"
    "TEL;TYPE=CELL:+15550100\r\nX-CUSTOM:kept\r\nEND:VCARD\r\n"
)


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    """An HTTP transport that writes down every request and answers from a table."""

    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        raw = request.content.decode() if request.content else ""
        try:
            body: Any = json.loads(raw) if raw else None
        except ValueError:
            body = raw.replace("\r\n", "\n")
        self.calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(sorted(request.url.params.multi_items())),
                "body": body,
            }
        )
        return self.answer(request)


async def _drive(client: Any, recorder: _Recorder, call: Callable[[], Any]) -> list[dict[str, Any]]:
    """Run ``call`` with ``client`` talking to ``recorder`` only."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
            # No real Redis: an unreadable cache generation bypasses the cache.
            patch(_GENERATION_REDIS, AsyncMock(side_effect=ConnectionError("no redis"))),
        ):
            await call()
    return recorder.calls


def _google_event(request: httpx.Request) -> httpx.Response:
    if request.method == "GET":
        return httpx.Response(
            200,
            json={
                "id": "evt-1",
                "summary": "Old",
                "start": {"dateTime": "2026-11-02T09:00:00Z", "timeZone": "UTC"},
                "end": {"dateTime": "2026-11-02T09:30:00Z", "timeZone": "UTC"},
            },
        )
    return httpx.Response(200, json={"id": "evt-1", "status": "confirmed"})


def _graph_event(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        201 if request.method == "POST" else 200,
        json={
            "id": "graph-evt-1",
            "subject": "Old",
            "start": {"dateTime": "2026-11-02T09:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-11-02T09:30:00.0000000", "timeZone": "UTC"},
        },
    )


async def _google_calendar() -> list[dict[str, Any]]:
    client = GoogleCalendarClient(_USER, _credentials(), MagicMock())
    recorder = _Recorder(_google_event)

    async def run() -> None:
        await client.create_event(**_TIMED, idempotency_key=_KEY)
        await client.update_event("evt-1", **_TIMED)

    return await _drive(client, recorder, run)


async def _microsoft_calendar() -> list[dict[str, Any]]:
    client = MicrosoftCalendarClient(_USER, _credentials(), MagicMock())
    recorder = _Recorder(_graph_event)

    async def run() -> None:
        await client.create_event(**_TIMED, idempotency_key=_KEY)
        await client.update_event("graph-evt-1", **_TIMED)

    return await _drive(client, recorder, run)


class _CalDavEvent:
    """A stored CalDAV event whose ``save`` writes down its serialised VEVENT."""

    def __init__(self, uid: str, saves: list[dict[str, Any]]) -> None:
        cal = vobject.iCalendar()
        vevent = cal.add("vevent")
        vevent.add("uid").value = uid
        vevent.add("summary").value = "Old"
        vevent.add("dtstart").value = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
        vevent.add("dtend").value = datetime(2026, 11, 2, 9, 30, tzinfo=UTC)
        self.vobject_instance = cal
        self._saves = saves

    async def save(self) -> None:
        vevent = self.vobject_instance.vevent
        self._saves.append(
            {
                "dtstart": vevent.dtstart.value.isoformat(),
                "dtend": vevent.dtend.value.isoformat(),
                "summary": vevent.summary.value,
            }
        )


class _CalDavCalendar:
    def __init__(self) -> None:
        self.saves: list[dict[str, Any]] = []
        self.event = _CalDavEvent("apple-evt-1", self.saves)

    async def save_event(self, **kwargs: Any) -> Any:
        self.saves.append(
            {
                key: (value.isoformat() if isinstance(value, datetime) else value)
                for key, value in sorted(kwargs.items())
                if key != "uid"  # drawn before the retry loop (S1): random by design
            }
        )
        saved = MagicMock()
        saved.vobject_instance = None
        return saved

    async def search(self, **_: Any) -> list[Any]:
        return [self.event]


async def _apple_calendar() -> list[dict[str, Any]]:
    client = AppleCalendarClient(_USER, MagicMock(), MagicMock())
    calendar = _CalDavCalendar()
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch.object(client, "_rate_limit", AsyncMock()),
        patch.object(client, "_get_circuit_breaker", return_value=breaker),
        patch.object(client, "_get_calendar", AsyncMock(return_value=calendar)),
        patch(
            "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
            return_value={"id": "apple-evt-1"},
        ),
        patch("asyncio.sleep", AsyncMock()),
    ):
        await client.create_event(**_TIMED)
        await client.update_event("apple-evt-1", **_TIMED)
    return calendar.saves


def _people(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "resourceName": "people/c1",
            "etag": "etag-1",
            "names": [{"displayName": "Ada Byron", "givenName": "Ada"}],
            "emailAddresses": [
                {"value": "ada@example.com", "type": "home"},
                {"value": "ada@work.example.com", "type": "work"},
            ],
        },
    )


async def _google_contacts() -> list[dict[str, Any]]:
    client = GooglePeopleClient(_USER, _credentials(), MagicMock())
    recorder = _Recorder(_people)
    with patch.object(client, "_get_cache", AsyncMock(return_value=AsyncMock())):
        return await _drive(
            client, recorder, lambda: client.update_contact("people/c1", **_CONTACT_FIELDS)
        )


def _graph_contact(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "graph-contact-1",
            "displayName": "Ada Byron",
            "emailAddresses": [{"address": "ada@example.com", "name": "Ada"}],
        },
    )


async def _microsoft_contacts() -> list[dict[str, Any]]:
    client = MicrosoftContactsClient(_USER, _credentials(), MagicMock())
    recorder = _Recorder(_graph_contact)
    with patch(
        "src.domains.connectors.clients.microsoft_contacts_client.invalidate_contacts_cache",
        AsyncMock(),
    ):
        return await _drive(
            client,
            recorder,
            lambda: client.update_contact("people/graph-contact-1", **_CONTACT_FIELDS),
        )


async def _apple_contacts() -> list[dict[str, Any]]:
    client = AppleContactsClient(_USER, MagicMock(), MagicMock())

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text=_VCARD)
        return httpx.Response(204)

    recorder = _Recorder(answer)
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        breaker = MagicMock(
            check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock()
        )
        with (
            patch.object(client, "_get_http_client", AsyncMock(return_value=http)),
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_get_circuit_breaker", return_value=breaker),
            patch.object(client, "_invalidate_contacts_cache", AsyncMock()),
            patch("asyncio.sleep", AsyncMock()),
        ):
            await client.update_contact("https://contacts.icloud.com/ada-1.vcf", **_CONTACT_FIELDS)
    return recorder.calls


def _tasks_page(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "items": [{"id": "t1", "title": "One", "status": "needsAction"}],
            "value": [{"id": "t1", "title": "One", "status": "notStarted"}],
        },
    )


async def _google_tasks() -> list[dict[str, Any]]:
    client = GoogleTasksClient(_USER, _credentials(), MagicMock())
    return await _drive(client, _Recorder(_tasks_page), lambda: client.list_tasks("@default"))


async def _microsoft_tasks() -> list[dict[str, Any]]:
    client = MicrosoftTasksClient(_USER, _credentials(), MagicMock())
    return await _drive(client, _Recorder(_tasks_page), lambda: client.list_tasks("list-1"))


async def _microsoft_contact_page() -> list[dict[str, Any]]:
    client = MicrosoftContactsClient(_USER, _credentials(), MagicMock())

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [{"id": "c1", "displayName": "Ada"}]})

    return await _drive(
        client, _Recorder(answer), lambda: client.list_connections(page_size=25, use_cache=False)
    )


async def _gmail_label_batch() -> list[dict[str, Any]]:
    client = GoogleGmailClient(_USER, _credentials(), MagicMock())

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    return await _drive(
        client,
        _Recorder(answer),
        lambda: client.batch_modify_labels(
            ["m1", "m2"], add_label_ids=["Label_1"], remove_label_ids=["UNREAD"]
        ),
    )


_CASES: dict[str, Callable[[], Any]] = {
    "google_calendar.create_update_timed": _google_calendar,
    "microsoft_calendar.create_update_timed": _microsoft_calendar,
    "apple_calendar.create_update_timed": _apple_calendar,
    "google_contacts.update_scalar_fields": _google_contacts,
    "microsoft_contacts.update_scalar_fields": _microsoft_contacts,
    "apple_contacts.update_scalar_fields": _apple_contacts,
    "google_tasks.first_page": _google_tasks,
    "microsoft_tasks.first_page": _microsoft_tasks,
    "microsoft_contacts.first_page": _microsoft_contact_page,
    "gmail.batch_modify_labels": _gmail_label_batch,
}


def _frozen() -> dict[str, Any]:
    if not _GOLDEN.exists():
        return {}
    return dict(json.loads(_GOLDEN.read_text(encoding="utf-8")))


@pytest.mark.parametrize("case", sorted(_CASES))
async def test_requests_unchanged(case: str) -> None:
    recorded = json.loads(json.dumps(await _CASES[case](), default=str))
    if os.environ.get("UPDATE_GOLDEN") == "1":
        frozen = _frozen()
        frozen[case] = recorded
        _GOLDEN.parent.mkdir(exist_ok=True)
        _GOLDEN.write_text(
            json.dumps(frozen, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return
    assert recorded == _frozen().get(case), f"{case}: the client's requests changed"
