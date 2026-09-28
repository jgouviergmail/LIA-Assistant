"""When a routine next needs the executor — one answer for both kinds (ADR-322).

A TIME routine follows its own recurrence. A CONDITION routine has none: the
system checks it at a cadence declared per condition type, phase-shifted by the
routine's id, until the optional last day it watches.

What must hold, and why each matters:

- the cadence table covers EXACTLY the condition vocabulary and every setting
  it names exists — a misspelled attribute would fail at the first check, in a
  background job, rather than at boot (ADR-085);
- a check is never faster than the cache its source reads through — a faster
  one re-reads Redis and would file a consultation for a read that never
  happened;
- checks are phase-shifted per routine and never drift: twenty watches created
  in the same minute must not hit the same mailbox provider in the same second
  forever (the jitter rule, applied to rows rather than jobs);
- the watch ends at the END of its last local day, whatever the clock does.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.config import settings
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay, describe
from src.domains.scheduled_actions.models import CONDITION_TYPES, TriggerKind
from src.domains.scheduled_actions.trigger import (
    CONDITION_CHECKS,
    TriggerPlan,
    check_interval,
    check_minutes,
    condition_until,
    next_check,
    schedule_sentence,
    watch_end,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 25, 12, 3, 17, tzinfo=UTC)


def _weekly_at_eight() -> RecurrenceSpec:
    return RecurrenceSpec(
        freq="weekly",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
        anchor_date=date(2026, 1, 5),
        byweekday=(1, 2, 3, 4, 5, 6, 7),
    )


def _plan(**over: Any) -> TriggerPlan:
    base: dict[str, Any] = {
        "action_id": uuid.UUID("00000000-0000-4000-8000-000000000001"),
        "trigger_kind": TriggerKind.CONDITION.value,
        "recurrence": None,
        "condition_config": {"type": "mail_match", "query": "devis"},
        "timezone": "Europe/Paris",
    }
    base.update(over)
    return TriggerPlan(**base)


class TestTheCadenceTable:
    """Declared once, complete, and pointing at settings that exist."""

    def test_it_covers_exactly_the_condition_vocabulary(self) -> None:
        assert set(CONDITION_CHECKS) == set(CONDITION_TYPES)

    def test_every_setting_it_names_exists(self) -> None:
        for condition_type, check in CONDITION_CHECKS.items():
            assert isinstance(getattr(settings, check.interval_setting), int), condition_type
            if check.source_ttl_setting is not None:
                assert isinstance(getattr(settings, check.source_ttl_setting), int), condition_type

    def test_the_weather_has_its_own_slower_cadence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        monkeypatch.setattr(settings, "scheduled_actions_weather_check_minutes", 60)

        assert check_interval("weather_change") == timedelta(minutes=60)
        assert check_interval("task_overdue") == timedelta(minutes=10)

    def test_a_check_is_never_faster_than_the_cache_it_reads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The mail search is cached: a faster check would only re-read Redis.
        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        monkeypatch.setattr(settings, "emails_cache_search_ttl_seconds", 900)

        assert check_interval("mail_match") == timedelta(seconds=900)

    def test_an_unknown_type_is_refused_rather_than_guessed(self) -> None:
        with pytest.raises(KeyError):
            check_interval("lunar_eclipse")


class TestTheNextCheck:
    """Strictly ahead, within one interval, on the routine's own phase."""

    def test_it_is_strictly_after_now_and_within_one_interval(self) -> None:
        interval = timedelta(minutes=10)
        action_id = uuid.uuid4()

        due = next_check(action_id, interval, NOW)

        assert NOW < due <= NOW + interval

    def test_a_routine_keeps_its_phase_so_it_never_drifts(self) -> None:
        interval = timedelta(minutes=10)
        action_id = uuid.uuid4()

        first = next_check(action_id, interval, NOW)
        # A check that took a few seconds re-arms on the same grid.
        second = next_check(action_id, interval, first + timedelta(seconds=7))

        assert second - first == interval

    def test_now_exactly_on_the_phase_arms_the_following_check(self) -> None:
        interval = timedelta(minutes=10)
        action_id = uuid.uuid4()
        on_phase = next_check(action_id, interval, NOW)

        assert next_check(action_id, interval, on_phase) == on_phase + interval

    def test_routines_created_together_do_not_check_together(self) -> None:
        interval = timedelta(minutes=10)
        # Twenty watches created in the same minute — the burst the rule is for.
        instants = {next_check(uuid.uuid4(), interval, NOW) for _ in range(20)}

        assert len(instants) > 15


class TestTheLastWatchedDay:
    """``until`` is a local day, included; it ends at that zone's next midnight."""

    def test_it_ends_at_the_local_midnight_after_the_day(self) -> None:
        end = watch_end(date(2026, 9, 30), "Europe/Paris")

        assert end == datetime(2026, 9, 30, 22, 0, tzinfo=UTC)

    def test_a_clock_change_day_is_a_whole_local_day(self) -> None:
        # 25 October 2026 lasts 25 hours in Paris: the end is its local midnight.
        end = watch_end(date(2026, 10, 25), "Europe/Paris")

        assert end == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)

    def test_no_day_means_no_end(self) -> None:
        assert watch_end(None, "Europe/Paris") is None

    def test_the_stored_day_is_read_forgivingly(self) -> None:
        assert condition_until({"type": "mail_match", "until": "2026-10-01"}) == date(2026, 10, 1)
        assert condition_until({"type": "mail_match"}) is None
        # A value no writer produces reads as « no end » rather than crashing a tick.
        assert condition_until({"type": "mail_match", "until": "someday"}) is None
        assert condition_until(None) is None


