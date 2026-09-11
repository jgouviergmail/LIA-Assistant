"""The busy guard's ONE calendar read answers two questions.

« Are they in a meeting? » (ADR-281) and, since 2026-09-11, « does an event
of theirs start soon? » — the second lets the learned-rhythm tick scoring
(ADR-214 §11.2) step aside for a departure advice or a meeting reminder
instead of deferring the whole day to an evening window. Same read, same
cache, same consultation rule: a cache hit opens nothing.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.moments import busy_gate
from src.domains.moments.busy import next_event_start

pytestmark = pytest.mark.unit

_MODULE = "src.domains.moments.busy_gate"
NOW = datetime(2026, 9, 11, 14, 30, tzinfo=UTC)
ME = "moi@example.com"


def _event(start: datetime, *, minutes: int = 60, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"evt-{start.isoformat()}",
        "summary": "Rendez-vous",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat()},
        **extra,
    }


class TestNextEventStart:
    def test_earliest_future_start_wins(self) -> None:
        events = [
            _event(NOW + timedelta(hours=3)),
            _event(NOW + timedelta(minutes=40)),
            _event(NOW - timedelta(hours=1)),  # already started: not "next"
        ]
        assert next_event_start(events, now=NOW, user_tz=ZoneInfo("UTC"), user_email=ME) == (
            NOW + timedelta(minutes=40)
        )

    def test_a_solo_appointment_counts(self) -> None:
        # The dentist has no attendees; it is exactly what a departure advice serves.
        events = [_event(NOW + timedelta(minutes=50))]
        assert next_event_start(events, now=NOW, user_tz=ZoneInfo("UTC"), user_email=ME) is not None

    def test_cancelled_all_day_and_declined_are_skipped(self) -> None:
        soon = NOW + timedelta(minutes=20)
        events = [
            _event(soon, status="cancelled"),
            {"id": "all-day", "start": {"date": "2026-09-11"}, "end": {"date": "2026-09-12"}},
            _event(
                soon,
                attendees=[{"email": ME, "responseStatus": "declined"}, {"email": "x@example.com"}],
            ),
            "not-a-mapping",
        ]
        assert next_event_start(events, now=NOW, user_tz=ZoneInfo("UTC"), user_email=ME) is None

    def test_no_event_is_none(self) -> None:
        assert next_event_start([], now=NOW, user_tz=ZoneInfo("UTC"), user_email=ME) is None


def _user() -> Any:
    return SimpleNamespace(id=uuid4(), email=ME, timezone="UTC")


def _db_ctx(user: Any) -> Any:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        session = MagicMock()
        session.get = AsyncMock(return_value=user)
        yield session

    return _ctx


def _calendar(items: list[dict[str, Any]]) -> Any:
    from contextlib import asynccontextmanager

    client = MagicMock()
    client.list_events = AsyncMock(return_value={"items": items})
    client.close = AsyncMock()

    @asynccontextmanager
    async def _open(_db: Any, _user_id: Any):
        yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

    return _open


def _redis(cached: Any = None) -> MagicMock:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=cached)
    redis.set = AsyncMock()
    return redis


async def _verdict(items: list[dict[str, Any]], *, cached: Any = None, enabled: bool = True) -> Any:
    user = _user()
    redis = _redis(cached)
    with (
        patch(f"{_MODULE}.get_db_context", new=_db_ctx(user)),
        patch(f"{_MODULE}.open_active_calendar", new=_calendar(items)),
        patch(f"{_MODULE}.get_redis_cache", new=AsyncMock(return_value=redis)),
        patch(f"{_MODULE}.record_surface_consultations", MagicMock()),
        patch.object(busy_gate.settings, "moments_busy_guard_enabled", enabled),
    ):
        verdict = await busy_gate.agenda_verdict(user.id, NOW)
    return verdict, redis


class TestWhatTheRegisterIsTold:
    """A live read is a consultation; an unreadable one is NAMED; a calendar
    nobody asked (no connector, cache served) records nothing."""

    async def _run(self, *, calendar: Any, cached: Any = None, surface: str = "heartbeat") -> Any:
        user = _user()
        recorded = MagicMock()
        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx(user)),
            patch(f"{_MODULE}.open_active_calendar", new=calendar),
            patch(f"{_MODULE}.get_redis_cache", new=AsyncMock(return_value=_redis(cached))),
            patch(f"{_MODULE}.record_surface_consultations", recorded),
            patch.object(busy_gate.settings, "moments_busy_guard_enabled", True),
        ):
            await busy_gate.agenda_verdict(user.id, NOW, surface=surface)
        return recorded

    async def test_a_live_read_is_filed_under_the_callers_surface(self) -> None:
        recorded = await self._run(calendar=_calendar([]), surface="interest")
        recorded.assert_called_once()
        kwargs = recorded.call_args.kwargs
        assert kwargs["surface"] == "interest"
        assert list(kwargs["opened"]) == ["calendar"]
        assert list(kwargs["failed"]) == []

    async def test_an_unreadable_calendar_is_named_never_silent(self) -> None:
        client = MagicMock()
        client.list_events = AsyncMock(side_effect=RuntimeError("provider down"))

        @asynccontextmanager
        async def _broken(_db: Any, _user_id: Any):
            yield CalendarAccess(client=client, calendar_id="primary", connector_type=None)

        recorded = await self._run(calendar=_broken)
        kwargs = recorded.call_args.kwargs
        assert list(kwargs["opened"]) == ["calendar"]
        assert list(kwargs["failed"]) == ["calendar"]

    async def test_no_connector_asks_nobody_and_records_nothing(self) -> None:
        from src.domains.connectors.calendar_access import CalendarUnavailable

        @asynccontextmanager
        async def _none(_db: Any, _user_id: Any):
            yield CalendarUnavailable.NO_CONNECTOR

        recorded = await self._run(calendar=_none)
        recorded.assert_not_called()

    async def test_a_cache_hit_records_nothing(self) -> None:
        cached = json.dumps({"busy": False, "next_start": None}).encode()
        recorded = await self._run(calendar=_calendar([]), cached=cached)
        recorded.assert_not_called()


class TestAgendaVerdict:
    async def test_carries_busy_and_the_next_start(self) -> None:
        in_progress = _event(
            NOW - timedelta(minutes=10),
            attendees=[{"email": ME}, {"email": "marc@example.com"}],
        )
        later = _event(NOW + timedelta(minutes=45))
        verdict, redis = await _verdict([in_progress, later])
        assert verdict == busy_gate.AgendaVerdict(busy=True, next_start=NOW + timedelta(minutes=45))
        stored = json.loads(redis.set.await_args.args[1])
        assert stored == {"busy": True, "next_start": (NOW + timedelta(minutes=45)).isoformat()}

    async def test_a_quiet_calendar(self) -> None:
        verdict, _ = await _verdict([])
        assert verdict == busy_gate.AgendaVerdict(busy=False, next_start=None)

    async def test_a_cached_json_verdict_is_read_back(self) -> None:
        cached = json.dumps({"busy": False, "next_start": (NOW + timedelta(hours=1)).isoformat()})
        verdict, redis = await _verdict([], cached=cached.encode())
        assert verdict == busy_gate.AgendaVerdict(busy=False, next_start=NOW + timedelta(hours=1))
        redis.set.assert_not_awaited()

    @pytest.mark.parametrize(("raw", "busy"), [(b"1", True), (b"0", False)])
    async def test_a_legacy_flag_still_reads(self, raw: bytes, busy: bool) -> None:
        verdict, _ = await _verdict([], cached=raw)
        assert verdict == busy_gate.AgendaVerdict(busy=busy, next_start=None)

    async def test_switch_off_is_no_verdict(self) -> None:
        verdict, redis = await _verdict([_event(NOW + timedelta(minutes=5))], enabled=False)
        assert verdict is None
        redis.get.assert_not_awaited()

    async def test_should_defer_for_meeting_is_the_busy_half(self) -> None:
        in_progress = _event(
            NOW - timedelta(minutes=10),
            attendees=[{"email": ME}, {"email": "marc@example.com"}],
        )
        user = _user()
        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx(user)),
            patch(f"{_MODULE}.open_active_calendar", new=_calendar([in_progress])),
            patch(f"{_MODULE}.get_redis_cache", new=AsyncMock(return_value=_redis())),
            patch(f"{_MODULE}.record_surface_consultations", MagicMock()),
            patch.object(busy_gate.settings, "moments_busy_guard_enabled", True),
        ):
            assert await busy_gate.should_defer_for_meeting(user.id, NOW) is True
