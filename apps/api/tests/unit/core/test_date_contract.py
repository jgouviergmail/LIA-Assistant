"""The one contract of a date a tool is given (ADR-310, ADR-318).

A tool never replaces a value it cannot read (ADR-310): « demain », « 24/09 »
and an impossible day are refused with the accepted format and today's date,
so the model corrects its own call. A date stays a date and a datetime a
datetime — « how many days » and « how many hours » are different questions,
and promoting every value to midnight would answer the first with the second.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.core.date_contract import (
    ISO_MOMENT_DESCRIPTION,
    InvertedPeriodError,
    UnreadableDateError,
    period_bounds,
    read_moment,
    unreadable_date_message,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


class TestWhatIsRead:
    def test_a_date_stays_a_date(self) -> None:
        assert read_moment("2026-09-24", PARIS) == date(2026, 9, 24)

    def test_a_datetime_without_offset_is_read_in_the_given_zone(self) -> None:
        moment = read_moment("2026-09-24T14:30", PARIS)

        assert isinstance(moment, datetime)
        assert moment == datetime(2026, 9, 24, 14, 30, tzinfo=PARIS)
        assert moment.utcoffset() == timedelta(hours=2)

    def test_a_datetime_with_an_offset_keeps_it(self) -> None:
        moment = read_moment("2026-09-24T14:30:00+05:00", PARIS)

        assert moment == datetime(2026, 9, 24, 14, 30, tzinfo=timezone(timedelta(hours=5)))

    def test_a_trailing_z_is_utc(self) -> None:
        assert read_moment("2026-09-24T12:00:00Z", PARIS) == datetime(2026, 9, 24, 12, tzinfo=UTC)

    def test_surrounding_spaces_are_ignored(self) -> None:
        assert read_moment("  2026-09-24 ", PARIS) == date(2026, 9, 24)


class TestWhatIsRefused:
    @pytest.mark.parametrize(
        "reference",
        ["demain", "tomorrow", "24/09/2026", "09/24/2026", "2026-02-30", "2026-13-01", "", "  "],
    )
    def test_anything_but_iso(self, reference: str) -> None:
        with pytest.raises(UnreadableDateError) as caught:
            read_moment(reference, PARIS)

        assert caught.value.reference == reference.strip()


class TestTheRefusalMessage:
    def test_it_names_the_value_the_format_and_today(self) -> None:
        from src.core.time_utils import now_in_timezone

        message = unreadable_date_message("demain", "Europe/Paris")

        assert "'demain'" in message
        assert "YYYY-MM-DD" in message
        assert now_in_timezone("Europe/Paris").date().isoformat() in message
        assert "Europe/Paris" in message


def test_the_published_description_names_the_format() -> None:
    assert "YYYY-MM-DD" in ISO_MOMENT_DESCRIPTION
    assert "timezone" in ISO_MOMENT_DESCRIPTION


NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


class TestAPeriod:
    """Two optional ISO values become two instants; a day is a WHOLE day."""

    def test_two_days_cover_both_whole_days(self) -> None:
        since, until = period_bounds("2026-09-21", "2026-09-22", PARIS, now=NOW, default_days=7)

        assert since == datetime(2026, 9, 21, tzinfo=PARIS)
        assert until == datetime(2026, 9, 23, tzinfo=PARIS)

    def test_one_day_is_that_day(self) -> None:
        since, until = period_bounds("2026-09-21", "2026-09-21", PARIS, now=NOW, default_days=7)

        assert until - since == timedelta(days=1)

    def test_nothing_given_is_the_default_window_ending_now(self) -> None:
        assert period_bounds(None, None, PARIS, now=NOW, default_days=7) == (
            NOW - timedelta(days=7),
            NOW,
        )

    def test_only_a_start_runs_until_now(self) -> None:
        since, until = period_bounds("2026-09-01", None, PARIS, now=NOW, default_days=7)

        assert (since, until) == (datetime(2026, 9, 1, tzinfo=PARIS), NOW)

    def test_only_an_end_looks_back_the_default_window(self) -> None:
        since, until = period_bounds(None, "2026-09-10", PARIS, now=NOW, default_days=7)

        assert until == datetime(2026, 9, 11, tzinfo=PARIS)
        assert since == until - timedelta(days=7)

    def test_without_a_default_window_an_open_end_stays_open(self) -> None:
        assert period_bounds(None, None, PARIS, now=NOW, default_days=None) == (None, None)
        assert period_bounds("2026-09-01", None, PARIS, now=NOW, default_days=None) == (
            datetime(2026, 9, 1, tzinfo=PARIS),
            None,
        )

    def test_datetimes_are_taken_as_instants(self) -> None:
        since, until = period_bounds(
            "2026-09-21T08:00", "2026-09-21T12:00:00Z", PARIS, now=NOW, default_days=7
        )

        assert since == datetime(2026, 9, 21, 8, tzinfo=PARIS)
        assert until == datetime(2026, 9, 21, 12, tzinfo=UTC)

    def test_a_period_ending_before_it_starts_is_refused(self) -> None:
        with pytest.raises(InvertedPeriodError):
            period_bounds("2026-09-22", "2026-09-21", PARIS, now=NOW, default_days=7)

    def test_an_unreadable_bound_is_the_contract_s_refusal(self) -> None:
        with pytest.raises(UnreadableDateError):
            period_bounds("last week", None, PARIS, now=NOW, default_days=7)
