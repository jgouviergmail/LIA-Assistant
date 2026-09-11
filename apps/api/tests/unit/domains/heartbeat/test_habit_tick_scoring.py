"""The heartbeat task's use of the tick scoring (ADR-214 §11.2).

The rule itself is tested where it lives, ``tests/unit/domains/habits/
test_tick_scoring.py``. What stays here is the HOOK — a deferred tick answers
False (skip), everything else keeps the enabled-flag behaviour — and the pin
that keeps the sweep's declared :class:`TickSurface` on the same fields and
fallbacks as its ``EligibilityChecker``: two declarations of one window, and
the scoring would defer toward bounds the checker never applies.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


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

    async def test_the_scoring_is_asked_with_the_heartbeats_own_surface(self) -> None:
        from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask

        task = HeartbeatProactiveTask()
        scoring = AsyncMock(return_value=False)
        with patch("src.domains.heartbeat.proactive_task.should_defer_tick_for_rhythm", scoring):
            await task.check_eligibility(uuid4(), {"heartbeat_enabled": True}, datetime.now(PARIS))
        assert scoring.await_args.kwargs["surface"] is task.tick_surface


class TestTickSurfacePinnedToTheChecker:
    """One window, declared twice, read by two rules — pinned so they agree."""

    def test_fields_and_fallbacks_match_the_eligibility_checker(self) -> None:
        from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
        from src.infrastructure.scheduler.heartbeat_notification import (
            _create_heartbeat_eligibility_checker,
        )

        checker = _create_heartbeat_eligibility_checker()
        surface = HeartbeatProactiveTask.tick_surface
        assert surface.task_type == checker.task_type
        assert surface.start_hour_field == checker.start_hour_field
        assert surface.end_hour_field == checker.end_hour_field
        assert surface.default_start_hour == checker.default_start_hour
        assert surface.default_end_hour == checker.default_end_hour

    def test_the_period_setting_is_the_checkers_interval(self) -> None:
        from src.core.config import settings
        from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
        from src.infrastructure.scheduler.heartbeat_notification import (
            _create_heartbeat_eligibility_checker,
        )

        surface = HeartbeatProactiveTask.tick_surface
        assert (
            getattr(settings, surface.interval_setting)
            == _create_heartbeat_eligibility_checker().interval_minutes
        )
