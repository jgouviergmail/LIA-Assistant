"""A task's due DAY, whatever its provider kept — the one door (2026-11-07, lot 6).

Measured on Graph (2026-11-07): To Do keeps the instant of midnight in the zone it is GIVEN, and
answers it in UTC; given UTC, it keeps the UTC date. So LIA writes a day as its midnight in the
account's zone, named, and reads a To Do due as its instant in that zone. Google Tasks keeps a
date: the time part of its ``due`` is noise, read as the date it names in every zone.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from src.core.task_due import due_day, task_due_day, todo_due

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
NEW_YORK = ZoneInfo("America/New_York")
TOKYO = ZoneInfo("Asia/Tokyo")


class TestAGoogleDue:
    @pytest.mark.parametrize("zone", [PARIS, NEW_YORK, TOKYO])
    def test_is_the_date_it_names_in_every_zone(self, zone: ZoneInfo) -> None:
        assert due_day("2026-11-08T00:00:00.000Z", todo=False, zone=zone) == date(2026, 11, 8)

    def test_a_bare_date_is_that_date(self) -> None:
        assert due_day("2026-11-08", todo=False, zone=NEW_YORK) == date(2026, 11, 8)


class TestAToDoDue:
    def test_is_its_instant_read_in_the_account_zone(self) -> None:
        # Midnight in Paris, answered in UTC: the evening before, 23:00.
        assert due_day("2026-11-07T23:00:00.000Z", todo=True, zone=PARIS) == date(2026, 11, 8)

    def test_a_summer_midnight_is_read_the_same_way(self) -> None:
        assert due_day("2026-07-14T22:00:00.000Z", todo=True, zone=PARIS) == date(2026, 7, 15)

    def test_west_of_greenwich_too(self) -> None:
        assert due_day("2026-11-08T05:00:00.000Z", todo=True, zone=NEW_YORK) == date(2026, 11, 8)

    def test_an_instant_without_an_offset_is_utc(self) -> None:
        assert due_day("2026-11-07T23:00:00", todo=True, zone=PARIS) == date(2026, 11, 8)


class TestNoDue:
    @pytest.mark.parametrize("raw", [None, "", "not a date", "2026-13-45"])
    def test_reads_as_none(self, raw: str | None) -> None:
        assert due_day(raw, todo=True, zone=PARIS) is None
        assert due_day(raw, todo=False, zone=PARIS) is None


class TestANormalizedTask:
    def test_says_by_its_marker_whose_due_it_holds(self) -> None:
        todo = {"due": "2026-11-07T23:00:00.000Z", "_provider": "microsoft"}
        google = {"due": "2026-11-07T23:00:00.000Z"}

        assert task_due_day(todo, PARIS) == date(2026, 11, 8)
        assert task_due_day(google, PARIS) == date(2026, 11, 7)

    def test_without_a_due_has_no_day(self) -> None:
        assert task_due_day({"title": "Pay", "_provider": "microsoft"}, PARIS) is None


class TestAToDoWrite:
    def test_is_the_day_s_midnight_in_the_named_zone(self) -> None:
        assert todo_due(date(2026, 11, 8), PARIS) == ("2026-11-08T00:00:00", "Europe/Paris")

    def test_a_clock_change_night_keeps_its_midnight(self) -> None:
        assert todo_due(date(2026, 3, 29), PARIS) == ("2026-03-29T00:00:00", "Europe/Paris")

    def test_reads_back_as_the_same_day_once_to_do_answers_its_instant(self) -> None:
        # What To Do answers for the day written in Tokyo: its midnight, in UTC.
        assert due_day("2026-11-07T15:00:00.000Z", todo=True, zone=TOKYO) == date(2026, 11, 8)
