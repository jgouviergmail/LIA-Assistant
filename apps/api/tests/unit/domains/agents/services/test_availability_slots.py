"""Pure free-slot computation (lot B, 2026-08).

The slot finder is the oracle behind "find me a 30-min slot Thursday":
its edge cases (overlapping busy blocks, busy crossing the window edges,
working-hours clamping across days and DST) decide the answer the user
gets — so they are pinned exhaustively here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.domains.agents.services.availability_slots import (
    busy_intervals_from_events,
    busy_intervals_from_freebusy,
    find_free_slots,
    merge_intervals,
)

pytestmark = pytest.mark.unit


def _dt(hour: int, minute: int = 0, day: int = 27) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


class TestMergeIntervals:
    def test_overlapping_and_adjacent_intervals_merge(self) -> None:
        merged = merge_intervals([(_dt(10), _dt(11)), (_dt(10, 30), _dt(12)), (_dt(12), _dt(13))])
        assert merged == [(_dt(10), _dt(13))]

    def test_disjoint_intervals_stay_separate_and_sorted(self) -> None:
        merged = merge_intervals([(_dt(15), _dt(16)), (_dt(9), _dt(10))])
        assert merged == [(_dt(9), _dt(10)), (_dt(15), _dt(16))]

    def test_empty_input(self) -> None:
        assert merge_intervals([]) == []


class TestFindFreeSlots:
    def test_gaps_of_sufficient_duration_are_returned(self) -> None:
        slots = find_free_slots(
            busy=[(_dt(10), _dt(11)), (_dt(14), _dt(15))],
            window_start=_dt(9),
            window_end=_dt(17),
            duration_minutes=60,
        )
        assert slots == [(_dt(9), _dt(10)), (_dt(11), _dt(14)), (_dt(15), _dt(17))]

    def test_gaps_shorter_than_duration_are_dropped(self) -> None:
        slots = find_free_slots(
            busy=[(_dt(9, 30), _dt(16, 45))],
            window_start=_dt(9),
            window_end=_dt(17),
            duration_minutes=60,
        )
        assert slots == []

    def test_all_free_window(self) -> None:
        slots = find_free_slots(
            busy=[], window_start=_dt(9), window_end=_dt(17), duration_minutes=30
        )
        assert slots == [(_dt(9), _dt(17))]

    def test_busy_crossing_window_edges_is_clamped(self) -> None:
        slots = find_free_slots(
            busy=[(_dt(7), _dt(10)), (_dt(16), _dt(19))],
            window_start=_dt(9),
            window_end=_dt(17),
            duration_minutes=30,
        )
        assert slots == [(_dt(10), _dt(16))]

    def test_fully_busy_window(self) -> None:
        slots = find_free_slots(
            busy=[(_dt(8), _dt(18))],
            window_start=_dt(9),
            window_end=_dt(17),
            duration_minutes=15,
        )
        assert slots == []

    def test_max_slots_caps_the_result(self) -> None:
        busy = [(_dt(h), _dt(h, 30)) for h in range(9, 17)]
        slots = find_free_slots(
            busy=busy,
            window_start=_dt(9),
            window_end=_dt(17),
            duration_minutes=15,
            max_slots=3,
        )
        assert len(slots) == 3

    def test_working_hours_clamp_spans_days_in_user_timezone(self) -> None:
        """A two-day window keeps only [9h, 18h] Paris time on EACH day."""
        paris = ZoneInfo("Europe/Paris")
        window_start = datetime(2026, 8, 27, 0, 0, tzinfo=paris)
        window_end = datetime(2026, 8, 29, 0, 0, tzinfo=paris)
        slots = find_free_slots(
            busy=[],
            window_start=window_start,
            window_end=window_end,
            duration_minutes=60,
            working_hours=(9, 18),
            timezone_name="Europe/Paris",
        )
        assert slots == [
            (
                datetime(2026, 8, 27, 9, 0, tzinfo=paris),
                datetime(2026, 8, 27, 18, 0, tzinfo=paris),
            ),
            (
                datetime(2026, 8, 28, 9, 0, tzinfo=paris),
                datetime(2026, 8, 28, 18, 0, tzinfo=paris),
            ),
        ]


class TestBusyIntervalExtraction:
    def test_freebusy_response_intervals(self) -> None:
        intervals = busy_intervals_from_freebusy(
            {
                "calendars": {
                    "primary": {
                        "busy": [{"start": "2026-08-27T10:00:00Z", "end": "2026-08-27T11:00:00Z"}]
                    },
                    "team": {
                        "busy": [
                            {
                                "start": "2026-08-27T14:00:00+02:00",
                                "end": "2026-08-27T15:00:00+02:00",
                            }
                        ]
                    },
                }
            }
        )
        assert intervals[0] == (_dt(10), _dt(11))
        assert len(intervals) == 2

    def test_events_projection_intervals_skip_unparseable(self) -> None:
        intervals = busy_intervals_from_events(
            [
                {
                    "start": {"dateTime": "2026-08-27T10:00:00Z"},
                    "end": {"dateTime": "2026-08-27T11:00:00Z"},
                },
                {"start": {"date": "2026-08-28"}, "end": {"date": "2026-08-29"}},
                {"start": {}, "end": {}},
            ]
        )
        # Timed event kept; all-day event kept as a full-day block; junk skipped.
        assert intervals[0] == (_dt(10), _dt(11))
        assert intervals[1][0].date().isoformat() == "2026-08-28"
        assert len(intervals) == 2
