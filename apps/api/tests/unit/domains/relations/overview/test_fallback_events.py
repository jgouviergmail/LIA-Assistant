"""The 360° overview's by-name meetings, for a person with no address on their card.

The last resort searches every calendar the account OWNS, like the card itself
(owner rule 2026-11-15): it used to ask ``primary`` alone, so a meeting in the
named calendar events are created in was never found by name.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.active_client import ClientUnavailable
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.relations.overview import fallback

pytestmark = pytest.mark.unit

USER = uuid4()
SOON = datetime.now(UTC) + timedelta(days=1)


def _event(event_id: str, hours: int) -> dict[str, Any]:
    start = SOON + timedelta(hours=hours)
    return {
        "id": event_id,
        "summary": f"Lunch {event_id}",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
    }


def _calendars(held: dict[str, list[dict[str, Any]]], listing: list[dict[str, Any]]) -> Any:
    client = AsyncMock()
    client.list_calendars.return_value = {"items": listing, "truncated": False}

    async def search(**kwargs: Any) -> dict[str, Any]:
        return {"items": held.get(kwargs["calendar_id"], []), "truncated": False}

    client.list_events.side_effect = search
    return client


def _door(opened: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextlib.asynccontextmanager
    async def open_active_calendar(user_id: Any) -> AsyncIterator[Any]:
        assert user_id == USER
        yield opened

    monkeypatch.setattr(fallback, "open_active_calendar", open_active_calendar)


async def test_every_owned_calendar_is_searched_soonest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _calendars(
        {
            "famille": [_event("booked", 5), _event("both", 1)],
            "moi@x.com": [_event("invited", 2), _event("both", 1)],
            "voisin@x.com": [_event("theirs", 0)],
        },
        [
            {"id": "moi@x.com", "accessRole": "owner", "primary": True},
            {"id": "famille", "accessRole": "owner"},
            {"id": "voisin@x.com", "accessRole": "writer"},
        ],
    )
    _door(CalendarAccess(client, "famille", "google_calendar"), monkeypatch)

    found = await fallback.fetch_upcoming_events(USER, "Heidi")

    assert [row["title"] for row in found or []] == ["Lunch both", "Lunch invited", "Lunch booked"]
    searched = [call.kwargs for call in client.list_events.await_args_list]
    assert [kwargs["calendar_id"] for kwargs in searched] == ["famille", "moi@x.com"]
    assert {kwargs["query"] for kwargs in searched} == {"Heidi"}


async def test_only_the_soonest_are_kept_across_calendars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = fallback._UPCOMING_EVENTS_LIMIT
    client = _calendars(
        {
            "famille": [_event(f"f{index}", 2 * index + 1) for index in range(limit)],
            "moi@x.com": [_event(f"m{index}", 2 * index) for index in range(limit)],
        },
        [
            {"id": "moi@x.com", "accessRole": "owner", "primary": True},
            {"id": "famille", "accessRole": "owner"},
        ],
    )
    _door(CalendarAccess(client, "famille", "google_calendar"), monkeypatch)

    found = await fallback.fetch_upcoming_events(USER, "Heidi") or []

    assert len(found) == limit
    assert found[0]["title"] == "Lunch m0"


async def test_no_usable_calendar_is_no_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    _door(ClientUnavailable.NO_CONNECTOR, monkeypatch)

    assert await fallback.fetch_upcoming_events(USER, "Heidi") is None
