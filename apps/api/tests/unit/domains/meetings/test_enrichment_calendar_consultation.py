"""The meeting's calendar lookup is a consultation, and it is recorded (ADR-304).

It was filed as « not a read » on the strength of the geocoding half alone,
until making the calendar door count as a client import surfaced it: the job
opens the person's calendar to find the event a recording overlaps.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.active_client import ClientUnavailable
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.meetings import enrichment

pytestmark = pytest.mark.unit

STARTED = datetime(2026, 9, 22, 9, 0, tzinfo=UTC)
STOPPED = STARTED + timedelta(hours=1)


def _door(opened: object) -> Any:
    @contextlib.asynccontextmanager
    async def _open(_user_id: object) -> AsyncIterator[object]:
        yield opened

    return _open


def _access(list_events: AsyncMock) -> CalendarAccess:
    client = MagicMock()
    client.list_events = list_events
    return CalendarAccess(client=client, calendar_id="primary", connector_type="google_calendar")


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    monkeypatch.setattr(
        enrichment, "record_surface_consultations", lambda **kwargs: rows.append(kwargs)
    )
    return rows


async def _match(monkeypatch: pytest.MonkeyPatch, opened: object) -> Any:
    monkeypatch.setattr(
        "src.domains.connectors.calendar_access.open_active_calendar", _door(opened)
    )
    return await enrichment.match_calendar_event(
        user_id=uuid4(), started_at=STARTED, stopped_at=STOPPED
    )


async def test_a_calendar_read_is_filed_on_the_meeting_surface(
    monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    event = {
        "id": "evt-1",
        "summary": "Weekly",
        "start": {"dateTime": STARTED.isoformat()},
        "end": {"dateTime": STOPPED.isoformat()},
    }
    match = await _match(monkeypatch, _access(AsyncMock(return_value={"items": [event]})))

    assert match is not None and match.event_id == "evt-1"
    (row,) = recorded
    assert row["surface"] == "meeting"
    assert list(row["opened"]) == ["calendar"]
    assert list(row["failed"]) == []


async def test_a_calendar_that_could_not_be_read_is_filed_failed(
    monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    failing = AsyncMock(side_effect=httpx.ConnectError("down"))
    assert await _match(monkeypatch, _access(failing)) is None
    (row,) = recorded
    assert list(row["failed"]) == ["calendar"]


async def test_no_calendar_connected_opened_nothing_and_files_nothing(
    monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    assert await _match(monkeypatch, ClientUnavailable.NO_CONNECTOR) is None
    assert recorded == []


def test_the_surface_names_what_it_reads() -> None:
    from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

    surface = CONSULTATION_SURFACES["meeting"]
    assert surface.capabilities() == {"meeting:calendar": "event"}
