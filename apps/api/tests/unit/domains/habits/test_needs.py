"""Recurring needs (ADR-375): a domain asked on enough days, never an hour locked.

The hour is a DESCRIPTOR (it pre-fills a routine), never a condition: a need
asked at scattered hours is still a need. The fixtures are generic.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.domains.habits.needs import (
    NEED_PAYLOAD_VERSION,
    NeedThresholds,
    detect_need,
    need_payload,
    part_of_day,
    prefill_hour,
)

pytestmark = pytest.mark.unit

TODAY = date(2026, 11, 6)  # a Friday


def _thresholds(**over: object) -> NeedThresholds:
    values: dict[str, object] = {
        "recurrence_window_days": 35,
        "recurrence_min_distinct_days": 4,
        "recurrence_need_min_weeks": 2,
        "recurrence_need_recent_days": 14,
        "recurrence_automate_share": 0.4,
        "recurrence_automate_min_days": 12,
        "recurrence_weekly_min_same_dow": 4,
        "recurrence_weekly_dow_fraction": 0.75,
        "recurrence_weekend_tolerance": 1,
        "recurrence_part_of_day_share": 0.6,
    }
    values.update(over)
    return NeedThresholds.from_settings(SimpleNamespace(**values))


def _days(offsets: list[int], hours: list[float] | None = None) -> dict[date, list[float]]:
    """Days `TODAY - offset`, each carrying the given hours (09:00 by default)."""
    return {TODAY - timedelta(days=k): list(hours or [9.0]) for k in offsets}


class TestExistence:
    def test_four_days_over_two_weeks_with_a_recent_one_is_a_need(self) -> None:
        need = detect_need(
            "event", _days([1, 4, 9, 12]), active_days=20, today=TODAY, thresholds=_thresholds()
        )
        assert need is not None
        assert (need.domain, need.distinct_days, need.active_days) == ("event", 4, 20)

    def test_three_days_are_not_yet_a_need(self) -> None:
        assert (
            detect_need(
                "event", _days([1, 4, 9]), active_days=20, today=TODAY, thresholds=_thresholds()
            )
            is None
        )

    def test_four_days_inside_one_week_are_not_yet_a_need(self) -> None:
        # Monday 2 to Thursday 5 November: one ISO week.
        assert (
            detect_need(
                "event", _days([1, 2, 3, 4]), active_days=20, today=TODAY, thresholds=_thresholds()
            )
            is None
        )

    def test_a_need_nobody_asked_for_in_two_weeks_has_lapsed(self) -> None:
        assert (
            detect_need(
                "event",
                _days([15, 18, 23, 26]),
                active_days=20,
                today=TODAY,
                thresholds=_thresholds(),
            )
            is None
        )

    def test_days_outside_the_window_do_not_count(self) -> None:
        assert (
            detect_need(
                "event",
                _days([1, 36, 40, 45]),
                active_days=20,
                today=TODAY,
                thresholds=_thresholds(),
            )
            is None
        )

    def test_a_day_with_no_hour_is_not_an_occurrence(self) -> None:
        days = _days([1, 4, 9])
        days[TODAY - timedelta(days=12)] = []
        assert (
            detect_need("event", days, active_days=20, today=TODAY, thresholds=_thresholds())
            is None
        )


class TestTheHourIsADescriptor:
    def test_scattered_hours_are_still_a_need(self) -> None:
        """The owner's reorientation: never wait for the same ask at the same hour."""
        days = {TODAY - timedelta(days=k): [7.0 + (k * 3) % 13] for k in (1, 3, 6, 8, 11, 13)}
        need = detect_need("email", days, active_days=20, today=TODAY, thresholds=_thresholds())
        assert need is not None
        assert need.part_of_day == "any"

    def test_concentrated_hours_name_their_part_of_day(self) -> None:
        need = detect_need(
            "event",
            _days([1, 4, 9, 12], [19.5, 20.25]),
            active_days=20,
            today=TODAY,
            thresholds=_thresholds(),
        )
        assert need is not None
        assert need.part_of_day == "evening"
        assert need.usual_hour == pytest.approx(19.875)

    def test_the_prefill_hour_is_the_first_quartile_rounded_down_to_a_quarter(self) -> None:
        assert prefill_hour([8.4, 9.1, 9.3, 11.0]) == pytest.approx(8.75)
        assert prefill_hour([10.0]) == pytest.approx(10.0)
        assert prefill_hour([23.99]) == pytest.approx(23.75)

    def test_a_need_around_midnight_is_read_across_it(self) -> None:
        """The clock wraps: 23:30 and 00:30 are an hour apart, not twenty-three.
        Read on a line, these asks would put the usual hour at noon and the
        routine after the late-evening asks it should precede."""
        need = detect_need(
            "event",
            _days([1, 4, 9, 12], [23.5, 0.5]),
            active_days=20,
            today=TODAY,
            thresholds=_thresholds(),
        )
        assert need is not None
        assert need.usual_hour == pytest.approx(0.0)
        assert need.prefill_hour == pytest.approx(23.5)
        assert need.part_of_day == "night"
        assert prefill_hour([0.25, 0.5, 23.75]) == pytest.approx(0.0)

    @pytest.mark.parametrize(
        "hours", [[8.0, 9.0, 10.0], [21.0, 22.0, 23.0, 23.5], [1.0, 13.0], [6.0, 18.0, 23.9, 0.1]]
    )
    def test_a_descriptor_is_always_an_hour_of_the_day(self, hours: list[float]) -> None:
        need = detect_need(
            "event",
            _days([1, 4, 9, 12], hours),
            active_days=20,
            today=TODAY,
            thresholds=_thresholds(),
        )
        assert need is not None
        assert 0.0 <= need.usual_hour < 24.0
        assert 0.0 <= need.prefill_hour < 24.0
        assert need.prefill_hour * 4 == int(need.prefill_hour * 4)

    @pytest.mark.parametrize(
        ("hour", "part"),
        [
            (4.99, "night"),
            (5.0, "morning"),
            (11.99, "morning"),
            (12.0, "afternoon"),
            (17.99, "afternoon"),
            (18.0, "evening"),
            (22.99, "evening"),
            (23.0, "night"),
            (0.5, "night"),
        ],
    )
    def test_part_of_day_boundaries(self, hour: float, part: str) -> None:
        assert part_of_day(hour) == part


