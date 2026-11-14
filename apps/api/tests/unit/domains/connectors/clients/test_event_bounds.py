"""An event's bounds are typed once, for the three calendars (ADR-380)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.wall_time import WallTime
from src.domains.connectors.clients.event_bounds import (
    DayBounds,
    TimedBounds,
    TimedSides,
    bounds_of,
    change_of,
    series_bounds,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


def _wall(day: int, hour: int, minute: int = 0) -> WallTime:
    return WallTime(datetime(2026, 11, day, hour, minute), PARIS)


class TestTheBoundsOfANewEvent:
    def test_timed_bounds_are_wall_times_in_the_zone_they_were_written_in(self) -> None:
        bounds = bounds_of("2026-11-27T09:30:00", "2026-11-27T10:30:00", PARIS, all_day=False)

        assert bounds == TimedBounds(_wall(27, 9, 30), _wall(27, 10, 30))

    def test_a_time_written_with_an_offset_lands_on_the_same_wall(self) -> None:
        bounds = bounds_of(
            "2026-11-27T08:30:00Z", "2026-11-27T10:30:00+01:00", PARIS, all_day=False
        )

        assert bounds == TimedBounds(_wall(27, 9, 30), _wall(27, 10, 30))

    def test_all_day_bounds_are_days_the_end_exclusive(self) -> None:
        bounds = bounds_of("2026-11-27", "2026-11-28", PARIS, all_day=True)

        assert bounds == DayBounds(date(2026, 11, 27), date(2026, 11, 28), PARIS)

    def test_a_day_is_no_time(self) -> None:
        with pytest.raises(ValueError):
            bounds_of("2026-11-27", "2026-11-28", PARIS, all_day=False)

    def test_an_all_day_event_ends_after_the_day_it_starts(self) -> None:
        with pytest.raises(ValueError):
            bounds_of("2026-11-27", "2026-11-27", PARIS, all_day=True)


class TestWhatAChangeSaysOfTheBounds:
    def test_no_bound_given_changes_no_bound(self) -> None:
        assert change_of(None, None, PARIS, all_day=None) is None

    def test_one_side_given_leaves_the_other_where_it_is(self) -> None:
        assert change_of("2026-11-27T09:30:00", None, PARIS, all_day=None) == TimedSides(
            start=_wall(27, 9, 30), end=None
        )
        assert change_of(None, "2026-11-27T10:30:00", PARIS, all_day=None) == TimedSides(
            start=None, end=_wall(27, 10, 30)
        )

    def test_a_shape_named_is_a_whole_new_pair_of_bounds(self) -> None:
        assert change_of(
            "2026-11-27T09:30:00", "2026-11-27T10:30:00", PARIS, all_day=False
        ) == TimedBounds(_wall(27, 9, 30), _wall(27, 10, 30))
        assert change_of("2026-11-27", "2026-11-29", PARIS, all_day=True) == DayBounds(
            date(2026, 11, 27), date(2026, 11, 29), PARIS
        )

    @pytest.mark.parametrize("all_day", [True, False])
    def test_a_shape_cannot_change_on_one_side_only(self, all_day: bool) -> None:
        with pytest.raises(ValueError):
            change_of("2026-11-27T09:30:00", None, PARIS, all_day=all_day)


class TestAWholeSeriesMoved:
    """A series keeps its first day and shows the times its occurrence was given."""

    def test_timed_bounds_keep_the_times_of_day(self) -> None:
        asked = TimedBounds(_wall(27, 9, 30), _wall(27, 11, 0))

        assert series_bounds(date(2026, 11, 2), asked) == TimedBounds(
            _wall(2, 9, 30), _wall(2, 11, 0)
        )

    def test_an_event_past_midnight_still_ends_the_day_after(self) -> None:
        asked = TimedBounds(_wall(27, 23, 0), _wall(28, 1, 0))

        assert series_bounds(date(2026, 11, 2), asked) == TimedBounds(
            _wall(2, 23, 0), _wall(3, 1, 0)
        )

    def test_an_occurrence_across_a_clock_change_gives_the_series_the_times_it_shows(self) -> None:
        # Paris, 25 October 2026: that night is an hour longer. Eleven to four lasts
        # six hours there and five on any other night: the series shows eleven to four.
        asked = TimedBounds(
            WallTime(datetime(2026, 10, 24, 23, 0), PARIS),
            WallTime(datetime(2026, 10, 25, 4, 0), PARIS),
        )

        assert series_bounds(date(2026, 10, 3), asked) == TimedBounds(
            WallTime(datetime(2026, 10, 3, 23, 0), PARIS),
            WallTime(datetime(2026, 10, 4, 4, 0), PARIS),
        )

    def test_days_keep_how_many_they_are(self) -> None:
        asked = DayBounds(date(2026, 11, 27), date(2026, 11, 30), PARIS)

        assert series_bounds(date(2026, 11, 2), asked) == DayBounds(
            date(2026, 11, 2), date(2026, 11, 5), PARIS
        )
