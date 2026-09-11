"""The interest sweep stands aside for a meeting and for the learned rhythm.

A11 (2026-09-11): the two « not now » gates the heartbeat tick applies were
the heartbeat's alone, while the interest sweep interrupts the same person
on its own schedule — measured, an interest notification could land in the
middle of a meeting the heartbeat had just stood aside for. Both gates fail
open; the interests_enabled refusal still comes first and costs no read.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.interests.proactive_task import InterestProactiveTask
from src.domains.moments.busy_gate import AgendaVerdict

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 8, 3, 10, 0, tzinfo=PARIS)
_VERDICT = "src.domains.interests.proactive_task.agenda_verdict"
_DEFER = "src.domains.interests.proactive_task.should_defer_tick_for_rhythm"


def _settings(**overrides: object) -> dict:
    base = {"interests_enabled": True, "timezone": "Europe/Paris"}
    base.update(overrides)
    return base


class TestInterestEligibilityGates:
    async def test_disabled_costs_no_calendar_read(self) -> None:
        verdict = AsyncMock(return_value=None)
        with patch(_VERDICT, verdict):
            assert (
                await InterestProactiveTask().check_eligibility(
                    uuid4(), _settings(interests_enabled=False), NOW
                )
                is False
            )
        verdict.assert_not_awaited()

    async def test_a_meeting_in_progress_stands_the_sweep_aside(self) -> None:
        from src.infrastructure.observability.metrics_habits import (
            heartbeat_ticks_deferred_total,
        )

        before = heartbeat_ticks_deferred_total.labels(
            task_type="interest", day_class="unknown", reason="in_meeting"
        )._value.get()
        defer = AsyncMock(return_value=False)
        with (
            patch(_VERDICT, AsyncMock(return_value=AgendaVerdict(busy=True, next_start=None))),
            patch(_DEFER, defer),
        ):
            assert (
                await InterestProactiveTask().check_eligibility(uuid4(), _settings(), NOW) is False
            )
        defer.assert_not_awaited()
        after = heartbeat_ticks_deferred_total.labels(
            task_type="interest", day_class="unknown", reason="in_meeting"
        )._value.get()
        assert after == before + 1

    async def test_the_calendar_read_is_filed_under_the_interest_surface(self) -> None:
        verdict = AsyncMock(return_value=None)
        with patch(_VERDICT, verdict), patch(_DEFER, AsyncMock(return_value=False)):
            await InterestProactiveTask().check_eligibility(uuid4(), _settings(), NOW)
        assert verdict.await_args.kwargs["surface"] == "interest"

    async def test_the_rhythm_is_asked_with_the_sweeps_surface_and_the_next_event(self) -> None:
        soon = NOW + timedelta(minutes=40)
        defer = AsyncMock(return_value=True)
        with (
            patch(_VERDICT, AsyncMock(return_value=AgendaVerdict(busy=False, next_start=soon))),
            patch(_DEFER, defer),
        ):
            assert (
                await InterestProactiveTask().check_eligibility(uuid4(), _settings(), NOW) is False
            )
        assert defer.await_args.kwargs["surface"] is InterestProactiveTask.tick_surface
        assert defer.await_args.kwargs["imminent_event_at"] == soon

    async def test_no_verdict_and_no_deferral_keeps_the_sweep_eligible(self) -> None:
        with (
            patch(_VERDICT, AsyncMock(return_value=None)),
            patch(_DEFER, AsyncMock(return_value=False)),
        ):
            assert (
                await InterestProactiveTask().check_eligibility(uuid4(), _settings(), NOW) is True
            )


class TestTickSurfacePinnedToTheChecker:
    """One window, declared twice, read by two rules — pinned so they agree."""

    def test_fields_and_fallbacks_match_the_eligibility_checker(self) -> None:
        from src.infrastructure.scheduler.interest_notification import (
            _create_interest_eligibility_checker,
        )

        checker = _create_interest_eligibility_checker()
        surface = InterestProactiveTask.tick_surface
        assert surface.task_type == checker.task_type
        assert surface.start_hour_field == checker.start_hour_field
        assert surface.end_hour_field == checker.end_hour_field
        assert surface.default_start_hour == checker.default_start_hour
        assert surface.default_end_hour == checker.default_end_hour

    def test_the_period_setting_is_the_checkers_interval(self) -> None:
        from src.core.config import settings
        from src.infrastructure.scheduler.interest_notification import (
            _create_interest_eligibility_checker,
        )

        surface = InterestProactiveTask.tick_surface
        assert (
            getattr(settings, surface.interval_setting)
            == _create_interest_eligibility_checker().interval_minutes
        )

    def test_the_calendar_section_is_declared_on_the_interest_surface(self) -> None:
        """The busy guard files a LIVE calendar read under the sweep's surface:
        a section the vocabulary does not carry is a row nobody can read."""
        from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

        assert CONSULTATION_SURFACES["interest"].domains["calendar"] == "event"
