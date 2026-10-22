"""Quota days follow civil midnight, including 23/25 hour DST days."""

from datetime import UTC, datetime

import pytest

from src.domains.proactive_discussions.day_window import local_day_utc_bounds

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "moment,timezone,start,end",
    [
        (
            "2026-03-08T16:00:00+00:00",
            "America/New_York",
            "2026-03-08T05:00:00+00:00",
            "2026-03-09T04:00:00+00:00",
        ),
        (
            "2026-11-01T16:00:00+00:00",
            "America/New_York",
            "2026-11-01T04:00:00+00:00",
            "2026-11-02T05:00:00+00:00",
        ),
        (
            "2026-10-20T00:00:00+00:00",
            "UTC",
            "2026-10-20T00:00:00+00:00",
            "2026-10-21T00:00:00+00:00",
        ),
    ],
)
def test_local_day_bounds(moment: str, timezone: str, start: str, end: str) -> None:
    assert local_day_utc_bounds(datetime.fromisoformat(moment), timezone) == (
        datetime.fromisoformat(start).astimezone(UTC),
        datetime.fromisoformat(end).astimezone(UTC),
    )
