"""The most recent instant of a schedule inside a window, walked back from its end.

The scheduler asks it once an occurrence is given up as too late: which later
occurrence, if any, has already come? Walking FORWARD from the occurrence given
up would visit every instant of the outage — hundreds for a frequent schedule;
walking back from now stops at the first day that holds one.

Proven in a zone far from UTC: a local day there is not the UTC day, and the
walk is by LOCAL day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import (
    DailyTimes,
    RecurrenceSpec,
    SeriesEnd,
    TimeOfDay,
    latest_occurrence,
)

pytestmark = pytest.mark.unit

AUCKLAND = "Pacific/Auckland"
_ZONE = ZoneInfo(AUCKLAND)


def _local(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=_ZONE).astimezone(UTC)


def _twice_a_day(**over: object) -> RecurrenceSpec:
    return RecurrenceSpec(
        freq="daily",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0), TimeOfDay(hour=18, minute=0))),
        anchor_date=date(2026, 11, 1),
        **over,
    )


def test_the_latest_instant_of_the_last_day_is_found_first() -> None:
    found = latest_occurrence(
        _twice_a_day(), AUCKLAND, after=_local(10, 8), until=_local(12, 19), max_days=30
    )

    assert found == _local(12, 18)


def test_an_instant_still_ahead_on_the_last_day_is_not_taken() -> None:
    found = latest_occurrence(
        _twice_a_day(), AUCKLAND, after=_local(10, 8), until=_local(12, 9), max_days=30
    )

    assert found == _local(12, 8)


def test_the_walk_goes_back_over_days_that_hold_nothing() -> None:
    """The series ended on the 11th: the 12th to the 14th are empty."""
    ended = _twice_a_day(end=SeriesEnd(kind="on_date", on_date=date(2026, 11, 11)))

    found = latest_occurrence(
        ended, AUCKLAND, after=_local(10, 8), until=_local(14, 12), max_days=30
    )

    assert found == _local(11, 18)


def test_the_bounds_are_open_on_the_past_and_closed_on_the_present() -> None:
    spec = _twice_a_day()

    assert latest_occurrence(
        spec, AUCKLAND, after=_local(12, 8), until=_local(12, 18), max_days=30
    ) == _local(12, 18)
    assert (
        latest_occurrence(spec, AUCKLAND, after=_local(12, 8), until=_local(12, 17), max_days=30)
        is None
    )


def test_the_walk_is_bounded() -> None:
    """A window of years is not walked day by day: past the bound, nothing."""
    ended = _twice_a_day(end=SeriesEnd(kind="on_date", on_date=date(2026, 11, 2)))

    found = latest_occurrence(ended, AUCKLAND, after=_local(1, 8), until=_local(20, 12), max_days=5)

    assert found is None
