"""Deterministic tick scoring — defer proactive ticks toward learned windows.

Plan §11.2, implemented behind its own OFF-by-default flag. The invariants
under test (ADR-214 decision 4):

- the learned rhythm PRIORITIZES, it never widens: a deferred tick requires
  a remaining same-day opportunity inside a learned window AND inside the
  user's configured bounds — empty intersection → behavior identical;
- anti-starvation: once the last learned window of the day has passed (or
  cannot fit one more tick before the bounds close), ticks flow normally;
- fail-open everywhere: no flag, no profile, no windows verdict, storage
  error → never defer, never block the tick pipeline.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.habits.rhythm import ClaimedWindow
from src.domains.heartbeat.habit_context import (
    should_defer_tick,
    should_defer_tick_for_rhythm,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


def _local(hour: int, minute: int = 0, *, day: int = 3) -> datetime:
    """2026-08-03 is a Monday; day=1 (Saturday 2026-08-01) for weekend cases."""
    return datetime(2026, 8, day, hour, minute, tzinfo=PARIS)


def _win(start: int, end: int) -> ClaimedWindow:
    return ClaimedWindow(start_hour=start, end_hour=end, presence=0.9)


class TestShouldDeferTick:
    """Pure rule, table-driven — the geometry cases."""

    @pytest.mark.parametrize(
        ("hour", "minute", "windows", "start", "end", "expected"),
        [
            # Inside a learned window → send now, never defer.
            (8, 30, [(8, 10)], 9, 22, False),
            # Before the window with room inside the bounds → defer.
            (10, 0, [(18, 20)], 9, 22, True),
            # After the last window of the day → anti-starvation, send.
            (21, 0, [(8, 10), (18, 20)], 9, 22, False),
            # Window opens exactly at the bounds' close → no tick fits, send.
            (10, 0, [(22, 23)], 9, 22, False),
            # Window opens too close to the close for one more tick → send.
            (10, 0, [(21, 23)], 9, 21, False),
            # Two windows, the first passed, the second still ahead → defer.
            (12, 0, [(8, 10), (18, 20)], 9, 22, True),
            # No learned windows → behavior identical.
            (10, 0, [], 9, 22, False),
            # Midnight-wrapping learned window: 22-01 is a future entry today.
            (18, 0, [(22, 1)], 9, 23, True),
            # Midnight-wrapping USER bounds (22→6): conservative same-day
            # ceiling (24h) — a 23h window entry stays reachable.
            (22, 10, [(23, 0)], 22, 6, True),
            # Inside a midnight-wrapping learned window at 00:30 → send.
            (0, 30, [(22, 1)], 0, 24, False),
        ],
    )
    def test_geometry(
        self,
        hour: int,
        minute: int,
        windows: list[tuple[int, int]],
        start: int,
        end: int,
        expected: bool,
    ) -> None:
        assert (
            should_defer_tick(
                _local(hour, minute),
                tuple(_win(s, e) for s, e in windows),
                notify_end_hour=end,
                notify_start_hour=start,
                tick_interval_minutes=15,
            )
            is expected
        )


def _settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "habits_tick_scoring_enabled": True,
        "habits_enabled": True,
        "heartbeat_notification_interval_minutes": 15,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _profile_payload(verdict: str = "windows", windows: list[dict] | None = None) -> dict:
    cls = {
        "verdict": verdict,
        "windows": (
            windows
            if windows is not None
            else [{"start_hour": 18, "end_hour": 20, "presence": 0.9}]
        ),
        "n_eff": 20.0,
        "bin_presence": [0.0] * 24,
    }
    return {
        "version": 1,
        "active_days_fraction": 0.8,
        "sparse": False,
        "classes": {"weekday": cls, "weekend": cls},
    }


def _user_settings(**overrides: Any) -> dict:
    base = {
        "timezone": "Europe/Paris",
        "habits_enabled": True,
        "heartbeat_notify_start_hour": 9,
        "heartbeat_notify_end_hour": 22,
    }
    base.update(overrides)
    return base


def _patch_profile(payload: dict | None) -> Any:
    row = None if payload is None else MagicMock(payload=payload)
    repo = MagicMock()
    repo.get_profile = AsyncMock(return_value=row)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=MagicMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    return (
        patch("src.infrastructure.database.get_db_context", MagicMock(return_value=ctx)),
        patch("src.domains.heartbeat.habit_context.HabitsRepository", MagicMock(return_value=repo)),
    )


def _patch_now(hour: int, *, day: int = 3) -> Any:
    return patch(
        "src.domains.heartbeat.habit_context.now_in_timezone",
        MagicMock(return_value=_local(hour, day=day)),
    )


class TestShouldDeferTickForRhythm:
    """The async gate: flags, preference, profile state, fail-open."""

    async def test_defers_before_the_learned_evening_window(self) -> None:
        p1, p2 = _patch_profile(_profile_payload())
        with p1, p2, _patch_now(10):
            assert (
                await should_defer_tick_for_rhythm(uuid4(), _user_settings(), _settings()) is True
            )

    async def test_scoring_flag_off_never_defers_and_never_fetches(self) -> None:
        p1, p2 = _patch_profile(_profile_payload())
        with p1 as ctx_mock, p2, _patch_now(10):
            result = await should_defer_tick_for_rhythm(
                uuid4(), _user_settings(), _settings(habits_tick_scoring_enabled=False)
            )
        assert result is False
        ctx_mock.assert_not_called()  # no DB round-trip when the flag is off

    async def test_user_preference_off_never_defers(self) -> None:
        p1, p2 = _patch_profile(_profile_payload())
        with p1, p2, _patch_now(10):
            assert (
                await should_defer_tick_for_rhythm(
                    uuid4(), _user_settings(habits_enabled=False), _settings()
                )
                is False
            )

    @pytest.mark.parametrize("verdict", ["none", "sparse", "diffuse", "insufficient"])
    async def test_non_window_verdicts_never_defer(self, verdict: str) -> None:
        p1, p2 = _patch_profile(_profile_payload(verdict=verdict))
        with p1, p2, _patch_now(10):
            assert (
                await should_defer_tick_for_rhythm(uuid4(), _user_settings(), _settings()) is False
            )

    async def test_missing_profile_never_defers(self) -> None:
        p1, p2 = _patch_profile(None)
        with p1, p2, _patch_now(10):
            assert (
                await should_defer_tick_for_rhythm(uuid4(), _user_settings(), _settings()) is False
            )

    async def test_weekend_uses_the_weekend_class(self) -> None:
        payload = _profile_payload()
        payload["classes"]["weekend"] = {
            "verdict": "none",
            "windows": [],
            "n_eff": 4.0,
            "bin_presence": [0.0] * 24,
        }
        p1, p2 = _patch_profile(payload)
        # Saturday 10:00 — weekday windows exist but the WEEKEND class says
        # none: deferring on the weekday rhythm would be someone else's habit.
        with p1, p2, _patch_now(10, day=1):
            assert (
                await should_defer_tick_for_rhythm(uuid4(), _user_settings(), _settings()) is False
            )

    async def test_midnight_start_bound_is_a_valid_bound(self) -> None:
        """Hour 0 is a VALID configured bound (code-review catch: an `or`
        fallback read midnight as absent, replaced 0 with 9, mis-detected the
        bounds as wrapping and deferred toward a window OUTSIDE the user's
        bounds — the exact starvation the invariant forbids)."""
        p1, p2 = _patch_profile(
            _profile_payload(windows=[{"start_hour": 10, "end_hour": 12, "presence": 0.9}])
        )
        # Night-shift bounds 0→8; the learned 10-12 window is OUT of bounds:
        # a 01:00 tick must flow normally, never defer toward the unreachable.
        with p1, p2, _patch_now(1):
            assert (
                await should_defer_tick_for_rhythm(
                    uuid4(),
                    _user_settings(heartbeat_notify_start_hour=0, heartbeat_notify_end_hour=8),
                    _settings(),
                )
                is False
            )

    async def test_storage_error_fails_open(self) -> None:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        with (
            patch("src.infrastructure.database.get_db_context", MagicMock(return_value=ctx)),
            _patch_now(10),
        ):
            assert (
                await should_defer_tick_for_rhythm(uuid4(), _user_settings(), _settings()) is False
            )


class TestCheckEligibilityIntegration:
    """The task hook: a deferred tick answers False (skip), everything else
    keeps the existing enabled-flag behavior."""

    async def test_deferred_tick_fails_task_eligibility(self) -> None:
        from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask

        task = HeartbeatProactiveTask()
        with patch(
            "src.domains.heartbeat.proactive_task.should_defer_tick_for_rhythm",
            AsyncMock(return_value=True),
        ):
            assert (
                await task.check_eligibility(
                    uuid4(), {"heartbeat_enabled": True}, datetime.now(PARIS)
                )
                is False
            )

    async def test_normal_tick_stays_eligible(self) -> None:
        from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask

        task = HeartbeatProactiveTask()
        with patch(
            "src.domains.heartbeat.proactive_task.should_defer_tick_for_rhythm",
            AsyncMock(return_value=False),
        ):
            assert (
                await task.check_eligibility(
                    uuid4(), {"heartbeat_enabled": True}, datetime.now(PARIS)
                )
                is True
            )

    async def test_heartbeat_disabled_short_circuits_before_scoring(self) -> None:
        from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask

        task = HeartbeatProactiveTask()
        scoring = AsyncMock(return_value=True)
        with patch("src.domains.heartbeat.proactive_task.should_defer_tick_for_rhythm", scoring):
            assert (
                await task.check_eligibility(
                    uuid4(), {"heartbeat_enabled": False}, datetime.now(PARIS)
                )
                is False
            )
        scoring.assert_not_awaited()