class TestAConditionPlan:
    def test_it_arms_the_next_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        monkeypatch.setattr(settings, "emails_cache_search_ttl_seconds", 60)
        plan = _plan()

        first = plan.first(NOW)

        assert first == next_check(plan.action_id, timedelta(minutes=10), NOW)

    def test_after_a_tick_it_re_arms_from_now_whatever_was_due(self) -> None:
        plan = _plan()
        long_ago = NOW - timedelta(days=3)

        # A missed check is missed: three days of downtime replay nothing.
        assert plan.after_tick(due_at=long_ago, now=NOW) == plan.first(NOW)

    def test_it_stops_once_the_last_day_is_over(self) -> None:
        plan = _plan(condition_config={"type": "task_overdue", "until": "2026-09-24"})

        assert plan.first(NOW) is None
        assert plan.after_tick(due_at=None, now=NOW) is None

    def test_the_last_day_is_still_watched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        # The fixed id has phase 0: checks fall on the ten-minute marks of UTC.
        # 23:45 in Paris on the last day: the 23:50 check still fits.
        late = datetime(2026, 9, 25, 21, 45, tzinfo=UTC)
        plan = _plan(condition_config={"type": "task_overdue", "until": "2026-09-25"})

        assert plan.first(late) == datetime(2026, 9, 25, 21, 50, tzinfo=UTC)

    def test_a_check_that_would_fall_on_the_end_arms_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        # 23:55 in Paris on the last day: the next mark IS local midnight, the
        # first instant of a day the person did not ask to watch.
        last_minutes = datetime(2026, 9, 25, 21, 55, tzinfo=UTC)
        plan = _plan(condition_config={"type": "task_overdue", "until": "2026-09-25"})

        assert plan.first(last_minutes) is None


class TestATimePlan:
    def test_it_follows_its_recurrence(self) -> None:
        plan = _plan(
            trigger_kind=TriggerKind.TIME.value,
            recurrence=_weekly_at_eight(),
            condition_config=None,
        )

        # 12:03 UTC is 14:03 in Paris: tomorrow at 08:00 local.
        assert plan.first(NOW) == datetime(2026, 9, 26, 6, 0, tzinfo=UTC)

    def test_a_manual_run_ahead_of_schedule_keeps_the_pending_slot(self) -> None:
        plan = _plan(
            trigger_kind=TriggerKind.TIME.value,
            recurrence=_weekly_at_eight(),
            condition_config=None,
        )
        pending = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)

        assert plan.after_tick(due_at=pending, now=NOW) == pending

    def test_a_time_row_without_its_recurrence_arms_nothing(self) -> None:
        # The CHECK constraint forbids it; a plan must not crash on it anyway.
        plan = _plan(trigger_kind=TriggerKind.TIME.value, recurrence=None, condition_config=None)

        assert plan.first(NOW) is None


class TestReadingARow:
    def test_the_plan_is_the_rows_own_fields(self) -> None:
        action = SimpleNamespace(
            id=uuid.uuid4(),
            trigger_kind="condition",
            recurrence_spec=None,
            condition_config={"type": "document_added"},
            user_timezone="America/New_York",
        )

        plan = TriggerPlan.of(action)

        assert plan == TriggerPlan(
            action_id=action.id,
            trigger_kind="condition",
            recurrence=None,
            condition_config={"type": "document_added"},
            timezone="America/New_York",
        )

    def test_a_new_zone_replaces_the_stored_one(self) -> None:
        action = SimpleNamespace(
            id=uuid.uuid4(),
            trigger_kind="time",
            recurrence_spec=_weekly_at_eight(),
            condition_config=None,
            user_timezone="Europe/Paris",
        )

        assert TriggerPlan.of(action, timezone="Asia/Tokyo").timezone == "Asia/Tokyo"


class TestTheSentence:
    """What the card, the hub and the chat's listing say in place of a schedule."""

    def test_a_condition_states_the_systems_clock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        monkeypatch.setattr(settings, "emails_cache_search_ttl_seconds", 60)

        assert schedule_sentence(_plan(), "fr") == "Vérifiée environ toutes les 10 min"
        assert check_minutes(_plan()) == 10

    def test_its_last_day_follows_in_the_recurrence_wording(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "scheduled_actions_weather_check_minutes", 60)
        plan = _plan(condition_config={"type": "weather_change", "until": "2026-10-12"})

        assert schedule_sentence(plan, "fr") == (
            "Vérifiée environ toutes les 60 min, jusqu'au 12/10/2026"
        )
        # Chinese joins with a full-width comma and no space.
        assert schedule_sentence(plan, "zh") == "约每 60 分钟检查一次，直到 12/10/2026"

    def test_a_cache_longer_than_the_cadence_is_what_is_stated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The figure a person reads is the interval actually applied.
        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        monkeypatch.setattr(settings, "emails_cache_search_ttl_seconds", 930)

        assert check_minutes(_plan()) == 16

    def test_a_schedule_is_the_recurrence_sentence(self) -> None:
        plan = _plan(
            trigger_kind=TriggerKind.TIME.value,
            recurrence=_weekly_at_eight(),
            condition_config=None,
        )

        assert schedule_sentence(plan, "en") == describe(_weekly_at_eight(), "en")
        assert check_minutes(plan) is None
