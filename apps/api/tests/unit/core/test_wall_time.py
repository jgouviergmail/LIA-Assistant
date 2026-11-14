"""A time on a wall never leaves the zone it is read in (ADR-380)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.wall_time import WallTime

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
KOLKATA = ZoneInfo("Asia/Kolkata")
AUCKLAND = ZoneInfo("Pacific/Auckland")


class TestReadingWhatAPersonWrote:
    def test_a_time_without_an_offset_is_that_time_on_the_zones_wall(self) -> None:
        wall = WallTime.read("2026-11-27T09:30:00", PARIS)

        assert wall.iso() == "2026-11-27T09:30:00"
        # Winter in Paris: an hour ahead of UTC — never 09:30 UTC.
        assert wall.instant() == datetime(2026, 11, 27, 8, 30, tzinfo=UTC)

    def test_the_same_wall_time_is_another_instant_in_summer(self) -> None:
        assert WallTime.read("2026-07-14T09:30:00", PARIS).instant() == datetime(
            2026, 7, 14, 7, 30, tzinfo=UTC
        )

    def test_minutes_are_enough(self) -> None:
        assert WallTime.read("2026-11-27T09:30", PARIS).iso() == "2026-11-27T09:30:00"

    @pytest.mark.parametrize(
        "written",
        [
            "2026-11-27T08:30:00Z",
            "2026-11-27T09:30:00+01:00",
            "2026-11-27T03:30:00-05:00",
            "2026-11-27T14:00:00+05:30",
            "2026-11-27T08:30:00.0000000Z",
        ],
    )
    def test_a_time_with_an_offset_is_the_instant_it_names_on_the_zones_wall(
        self, written: str
    ) -> None:
        wall = WallTime.read(written, PARIS)

        assert wall.iso() == "2026-11-27T09:30:00"
        assert wall.instant() == datetime(2026, 11, 27, 8, 30, tzinfo=UTC)

    def test_what_python_writes_for_a_wall_time_is_read_back(self) -> None:
        # Before 1911 Paris ran nine minutes and twenty-one seconds ahead of Greenwich,
        # and ``isoformat`` writes that offset to the second.
        written = datetime(1890, 6, 1, 10, 0, tzinfo=PARIS).isoformat()

        assert written.endswith("+00:09:21")
        assert WallTime.read(written, PARIS).iso() == "1890-06-01T10:00:00"

    @pytest.mark.parametrize(
        "written",
        [
            "",
            "2026-11-27",
            "tomorrow at nine",
            "2026-11-27 09:30:00",
            "20261127T093000",
            "2026-13-01T09:30:00",
            "2026-11-27T25:00:00",
            "2026-11-27T09:30:00+0100",
        ],
    )
    def test_what_is_not_a_day_and_a_time_is_refused_never_guessed(self, written: str) -> None:
        with pytest.raises(ValueError):
            WallTime.read(written, PARIS)


class TestZonesThatAreNotAWholeHourAway:
    def test_a_half_hour_zone(self) -> None:
        assert WallTime.read("2026-11-27T09:30:00", KOLKATA).instant() == datetime(
            2026, 11, 27, 4, 0, tzinfo=UTC
        )

    def test_a_zone_a_day_ahead(self) -> None:
        # Half past nine on the 27th in Auckland is still the 26th in UTC.
        assert WallTime.read("2026-11-27T09:30:00", AUCKLAND).instant() == datetime(
            2026, 11, 26, 20, 30, tzinfo=UTC
        )


class TestTheNightsTheClocksChange:
    def test_an_hour_the_clocks_skip_is_read_with_the_offset_before_the_change(self) -> None:
        # Paris, 29 March 2026: 02:00 becomes 03:00, so 02:30 never shows.
        assert WallTime.read("2026-03-29T02:30:00", PARIS).instant() == datetime(
            2026, 3, 29, 1, 30, tzinfo=UTC
        )

    def test_an_hour_the_clocks_show_twice_is_its_first_passage(self) -> None:
        # Paris, 25 October 2026: 03:00 becomes 02:00, so 02:30 shows twice.
        assert WallTime.read("2026-10-25T02:30:00", PARIS).instant() == datetime(
            2026, 10, 25, 0, 30, tzinfo=UTC
        )

    def test_an_instant_in_the_repeated_hour_keeps_which_passage_it_is(self) -> None:
        second_passage = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)

        wall = WallTime.seen_from(second_passage, PARIS)

        assert wall.iso() == "2026-10-25T02:30:00"
        assert wall.instant() == second_passage


class TestWhetherTheZoneAloneIsEnough:
    """A provider told « 02:30, Europe/Paris » places it by its own rule on those two nights."""

    @pytest.mark.parametrize(
        "written",
        [
            "2026-11-27T09:30:00",
            # The last second before the clocks jump, and the first one after.
            "2026-03-29T01:59:59",
            "2026-03-29T03:00:00",
            # The last second before the hour repeats, and the first one after it has.
            "2026-10-25T01:59:59",
            "2026-10-25T03:00:00",
        ],
    )
    def test_a_time_the_clocks_show_once_is_placed_by_its_zone(self, written: str) -> None:
        assert WallTime.read(written, PARIS).zone_suffices

    @pytest.mark.parametrize(
        "written",
        [
            "2026-03-29T02:00:00",
            "2026-03-29T02:30:00",
            "2026-03-29T02:59:59",
            "2026-10-25T02:00:00",
            "2026-10-25T02:30:00",
            "2026-10-25T02:59:59",
        ],
    )
    def test_an_hour_skipped_or_shown_twice_is_not(self, written: str) -> None:
        assert not WallTime.read(written, PARIS).zone_suffices

    def test_neither_passage_of_a_repeated_hour_is(self) -> None:
        first = WallTime.seen_from(datetime(2026, 10, 25, 0, 30, tzinfo=UTC), PARIS)
        second = WallTime.seen_from(datetime(2026, 10, 25, 1, 30, tzinfo=UTC), PARIS)

        assert (first.iso(), second.iso()) == ("2026-10-25T02:30:00", "2026-10-25T02:30:00")
        assert not first.zone_suffices
        assert not second.zone_suffices

    def test_a_zone_whose_clocks_never_change_always_suffices(self) -> None:
        assert WallTime.read("2026-10-25T02:30:00", KOLKATA).zone_suffices

    def test_the_southern_nights_are_the_other_way_round(self) -> None:
        # Auckland, 2026: the clocks go BACK on 5 April (03:00 → 02:00) and
        # FORWARD on 27 September (02:00 → 03:00).
        assert not WallTime.read("2026-04-05T02:30:00", AUCKLAND).zone_suffices
        assert not WallTime.read("2026-09-27T02:30:00", AUCKLAND).zone_suffices
        assert WallTime.read("2026-04-05T03:30:00", AUCKLAND).zone_suffices


class TestWhatItIsMadeOf:
    def test_an_instant_is_seen_on_a_wall(self) -> None:
        wall = WallTime.seen_from(datetime(2026, 11, 27, 8, 30, tzinfo=UTC), PARIS)

        assert wall == WallTime(datetime(2026, 11, 27, 9, 30), PARIS)

    def test_it_is_handed_over_with_its_zone_attached(self) -> None:
        zoned = WallTime.read("2026-11-27T09:30:00", PARIS).in_its_zone()

        assert zoned.tzinfo is PARIS
        assert zoned.utcoffset() == timedelta(hours=1)
        assert (zoned.hour, zoned.minute) == (9, 30)

    def test_a_wall_time_carries_no_offset_of_its_own(self) -> None:
        with pytest.raises(ValueError):
            WallTime(datetime(2026, 11, 27, 9, 30, tzinfo=UTC), PARIS)

    def test_an_instant_without_an_offset_is_no_instant(self) -> None:
        with pytest.raises(ValueError):
            WallTime.seen_from(datetime(2026, 11, 27, 8, 30), PARIS)
