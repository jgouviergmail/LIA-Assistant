"""Reading a routine's calendar and the ledger for the proposal rules (ADR-375)."""

from __future__ import annotations

from datetime import date

import pytest

from src.core.recurrence import RecurrenceSpec
from src.domains.habits.usage_observations import LedgerView, needs_from_ledger, routine_schedule

pytestmark = pytest.mark.unit


def _spec(**over: object) -> RecurrenceSpec:
    data: dict[str, object] = {
        "freq": "daily",
        "interval": 1,
        "anchor_date": "2026-09-01",
        "times": {"mode": "at", "at": [{"hour": 7, "minute": 45}, {"hour": 18, "minute": 0}]},
    }
    data.update(over)
    return RecurrenceSpec.model_validate(data)


def test_a_daily_routine_fires_every_day_at_its_times() -> None:
    times, fires_on = routine_schedule(_spec())
    assert times == (7.75, 18.0)
    assert fires_on == frozenset(range(7))


def test_a_weekly_routine_fires_on_its_iso_weekdays() -> None:
    _, fires_on = routine_schedule(_spec(freq="weekly", byweekday=[1, 2, 3, 4, 5]))
    assert fires_on == frozenset(range(5))


@pytest.mark.parametrize(
    "over",
    [
        {"interval": 2},
        {"freq": "weekly", "byweekday": [7], "interval": 2},
        {"freq": "monthly", "bymonthday": [1]},
    ],
)
def test_a_calendar_that_skips_days_serves_no_daily_or_weekly_need(over: dict[str, object]) -> None:
    _, fires_on = routine_schedule(_spec(**over))
    assert fires_on == frozenset()


def test_a_condition_routine_has_no_calendar() -> None:
    assert routine_schedule(None) == ((), frozenset())


def test_needs_are_read_from_registered_single_domain_signatures() -> None:
    ledger = LedgerView(
        readable=True,
        days_by_domain={
            "event": {date(2026, 11, d): [9.0] for d in (2, 3, 4, 5)}
            | {date(2026, 10, d): [9.0] for d in (27, 28)},
            "email+contact": {date(2026, 11, d): [9.0] for d in range(1, 7)},
            "not_a_domain": {date(2026, 11, d): [9.0] for d in range(1, 7)},
        },
        intents={"event": "search"},
    )
    from types import SimpleNamespace

    from src.domains.habits.needs import NeedThresholds

    thresholds = NeedThresholds.from_settings(
        SimpleNamespace(
            recurrence_window_days=35,
            recurrence_min_distinct_days=4,
            recurrence_need_min_weeks=2,
            recurrence_need_recent_days=14,
            recurrence_automate_share=0.4,
            recurrence_automate_min_days=12,
            recurrence_weekly_min_same_dow=4,
            recurrence_weekly_dow_fraction=0.75,
            recurrence_weekend_tolerance=1,
            recurrence_part_of_day_share=0.6,
        )
    )
    needs = needs_from_ledger(
        ledger, active_days=20, today=date(2026, 11, 6), thresholds=thresholds
    )
    assert [need.domain for need in needs] == ["event"]


def test_an_unreadable_ledger_holds_no_need() -> None:
    from types import SimpleNamespace

    from src.domains.habits.needs import NeedThresholds

    thresholds = NeedThresholds.from_settings(
        SimpleNamespace(
            recurrence_window_days=35,
            recurrence_min_distinct_days=4,
            recurrence_need_min_weeks=2,
            recurrence_need_recent_days=14,
            recurrence_automate_share=0.4,
            recurrence_automate_min_days=12,
            recurrence_weekly_min_same_dow=4,
            recurrence_weekly_dow_fraction=0.75,
            recurrence_weekend_tolerance=1,
            recurrence_part_of_day_share=0.6,
        )
    )
    ledger = LedgerView(readable=False, days_by_domain={}, intents={})
    assert (
        needs_from_ledger(ledger, active_days=0, today=date(2026, 11, 6), thresholds=thresholds)
        == ()
    )
