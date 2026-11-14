"""How late an occurrence of a time routine may still start (ADR-265 amendment 2026-11-12 b).

A due occurrence used to run however late the scheduler reached it: a morning
routine answered at 14:00 after an outage. It is now run late only inside a
catch-up window — half the gap to the occurrence that follows it, never more
than the operator's maximum — and given up past it.

What must hold, and why each matters:

- the window follows the routine's OWN rhythm: a routine every fifteen minutes
  is stale after a few minutes, a daily one after the maximum;
- an occurrence nothing follows is never given up: running it late is all that
  is left of what the person asked for;
- once an occurrence is given up, the routine re-arms on the most recent
  occurrence that may still start — an outage ending twenty minutes after
  today's slot serves TODAY — and never on one in between;
- every instant is computed on the routine's local calendar: the cases run in
  a zone far from UTC, on a day that is not the UTC day.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay
from src.domains.scheduled_actions.models import TriggerKind
from src.domains.scheduled_actions.trigger import TriggerPlan

pytestmark = pytest.mark.unit

#: UTC+13 in November: 08:00 there is 19:00 UTC of the PREVIOUS day.
AUCKLAND = "Pacific/Auckland"
_ZONE = ZoneInfo(AUCKLAND)


def _local(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    """A wall time of November 2026 in Auckland, as the UTC instant it is."""
    return datetime(2026, 11, day, hour, minute, second, tzinfo=_ZONE).astimezone(UTC)


def _daily(*, end: SeriesEnd | None = None) -> RecurrenceSpec:
    return RecurrenceSpec(
        freq="daily",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
        anchor_date=date(2026, 11, 1),
        **({"end": end} if end is not None else {}),
    )


def _every(step_minutes: int) -> RecurrenceSpec:
    return RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=step_minutes,
            start=TimeOfDay(hour=6, minute=0),
            end=TimeOfDay(hour=22, minute=0),
        ),
        anchor_date=date(2026, 11, 1),
    )


def _plan(recurrence: RecurrenceSpec | None, **over: Any) -> TriggerPlan:
    base: dict[str, Any] = {
        "action_id": uuid.UUID("00000000-0000-4000-8000-000000000006"),
        "trigger_kind": TriggerKind.TIME.value,
        "recurrence": recurrence,
        "condition_config": None,
        "timezone": AUCKLAND,
    }
    return TriggerPlan(**{**base, **over})


@pytest.fixture(autouse=True)
def _two_hours_at_most(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cases state their own maximum: the default is the operator's to move."""
    monkeypatch.setattr(settings, "scheduled_actions_catch_up_max_minutes", 120)


class TestTheWindowFollowsTheRoutinesRhythm:
    def test_a_daily_occurrence_may_start_until_the_maximum(self) -> None:
        due = _local(12, 8)

        assert _plan(_daily()).catch_up_deadline(due) == due + timedelta(minutes=120)

    @pytest.mark.parametrize(("step", "window_seconds"), [(60, 1800), (15, 450), (5, 150)])
    def test_a_frequent_occurrence_is_stale_after_half_its_period(
        self, step: int, window_seconds: int
    ) -> None:
        due = _local(12, 9)

        deadline = _plan(_every(step)).catch_up_deadline(due)

        assert deadline == due + timedelta(seconds=window_seconds)

    def test_the_gap_is_the_one_to_the_occurrence_that_follows(self) -> None:
        """08:00 then 08:10 then nothing until tomorrow: the first is stale in
        five minutes, the second only at the maximum."""
        spec = RecurrenceSpec(
            freq="daily",
            times=DailyTimes(
                mode="at", at=(TimeOfDay(hour=8, minute=0), TimeOfDay(hour=8, minute=10))
            ),
            anchor_date=date(2026, 11, 1),
        )
        plan = _plan(spec)

        assert plan.catch_up_deadline(_local(12, 8)) == _local(12, 8, 5)
        assert plan.catch_up_deadline(_local(12, 8, 10)) == _local(12, 10, 10)

    def test_the_operator_s_maximum_is_read_at_each_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        due = _local(12, 8)
        monkeypatch.setattr(settings, "scheduled_actions_catch_up_max_minutes", 30)

        assert _plan(_daily()).catch_up_deadline(due) == due + timedelta(minutes=30)

    def test_an_occurrence_nothing_follows_is_never_given_up(self) -> None:
        last = _daily(end=SeriesEnd(kind="on_date", on_date=date(2026, 11, 12)))

        assert _plan(last).catch_up_deadline(_local(12, 8)) is None

    def test_a_condition_routine_has_no_occurrence_to_be_late_for(self) -> None:
        watch = _plan(
            None,
            trigger_kind=TriggerKind.CONDITION.value,
            condition_config={"type": "mail_match", "query": "invoice"},
        )

        assert watch.catch_up_deadline(_local(12, 8)) is None
        assert watch.retry_deadline(_local(12, 8)) is None

    def test_a_schedule_without_recurrence_has_none_either(self) -> None:
        assert _plan(None).catch_up_deadline(_local(12, 8)) is None
        assert _plan(None).retry_deadline(_local(12, 8)) is None


