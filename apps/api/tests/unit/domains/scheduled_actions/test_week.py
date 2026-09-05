"""The week fold (ADR-265): which run colours which cell, and what today is."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.scheduled_actions.models import ScheduledRunOutcome
from src.domains.scheduled_actions.week import (
    build_week,
    fold_runs_by_slot,
    week_read_lower_bound,
)

pytestmark = pytest.mark.unit

# Wednesday 5 August 2026, 12:00 Paris.
NOW = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)
MON = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)  # 08:00 Paris
WED = datetime(2026, 8, 5, 6, 0, tzinfo=UTC)
FRI = datetime(2026, 8, 7, 6, 0, tzinfo=UTC)


def _action(**over: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "days_of_week": [1, 3, 5],
        "trigger_hour": 8,
        "trigger_minute": 0,
        "user_timezone": "Europe/Paris",
        "is_enabled": True,
    }
    base.update(over)
    return SimpleNamespace(**base)


def _run(action: SimpleNamespace, slot: datetime | None, **over: Any) -> SimpleNamespace:
    base = {
        "scheduled_action_id": action.id,
        "slot_at": slot,
        "started_at": (slot or NOW) + timedelta(seconds=5),
        "outcome": ScheduledRunOutcome.SUCCESS,
        "error": None,
        "manual": False,
    }
    base.update(over)
    return SimpleNamespace(**base)


class TestCells:
    def test_one_cell_per_configured_day_of_the_week(self) -> None:
        action = _action()
        [week] = build_week([action], [], now=NOW)

        assert [c.day for c in week.cells] == [1, 3, 5]
        assert [c.slot_at for c in week.cells] == [MON, WED, FRI]
        assert [c.date for c in week.cells] == [
            date(2026, 8, 3),
            date(2026, 8, 5),
            date(2026, 8, 7),
        ]
        assert all(c.outcome is None for c in week.cells)
        assert (week.week_start, week.today, week.timezone) == (
            date(2026, 8, 3),
            3,
            "Europe/Paris",
        )

    def test_a_run_colours_exactly_the_slot_it_served(self) -> None:
        action = _action()
        runs = [
            _run(action, MON),
            _run(action, WED, outcome=ScheduledRunOutcome.FAILURE, error="boom"),
        ]
        [week] = build_week([action], runs, now=NOW)

        by_day = {c.day: c for c in week.cells}
        assert by_day[1].outcome is ScheduledRunOutcome.SUCCESS
        assert by_day[1].run_at == MON + timedelta(seconds=5)
        assert by_day[3].outcome is ScheduledRunOutcome.FAILURE
        assert by_day[3].error == "boom"
        assert by_day[5].outcome is None

    def test_the_last_run_of_a_slot_wins(self) -> None:
        # A due failure at 08:00:05, then a manual success at 09:30 serving the same slot.
        action = _action()
        runs = [
            _run(action, MON, outcome=ScheduledRunOutcome.FAILURE, error="first"),
            _run(action, MON, started_at=MON + timedelta(hours=1, minutes=30), manual=True),
        ]
        [week] = build_week([action], runs, now=NOW)

        monday = week.cells[0]
        assert monday.outcome is ScheduledRunOutcome.SUCCESS
        assert monday.manual is True
        assert monday.error is None

    def test_a_rehearsal_colours_nothing(self) -> None:
        action = _action()
        [week] = build_week([action], [_run(action, None)], now=NOW)
        assert all(c.outcome is None for c in week.cells)

    def test_a_run_from_before_a_schedule_change_no_longer_matches(self) -> None:
        # The routine ran at 08:00 Monday; the user then moved it to 09:00.
        action = _action(trigger_hour=9)
        [week] = build_week([action], [_run(action, MON)], now=NOW)
        assert all(c.outcome is None for c in week.cells)

    def test_another_routines_run_never_colours_this_one(self) -> None:
        mine, theirs = _action(), _action()
        weeks = build_week([mine, theirs], [_run(theirs, MON)], now=NOW)
        by_id = {w.action_id: w for w in weeks}
        assert by_id[mine.id].cells[0].outcome is None
        assert by_id[theirs.id].cells[0].outcome is ScheduledRunOutcome.SUCCESS

    def test_a_paused_routine_keeps_its_cells_and_its_history(self) -> None:
        action = _action(is_enabled=False)
        [week] = build_week([action], [_run(action, MON)], now=NOW)
        assert len(week.cells) == 3
        assert week.cells[0].outcome is ScheduledRunOutcome.SUCCESS

    def test_the_skips_and_the_proposal_are_reported_as_such(self) -> None:
        action = _action()
        runs = [
            _run(action, MON, outcome=ScheduledRunOutcome.SKIPPED_CONDITION),
            _run(action, WED, outcome=ScheduledRunOutcome.PROPOSED),
        ]
        [week] = build_week([action], runs, now=NOW)
        assert [c.outcome for c in week.cells] == [
            ScheduledRunOutcome.SKIPPED_CONDITION,
            ScheduledRunOutcome.PROPOSED,
            None,
        ]

    def test_no_routine_no_week(self) -> None:
        assert build_week([], [], now=NOW) == []


class TestToday:
    def test_today_is_read_in_the_routines_zone_not_the_servers(self) -> None:
        # Sunday 14:00 UTC: 16:00 Sunday in Paris, 02:00 Monday in Auckland.
        sunday_night = datetime(2026, 8, 9, 14, 0, tzinfo=UTC)
        paris = _action(days_of_week=[1, 2, 3, 4, 5, 6, 7])
        auckland = _action(days_of_week=[1, 2, 3, 4, 5, 6, 7], user_timezone="Pacific/Auckland")

        weeks = {w.action_id: w for w in build_week([paris, auckland], [], now=sunday_night)}

        assert weeks[paris.id].today == 7
        assert weeks[paris.id].week_start == date(2026, 8, 3)
        assert weeks[auckland.id].today == 1
        assert weeks[auckland.id].week_start == date(2026, 8, 10)


class TestLowerBound:
    def test_the_earliest_monday_across_the_zones(self) -> None:
        sunday_night = datetime(2026, 8, 9, 14, 0, tzinfo=UTC)
        actions = [_action(), _action(user_timezone="Pacific/Auckland")]
        bound = week_read_lower_bound(actions, now=sunday_night)
        # Paris Monday 3 August 00:00 CEST = 2 August 22:00Z, earlier than Auckland's 10 August.
        assert bound == datetime(2026, 8, 2, 22, 0, tzinfo=UTC)

    def test_no_routine_no_bound(self) -> None:
        assert week_read_lower_bound([], now=NOW) is None


class TestFold:
    def test_keeps_the_latest_start_per_slot_and_drops_rehearsals(self) -> None:
        action = _action()
        older = _run(action, MON, started_at=MON + timedelta(seconds=5))
        newer = _run(action, MON, started_at=MON + timedelta(hours=2))
        rehearsal = _run(action, None)
        folded = fold_runs_by_slot([newer, older, rehearsal])  # order-independent
        assert folded == {(action.id, MON): newer}