class TestCadence:
    def test_one_weekday_holding_the_days_is_weekly(self) -> None:
        sundays = [k for k in range(35) if (TODAY - timedelta(days=k)).weekday() == 6][:4]
        need = detect_need(
            "event", _days(sundays, [19.0]), active_days=20, today=TODAY, thresholds=_thresholds()
        )
        assert need is not None
        assert (need.cadence, need.weekday) == ("weekly", 6)
        assert need.at_automation_bar is True

    def test_working_days_only_is_weekdays(self) -> None:
        weekdays = [k for k in range(1, 30) if (TODAY - timedelta(days=k)).weekday() < 5][:14]
        need = detect_need(
            "email", _days(weekdays), active_days=22, today=TODAY, thresholds=_thresholds()
        )
        assert need is not None
        assert need.cadence == "weekdays"

    def test_a_weekend_day_beyond_the_tolerance_makes_it_daily(self) -> None:
        offsets = [k for k in range(1, 30) if (TODAY - timedelta(days=k)).weekday() < 5][:12]
        offsets += [k for k in range(1, 30) if (TODAY - timedelta(days=k)).weekday() >= 5][:2]
        need = detect_need(
            "email", _days(offsets), active_days=25, today=TODAY, thresholds=_thresholds()
        )
        assert need is not None
        assert need.cadence == "daily"

    def test_too_few_days_never_claim_weekdays(self) -> None:
        need = detect_need(
            "email", _days([1, 4, 8, 11]), active_days=20, today=TODAY, thresholds=_thresholds()
        )
        assert need is not None
        assert need.cadence == "daily"


class TestAutomationBar:
    def test_share_and_days_both_reached(self) -> None:
        need = detect_need(
            "event",
            _days(list(range(1, 25, 2))),
            active_days=24,
            today=TODAY,
            thresholds=_thresholds(),
        )
        assert need is not None
        assert (need.distinct_days, need.at_automation_bar) == (12, True)

    def test_enough_days_but_a_small_share_of_a_busy_month(self) -> None:
        need = detect_need(
            "event",
            _days(list(range(1, 25, 2))),
            active_days=35,
            today=TODAY,
            thresholds=_thresholds(),
        )
        assert need is not None
        assert need.at_automation_bar is False

    def test_a_high_share_of_too_few_days(self) -> None:
        need = detect_need(
            "event", _days([1, 4, 9, 12, 15]), active_days=6, today=TODAY, thresholds=_thresholds()
        )
        assert need is not None
        assert need.at_automation_bar is False

    def test_an_incomplete_rollup_never_inflates_the_share(self) -> None:
        """Active days below the need's own days (pruned rollup) count as the need's days."""
        need = detect_need(
            "event",
            _days(list(range(1, 25, 2))),
            active_days=3,
            today=TODAY,
            thresholds=_thresholds(),
        )
        assert need is not None
        assert need.active_days == 12


class TestPayload:
    def test_the_payload_is_versioned_and_carries_no_lock(self) -> None:
        need = detect_need(
            "event",
            _days([1, 4, 9, 12], [8.5]),
            active_days=20,
            today=TODAY,
            thresholds=_thresholds(),
        )
        assert need is not None
        payload = need_payload(need, usual_intent="search")
        assert payload["version"] == NEED_PAYLOAD_VERSION == 2
        assert payload["domain"] == "event"
        assert payload["usual_intent"] == "search"
        assert "trigger_hour" not in payload and "shape" not in payload
        assert payload["prefill_hour"] == pytest.approx(8.5)

    def test_no_intent_is_absent_rather_than_a_placeholder(self) -> None:
        need = detect_need(
            "event", _days([1, 4, 9, 12]), active_days=20, today=TODAY, thresholds=_thresholds()
        )
        assert need is not None
        assert "usual_intent" not in need_payload(need, usual_intent=None)