class TestHowLongABusyAccountIsWaitedFor:
    def test_as_long_as_the_occurrence_may_still_start(self) -> None:
        due = _local(12, 9)
        plan = _plan(_every(60))

        assert plan.retry_deadline(due) == plan.catch_up_deadline(due)

    def test_the_last_occurrence_of_a_series_is_waited_for_the_maximum(self) -> None:
        """Never given up for lateness, but an account busy for hours is not a
        turn under way: the wait is bounded all the same."""
        last = _daily(end=SeriesEnd(kind="on_date", on_date=date(2026, 11, 12)))
        due = _local(12, 8)

        assert _plan(last).retry_deadline(due) == due + timedelta(minutes=120)


class TestWhatIsArmedOnceAnOccurrenceIsGivenUp:
    def test_an_outage_ending_after_today_s_slot_serves_today(self) -> None:
        """Yesterday's occurrence is gone; today's is twenty minutes old."""
        plan = _plan(_daily())

        armed = plan.after_missed(due_at=_local(11, 8), now=_local(12, 8, 20))

        assert armed == _local(12, 8)

    def test_a_slot_itself_too_old_is_not_armed(self) -> None:
        plan = _plan(_daily())

        armed = plan.after_missed(due_at=_local(11, 8), now=_local(12, 14))

        assert armed == _local(13, 8)

    def test_the_most_recent_occurrence_is_the_only_candidate(self) -> None:
        """Six hourly occurrences passed during the outage: the one thirty
        seconds old is served, none of the five before it."""
        plan = _plan(_every(60))

        armed = plan.after_missed(due_at=_local(12, 8), now=_local(12, 14, 0, 30))

        assert armed == _local(12, 14)

    def test_past_its_own_window_the_most_recent_one_is_skipped_too(self) -> None:
        plan = _plan(_every(60))

        armed = plan.after_missed(due_at=_local(12, 8), now=_local(12, 14, 45))

        assert armed == _local(12, 15)

    def test_the_occurrence_given_up_is_never_armed_again(self) -> None:
        """No other occurrence has come since: the next one is ahead."""
        plan = _plan(_every(60))

        armed = plan.after_missed(due_at=_local(12, 14), now=_local(12, 14, 40))

        assert armed == _local(12, 15)

    def test_the_last_occurrence_of_a_series_is_armed_however_late(self) -> None:
        """Nothing follows it, so it is never given up — two days after it too."""
        series = _daily(end=SeriesEnd(kind="on_date", on_date=date(2026, 11, 12)))
        plan = _plan(series)

        armed = plan.after_missed(due_at=_local(10, 8), now=_local(14, 16))

        assert armed == _local(12, 8)

    def test_a_series_with_nothing_left_arms_nothing(self) -> None:
        series = _daily(end=SeriesEnd(kind="on_date", on_date=date(2026, 11, 11)))
        plan = _plan(series)

        assert plan.after_missed(due_at=_local(11, 8), now=_local(12, 16)) is None


class TestTheOccurrenceATickWasDueFor:
    def test_a_due_tick_carries_the_bounds_of_its_occurrence(self) -> None:
        plan = _plan(_every(60))
        due = _local(12, 9)

        occurrence = plan.due_occurrence(due_at=due, started_at=due + timedelta(seconds=5))

        assert occurrence is not None
        assert (occurrence.at, occurrence.late_after, occurrence.retry_until) == (
            due,
            due + timedelta(minutes=30),
            due + timedelta(minutes=30),
        )

    def test_it_is_late_only_past_its_deadline(self) -> None:
        plan = _plan(_every(60))
        due = _local(12, 9)
        occurrence = plan.due_occurrence(due_at=due, started_at=due)
        assert occurrence is not None

        assert occurrence.is_late(due + timedelta(minutes=30)) is False
        assert occurrence.is_late(due + timedelta(minutes=30, seconds=1)) is True

    def test_the_last_occurrence_of_a_series_is_never_late(self) -> None:
        last = _daily(end=SeriesEnd(kind="on_date", on_date=date(2026, 11, 12)))
        due = _local(12, 8)
        occurrence = _plan(last).due_occurrence(due_at=due, started_at=due + timedelta(days=3))
        assert occurrence is not None

        assert occurrence.is_late(due + timedelta(days=3)) is False

    def test_a_run_started_ahead_of_its_slot_was_due_for_nothing(self) -> None:
        plan = _plan(_daily())
        ahead = _local(12, 8)

        assert plan.due_occurrence(due_at=ahead, started_at=ahead - timedelta(hours=1)) is None
        assert plan.due_occurrence(due_at=None, started_at=ahead) is None

    def test_a_watch_is_due_for_no_occurrence(self) -> None:
        watch = _plan(
            None,
            trigger_kind=TriggerKind.CONDITION.value,
            condition_config={"type": "mail_match", "query": "invoice"},
        )
        due = _local(12, 8)

        assert watch.due_occurrence(due_at=due, started_at=due) is None
