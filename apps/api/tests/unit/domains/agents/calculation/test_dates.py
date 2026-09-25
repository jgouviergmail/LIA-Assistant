"""Date arithmetic the model must not do in its head (ADR-318).

Every expected value below was computed by the standard library on 3.14.7
before being written here — the calendar is not a subject to reason about from
memory. The clock is injected: « today » is 2026-09-24 (a Thursday) at 12:00
UTC, 14:00 in Paris.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.date_contract import UnreadableDateError
from src.domains.agents.calculation.dates import (
    DATE_OPERATIONS,
    DATE_UNITS,
    DateArithmeticError,
    DateRequest,
    answer_date_request,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _facts(
    operation: str,
    *,
    date: str | None = None,
    other_date: str | None = None,
    amount: int | None = None,
    unit: str | None = None,
    timezone: str | None = None,
    to_timezone: str | None = None,
) -> dict[str, object]:
    request = DateRequest(
        operation=operation,
        date=date,
        other_date=other_date,
        amount=amount,
        unit=unit,
        timezone=timezone,
        to_timezone=to_timezone,
    )
    return answer_date_request(request, user_zone=PARIS, now=NOW).facts


def _refusal(
    operation: str,
    *,
    date: str | None = None,
    other_date: str | None = None,
    amount: int | None = None,
    unit: str | None = None,
    to_timezone: str | None = None,
) -> DateArithmeticError:
    with pytest.raises(DateArithmeticError) as caught:
        _facts(
            operation,
            date=date,
            other_date=other_date,
            amount=amount,
            unit=unit,
            to_timezone=to_timezone,
        )
    return caught.value


class TestNow:
    def test_the_current_moment_in_the_person_s_zone(self) -> None:
        facts = _facts("now")

        assert facts["result"] == "2026-09-24T14:00:00+02:00"
        assert facts["weekday"] == "Thursday"
        assert facts["iso_week"] == 39
        assert facts["timezone"] == "Europe/Paris"

    def test_in_another_zone(self) -> None:
        facts = _facts("now", timezone="Asia/Tokyo")

        assert facts["result"] == "2026-09-24T21:00:00+09:00"


class TestDifference:
    def test_between_two_dates(self) -> None:
        facts = _facts("difference", date="2026-09-24", other_date="2027-07-14")

        assert facts["days"] == 293
        assert facts["weeks"] == {"weeks": 41, "days": 6}
        assert facts["calendar"] == {"years": 0, "months": 9, "days": 20}
        assert "duration" not in facts

    def test_backwards_is_negative(self) -> None:
        facts = _facts("difference", date="2027-07-14", other_date="2026-09-24")

        assert facts["days"] == -293
        assert facts["calendar"] == {"years": 0, "months": -9, "days": -20}

    def test_an_age(self) -> None:
        facts = _facts("difference", date="1980-05-12", other_date="2026-09-24")

        assert facts["calendar"] == {"years": 46, "months": 4, "days": 12}

    def test_the_first_date_defaults_to_today(self) -> None:
        facts = _facts("difference", other_date="2026-12-25")

        assert facts["from"] == "2026-09-24"
        assert facts["days"] == 92

    def test_two_datetimes_give_a_duration(self) -> None:
        facts = _facts("difference", date="2026-09-24T09:15", other_date="2026-09-24T17:40")

        assert facts["duration"] == {"hours": 8, "minutes": 25, "total_minutes": 505}
        assert facts["days"] == 0

    def test_a_duration_counts_real_time_across_a_clock_change(self) -> None:
        """Paris leaves summer time on 2026-10-25: noon to noon is 25 hours."""
        facts = _facts("difference", date="2026-10-24T12:00", other_date="2026-10-25T12:00")

        assert facts["duration"] == {"hours": 25, "minutes": 0, "total_minutes": 1500}
        assert facts["days"] == 1

    def test_with_a_time_the_elapsed_time_is_the_answer(self) -> None:
        """23:00 to 01:00 is two hours, on dates one day apart — never « 1 day »
        beside « 0 days »."""
        answer = answer_date_request(
            DateRequest(
                operation="difference", date="2026-09-24T23:00", other_date="2026-09-25T01:00"
            ),
            user_zone=PARIS,
            now=NOW,
        )

        assert answer.facts["result"] == "2 h 0 min"
        assert answer.facts["days"] == 1
        assert answer.facts["calendar"] == {
            "years": 0,
            "months": 0,
            "days": 0,
            "hours": 2,
            "minutes": 0,
        }
        assert "2 h 0 min elapsed" in answer.summary
        assert "the dates are 1 day apart" in answer.summary

    def test_a_negative_duration_under_an_hour_keeps_its_sign(self) -> None:
        facts = _facts("difference", date="2026-09-24T10:30", other_date="2026-09-24T10:00")

        assert facts["duration"] == {"hours": 0, "minutes": -30, "total_minutes": -30}
        assert facts["result"] == "-0 h 30 min"

    def test_a_date_beside_a_datetime_is_its_midnight(self) -> None:
        facts = _facts("difference", date="2026-09-24", other_date="2026-09-25T06:00")

        assert facts["duration"] == {"hours": 30, "minutes": 0, "total_minutes": 1800}

    def test_the_other_date_is_required(self) -> None:
        refusal = _refusal("difference", date="2026-09-24")

        assert refusal.reason == "missing_parameter"
        assert "other_date" in str(refusal)


class TestAdd:
    @pytest.mark.parametrize(
        ("base", "amount", "unit", "expected"),
        [
            ("2026-09-24", 10, "days", "2026-10-04"),
            ("2026-09-24", -3, "weeks", "2026-09-03"),
            ("2026-09-24", 3, "business_days", "2026-09-29"),
            ("2026-09-24", 10, "business_days", "2026-10-08"),
            ("2026-09-26", 1, "business_days", "2026-09-28"),
            ("2026-09-26", 5, "business_days", "2026-10-02"),
            ("2026-09-28", -1, "business_days", "2026-09-25"),
            ("2026-09-27", -1, "business_days", "2026-09-25"),
            ("2026-09-24", 0, "business_days", "2026-09-24"),
            ("2026-10-24T12:00", 1, "days", "2026-10-25T12:00:00+01:00"),
            ("2026-10-25T01:30", 2, "hours", "2026-10-25T02:30:00+01:00"),
            ("2026-09-24T23:50", 15, "minutes", "2026-09-25T00:05:00+02:00"),
        ],
    )
    def test_the_result(self, base: str, amount: int, unit: str, expected: str) -> None:
        assert _facts("add", date=base, amount=amount, unit=unit)["result"] == expected

    @pytest.mark.parametrize(
        ("base", "amount", "unit", "expected"),
        [("2026-01-31", 1, "months", "2026-02-28"), ("2024-02-29", 1, "years", "2025-02-28")],
    )
    def test_a_day_the_month_does_not_have_is_clamped_and_said(
        self, base: str, amount: int, unit: str, expected: str
    ) -> None:
        facts = _facts("add", date=base, amount=amount, unit=unit)

        assert facts["result"] == expected
        assert facts["day_clamped"] is True

    def test_an_ordinary_month_is_not_clamped(self) -> None:
        assert _facts("add", date="2026-01-15", amount=1, unit="months")["day_clamped"] is False

    def test_the_weekday_of_the_result_is_given(self) -> None:
        assert _facts("add", date="2026-09-24", amount=10, unit="days")["weekday"] == "Sunday"

    @pytest.mark.parametrize(
        ("amount", "unit"), [(1, "days"), (10**9, "years"), (10**9, "business_days")]
    )
    def test_beyond_the_calendar_is_refused(self, amount: int, unit: str) -> None:
        assert _refusal("add", date="9999-12-31", amount=amount, unit=unit).reason == (
            "out_of_range"
        )

    def test_an_unknown_unit_lists_the_accepted_ones(self) -> None:
        refusal = _refusal("add", date="2026-09-24", amount=1, unit="fortnights")

        assert refusal.reason == "invalid_parameter"
        for unit in DATE_UNITS:
            assert unit in str(refusal)

    @pytest.mark.parametrize("missing", ["amount", "unit"])
    def test_amount_and_unit_are_required(self, missing: str) -> None:
        refusal = _refusal(
            "add",
            date="2026-09-24",
            amount=None if missing == "amount" else 1,
            unit=None if missing == "unit" else "days",
        )

        assert refusal.reason == "missing_parameter"
        assert missing in str(refusal)


class TestWeekday:
    def test_the_facts_of_a_day(self) -> None:
        facts = _facts("weekday", date="2026-07-14")

        assert facts["result"] == "Tuesday"
        assert facts["iso_week"] == 29
        assert facts["iso_year"] == 2026
        assert facts["day_of_year"] == 195
        assert facts["is_weekend"] is False

    def test_a_datetime_is_read_as_its_local_day(self) -> None:
        """23:30 UTC on the 25th is already the 26th in Paris."""
        assert _facts("weekday", date="2026-09-25T23:30:00Z")["date"] == "2026-09-26"


class TestBusinessDays:
    def test_a_month_both_ends_included(self) -> None:
        facts = _facts("business_days", date="2026-09-01", other_date="2026-09-30")

        assert facts["business_days"] == 22
        assert facts["result"] == "22"
        assert facts["calendar_days"] == 30
        assert facts["public_holidays_excluded"] is False

    @pytest.mark.parametrize(
        ("day", "expected"), [("2026-09-24", 1), ("2026-09-26", 0), ("2026-09-27", 0)]
    )
    def test_a_single_day(self, day: str, expected: int) -> None:
        assert _facts("business_days", date=day, other_date=day)["business_days"] == expected

    def test_backwards_is_negative(self) -> None:
        facts = _facts("business_days", date="2026-09-30", other_date="2026-09-01")

        assert facts["business_days"] == -22


class TestConvertTimezone:
    def test_a_local_time_elsewhere(self) -> None:
        facts = _facts("convert_timezone", date="2026-09-24T09:00", to_timezone="America/New_York")

        assert facts["from"] == "2026-09-24T09:00:00+02:00"
        assert facts["result"] == "2026-09-24T03:00:00-04:00"
        assert facts["to_timezone"] == "America/New_York"

    def test_a_time_with_its_own_offset(self) -> None:
        facts = _facts(
            "convert_timezone", date="2026-09-24T09:00:00+02:00", to_timezone="Asia/Tokyo"
        )

        assert facts["result"] == "2026-09-24T16:00:00+09:00"

    def test_a_naive_time_is_read_in_the_named_source_zone(self) -> None:
        facts = _facts(
            "convert_timezone",
            date="2026-09-24T09:00",
            timezone="America/New_York",
            to_timezone="Europe/Paris",
        )

        assert facts["result"] == "2026-09-24T15:00:00+02:00"

    def test_without_a_time_it_is_now(self) -> None:
        facts = _facts("convert_timezone", to_timezone="Asia/Tokyo")

        assert facts["result"] == "2026-09-24T21:00:00+09:00"

    def test_a_bare_date_has_no_time_to_convert(self) -> None:
        refusal = _refusal("convert_timezone", date="2026-09-24", to_timezone="Asia/Tokyo")

        assert refusal.reason == "invalid_parameter"

    def test_the_target_zone_is_required(self) -> None:
        assert _refusal("convert_timezone", date="2026-09-24T09:00").reason == ("missing_parameter")

    @pytest.mark.parametrize("zone", ["Mars/Olympus", "../etc/passwd", "UTC+2", "a" * 300])
    def test_an_unknown_zone_is_refused(self, zone: str) -> None:
        """A name longer than the filesystem allows raises ``OSError`` (measured):
        a refusal too, which echoes a bounded part of the value and no server path."""
        refusal = _refusal("convert_timezone", date="2026-09-24T09:00", to_timezone=zone)

        assert refusal.reason == "unknown_timezone"
        assert "Europe/Paris" in str(refusal)
        assert "a" * 65 not in str(refusal)
        assert "site-packages" not in str(refusal)


class TestContract:
    def test_an_unreadable_date_propagates_for_the_tool_to_word(self) -> None:
        with pytest.raises(UnreadableDateError):
            _facts("weekday", date="demain")

    def test_an_unknown_operation_lists_the_accepted_ones(self) -> None:
        refusal = _refusal("sunrise")

        assert refusal.reason == "invalid_parameter"
        for operation in DATE_OPERATIONS:
            assert operation in str(refusal)

    def test_every_answer_carries_a_summary_and_a_result(self) -> None:
        answer = answer_date_request(
            DateRequest(operation="weekday", date="2026-07-14"), user_zone=PARIS, now=NOW
        )

        assert answer.summary
        assert answer.facts["result"] == "Tuesday"
        assert answer.facts["operation"] == "weekday"
