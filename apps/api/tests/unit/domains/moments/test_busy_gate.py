"""Deferring a tick because the person is in a meeting — and what that costs.

Three properties, each a decision:

- **fail-open in full.** Not knowing whether someone is busy is not a reason to
  stay silent, and certainly not a reason to take a tick down. Every failure
  path answers « not busy ».
- **a cache hit is not a consultation.** Redis answered; the calendar was never
  opened. Recording one would be a false claim in a register whose whole promise
  is « exact or absent ».
- **a live read IS one**, and it is recorded even though the tick then goes on to
  say nothing — the person's calendar was opened on LIA's own initiative, which
  is precisely what the register exists to show.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.calendar_access import CalendarAccess, CalendarUnavailable
from src.domains.moments import busy_gate

pytestmark = pytest.mark.unit

_MODULE = "src.domains.moments.busy_gate"
NOW = datetime(2026, 9, 11, 14, 30, tzinfo=UTC)
ME = "moi@example.com"


def _user() -> Any:
    return SimpleNamespace(id=uuid4(), email=ME, timezone="UTC")


def _meeting_now() -> dict[str, Any]:
    start = NOW - timedelta(minutes=10)
    return {
        "id": "evt-1",
        "summary": "Point budget",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        "attendees": [{"email": ME}, {"email": "marc@example.com"}],
    }


def _db_ctx(user: Any) -> Any:
    """A session whose ``get`` hands back the account the guard looks up."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        session = MagicMock()
        session.get = AsyncMock(return_value=user)
        yield session

    return _ctx


def _calendar(items: list[dict[str, Any]] | Exception) -> Any:
    from contextlib import asynccontextmanager

    client = MagicMock()
    if isinstance(items, Exception):
        client.list_events = AsyncMock(side_effect=items)
    else:
        client.list_events = AsyncMock(return_value={"items": items})
    client.close = AsyncMock()

    @asynccontextmanager
    async def _open(_db: Any, _user_id: Any):
        yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

    return _open


def _no_calendar() -> Any:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _open(_db: Any, _user_id: Any):
        yield CalendarUnavailable.NO_CONNECTOR

    return _open


def _redis(cached: Any = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    return redis


async def _ask(
    items: Any,
    *,
    cached: Any = None,
    opener: Any = None,
    enabled: bool = True,
    recorder: Any = None,
) -> bool:
    user = _user()
    with (
        patch(f"{_MODULE}.get_db_context", new=_db_ctx(user)),
        patch(f"{_MODULE}.open_active_calendar", new=opener or _calendar(items)),
        patch(f"{_MODULE}.get_redis_cache", new=AsyncMock(return_value=_redis(cached))),
        patch(f"{_MODULE}.record_surface_consultations", recorder or MagicMock()),
        patch.object(busy_gate.settings, "moments_busy_guard_enabled", enabled),
    ):
        return await busy_gate.should_defer_for_meeting(user.id, NOW)


class TestTheVerdict:
    async def test_a_meeting_in_progress_defers_the_tick(self) -> None:
        assert await _ask([_meeting_now()]) is True

    async def test_an_empty_calendar_does_not(self) -> None:
        assert await _ask([]) is False

    async def test_the_switch_being_off_skips_the_read_entirely(self) -> None:
        """Off means off: no verdict, and no calendar call to reach it."""
        opener = _calendar([_meeting_now()])
        assert await _ask([], opener=opener, enabled=False) is False


class TestItFailsOpen:
    async def test_no_calendar_connector(self) -> None:
        assert await _ask([], opener=_no_calendar()) is False

    async def test_a_provider_failure(self) -> None:
        assert await _ask(RuntimeError("calendar down")) is False

    async def test_a_redis_failure(self) -> None:
        user = _user()
        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx(user)),
            patch(f"{_MODULE}.open_active_calendar", new=_calendar([_meeting_now()])),
            patch(f"{_MODULE}.get_redis_cache", new=AsyncMock(side_effect=RuntimeError("gone"))),
            patch(f"{_MODULE}.record_surface_consultations", MagicMock()),
            patch.object(busy_gate.settings, "moments_busy_guard_enabled", True),
        ):
            # Redis is a cache, not the answer: losing it must not lose the
            # verdict, and must not deliver a wrong one either.
            assert await busy_gate.should_defer_for_meeting(user.id, NOW) is True


class TestTheRegister:
    async def test_a_live_read_is_recorded(self) -> None:
        """The calendar was opened on LIA's own initiative, and nobody was
        watching — recording it is the whole point of the register."""
        recorder = MagicMock()

        await _ask([_meeting_now()], recorder=recorder)

        assert recorder.called
        assert recorder.call_args.kwargs["opened"] == ["calendar"]

    async def test_a_cache_hit_is_not_a_consultation(self) -> None:
        """Redis answered; the mailbox was never opened."""
        recorder = MagicMock()

        await _ask([], cached=b"1", recorder=recorder)

        assert not recorder.called

    async def test_a_cached_verdict_is_obeyed_without_a_call(self) -> None:
        opener = _calendar([])

        assert await _ask([], cached=b"1", opener=opener) is True

    async def test_a_failed_read_is_recorded_as_failed_not_as_silence(self) -> None:
        """A blind source is named, never read as « nothing there ».

        The section must be in ``opened`` AS WELL: the recorder files one row
        per opened section and reads ``failed`` as a subset of them, so the
        first version of this test — ``opened == []`` — pinned exactly the
        silence its title refuses (cold review, 2026-09-11).
        """
        recorder = MagicMock()

        await _ask(RuntimeError("calendar down"), recorder=recorder)

        assert recorder.call_args.kwargs["failed"] == ["calendar"]
        assert recorder.call_args.kwargs["opened"] == ["calendar"]
