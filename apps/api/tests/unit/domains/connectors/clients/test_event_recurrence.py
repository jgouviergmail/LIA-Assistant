"""A repeating event on the three calendars (ADR-369, lot 10).

One spec, the one every recurrence of LIA is (``core/recurrence``): Google and iCloud take an
RRULE, Graph a ``patternedRecurrence``. What Graph cannot hold is refused by name, never held
differently: a day of the month it would skip is not the day the person asked for.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
import vobject

from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay
from src.domains.connectors.clients.calendar_options import (
    EventOptions,
    apply_ical_options,
    google_options,
    graph_options,
)
from src.domains.connectors.clients.event_recurrence import (
    RecurrenceNotHeldError,
    graph_recurrence,
    rrule_of,
)

pytestmark = pytest.mark.unit

ZONE = "Europe/Paris"
START = date(2027, 1, 4)  # A Monday.


def _spec(freq: str, **fields: Any) -> RecurrenceSpec:
    return RecurrenceSpec(
        freq=freq,
        times=DailyTimes(mode="at", at=[TimeOfDay(hour=9, minute=0)]),
        anchor_date=fields.pop("anchor_date", START),
        **fields,
    )


class TestAnRrule:
    @pytest.mark.parametrize(
        ("fields", "rule"),
        [
            ({"freq": "daily"}, "RRULE:FREQ=DAILY"),
            ({"freq": "daily", "interval": 3}, "RRULE:FREQ=DAILY;INTERVAL=3"),
            ({"freq": "weekly", "byweekday": (1, 3)}, "RRULE:FREQ=WEEKLY;BYDAY=MO,WE"),
            (
                {"freq": "weekly", "byweekday": (7,), "interval": 2},
                "RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=SU",
            ),
            ({"freq": "monthly", "bymonthday": (15,)}, "RRULE:FREQ=MONTHLY;BYMONTHDAY=15"),
            ({"freq": "monthly", "bymonthday": (-1,)}, "RRULE:FREQ=MONTHLY;BYMONTHDAY=-1"),
            ({"freq": "monthly", "nth_weekday": (2, 2)}, "RRULE:FREQ=MONTHLY;BYDAY=2TU"),
            ({"freq": "monthly", "nth_weekday": (-1, 5)}, "RRULE:FREQ=MONTHLY;BYDAY=-1FR"),
            (
                {"freq": "yearly", "bymonth": (5,), "bymonthday": (15,)},
                "RRULE:FREQ=YEARLY;BYMONTH=5;BYMONTHDAY=15",
            ),
        ],
    )
    def test_each_shape_is_said(self, fields: dict[str, Any], rule: str) -> None:
        assert rrule_of(_spec(**fields), zone=ZONE, all_day=False) == rule

    def test_a_count_is_its_number(self) -> None:
        spec = _spec("daily", end=SeriesEnd(kind="after_count", after_count=5))

        assert rrule_of(spec, zone=ZONE, all_day=False) == "RRULE:FREQ=DAILY;COUNT=5"

    def test_an_all_day_series_ends_on_a_day(self) -> None:
        spec = _spec("daily", end=SeriesEnd(kind="on_date", on_date=date(2027, 1, 31)))

        assert rrule_of(spec, zone=ZONE, all_day=True) == "RRULE:FREQ=DAILY;UNTIL=20270131"

    def test_a_timed_series_ends_with_its_last_local_day_in_utc(self) -> None:
        spec = _spec("daily", end=SeriesEnd(kind="on_date", on_date=date(2027, 1, 31)))

        assert rrule_of(spec, zone=ZONE, all_day=False) == (
            "RRULE:FREQ=DAILY;UNTIL=20270131T225959Z"
        )

    def test_a_summer_day_ends_two_hours_before_utc_midnight(self) -> None:
        spec = _spec("daily", end=SeriesEnd(kind="on_date", on_date=date(2027, 7, 31)))

        assert rrule_of(spec, zone=ZONE, all_day=False).endswith("UNTIL=20270731T215959Z")

    def test_once_is_no_series(self) -> None:
        with pytest.raises(RecurrenceNotHeldError):
            rrule_of(_spec("once"), zone=ZONE, all_day=False)


class TestAGraphRecurrence:
    def test_a_day_after_day_series(self) -> None:
        answer = graph_recurrence(_spec("daily", interval=2), zone=ZONE)

        assert answer["pattern"] == {"type": "daily", "interval": 2}
        assert answer["range"] == {
            "type": "noEnd",
            "startDate": "2027-01-04",
            "recurrenceTimeZone": ZONE,
        }

    def test_a_weekly_one_names_its_days_and_the_week_s_first(self) -> None:
        answer = graph_recurrence(_spec("weekly", byweekday=(1, 7)), zone=ZONE)

        assert answer["pattern"] == {
            "type": "weekly",
            "interval": 1,
            "daysOfWeek": ["monday", "sunday"],
            "firstDayOfWeek": "monday",
        }

    def test_a_day_of_the_month(self) -> None:
        answer = graph_recurrence(_spec("monthly", bymonthday=(15,)), zone=ZONE)

        assert answer["pattern"] == {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": 15}

    @pytest.mark.parametrize(
        ("nth", "index"),
        [((1, 2), "first"), ((2, 2), "second"), ((4, 2), "fourth"), ((-1, 2), "last")],
    )
    def test_a_weekday_of_the_month(self, nth: tuple[int, int], index: str) -> None:
        answer = graph_recurrence(_spec("monthly", nth_weekday=nth), zone=ZONE)

        assert answer["pattern"] == {
            "type": "relativeMonthly",
            "interval": 1,
            "daysOfWeek": ["tuesday"],
            "index": index,
        }

    def test_a_day_of_the_year(self) -> None:
        answer = graph_recurrence(_spec("yearly", bymonth=(5,), bymonthday=(15,)), zone=ZONE)

        assert answer["pattern"] == {
            "type": "absoluteYearly",
            "interval": 1,
            "month": 5,
            "dayOfMonth": 15,
        }

    def test_a_count(self) -> None:
        spec = _spec("daily", end=SeriesEnd(kind="after_count", after_count=5))

        assert graph_recurrence(spec, zone=ZONE)["range"] == {
            "type": "numbered",
            "numberOfOccurrences": 5,
            "startDate": "2027-01-04",
            "recurrenceTimeZone": ZONE,
        }

    def test_a_last_day(self) -> None:
        spec = _spec("daily", end=SeriesEnd(kind="on_date", on_date=date(2027, 1, 31)))

        assert graph_recurrence(spec, zone=ZONE)["range"] == {
            "type": "endDate",
            "endDate": "2027-01-31",
            "startDate": "2027-01-04",
            "recurrenceTimeZone": ZONE,
        }

    @pytest.mark.parametrize(
        "fields",
        [
            {"freq": "monthly", "bymonthday": (-1,)},
            {"freq": "monthly", "bymonthday": (1, 15)},
            {"freq": "monthly", "nth_weekday": (5, 2)},
            {"freq": "yearly", "bymonth": (1, 7), "bymonthday": (15,)},
            {"freq": "yearly", "bymonth": (5,), "bymonthday": (1, 15)},
            {"freq": "once"},
        ],
    )
    def test_what_it_cannot_hold_is_refused_by_name(self, fields: dict[str, Any]) -> None:
        with pytest.raises(RecurrenceNotHeldError):
            graph_recurrence(_spec(**fields), zone=ZONE)


class TestTheOptions:
    spec = _spec("weekly", byweekday=(1,))

    def test_google_takes_the_rule_as_a_list(self) -> None:
        body = google_options(EventOptions(recurrence=self.spec, zone=ZONE))

        assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"]

    def test_graph_takes_its_pattern(self) -> None:
        body = graph_options(EventOptions(recurrence=self.spec, zone=ZONE))

        assert body["recurrence"]["pattern"]["daysOfWeek"] == ["monday"]

    def test_a_card_takes_its_line_and_replaces_the_one_it_had(self) -> None:
        calendar = vobject.iCalendar()
        vevent = calendar.add("vevent")
        vevent.add("rrule").value = "FREQ=DAILY"

        apply_ical_options(vevent, EventOptions(recurrence=self.spec, zone=ZONE))

        assert [line.value for line in vevent.contents["rrule"]] == ["FREQ=WEEKLY;BYDAY=MO"]

    def test_nothing_named_is_nothing_said(self) -> None:
        assert "recurrence" not in google_options(EventOptions())
        assert "recurrence" not in graph_options(EventOptions())
