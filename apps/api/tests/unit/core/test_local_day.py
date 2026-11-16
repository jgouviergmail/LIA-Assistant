"""A person's calendar day, as instants (ADR-148 amendment 2026-11-14).

A local day is built from the calendar, never by adding 24 hours to an
instant: 29 March lasts 23 hours in Paris, 25 October 25.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.local_day import local_day_bounds, local_midnight, local_today

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


def test_local_midnight_is_an_instant_in_utc() -> None:
    assert local_midnight(date(2026, 11, 14), PARIS) == datetime(2026, 11, 13, 23, tzinfo=UTC)
    assert local_midnight(date(2026, 7, 14), PARIS) == datetime(2026, 7, 13, 22, tzinfo=UTC)


@pytest.mark.parametrize(
    ("day", "hours"),
    [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25), (date(2026, 11, 14), 24)],
)
def test_a_day_lasts_what_the_calendar_says(day: date, hours: int) -> None:
    start, end = local_day_bounds(day, PARIS)
    assert end - start == timedelta(hours=hours)


def test_today_is_the_person_s_day_not_the_server_s() -> None:
    """At 23:30 UTC on the 13th it is already the 14th in Paris, still the 13th in New York."""
    now = datetime(2026, 11, 13, 23, 30, tzinfo=UTC)
    assert local_today(now, PARIS) == date(2026, 11, 14)
    assert local_today(now, ZoneInfo("America/New_York")) == date(2026, 11, 13)
