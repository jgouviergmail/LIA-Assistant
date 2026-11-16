"""Chart buckets at the person's clock (ADR-148 amendment 2026-11-14).

The SQL buckets (``date_trunc`` over ``timezone(<zone>, ...)``) are proven
against PostgreSQL in ``tests/integration/test_application_health_aggregate.py``;
what is pinned here is the list of buckets the chart DRAWS, which must be the
one the SQL fills: every local bucket the window touches, once, in order —
an hour the clocks skip is never drawn, an hour they repeat is drawn once.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.domains.health_metrics.chart_read import chart_bucket_starts, default_chart_window

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
KOLKATA = ZoneInfo("Asia/Kolkata")


def test_day_buckets_start_at_the_person_s_midnight() -> None:
    """48 hours from midnight UTC touch three days in Paris."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    buckets = chart_bucket_starts("day", start, start + timedelta(days=2), PARIS, maximum=10)
    assert buckets == [datetime(2026, 1, 1), datetime(2026, 1, 2), datetime(2026, 1, 3)]


def test_an_hour_the_clocks_skip_is_never_drawn() -> None:
    """29 March 2026 in Paris: 01:00 is followed by 03:00."""
    start = datetime(2026, 3, 28, 23, 0, tzinfo=UTC)  # 00:00 local
    buckets = chart_bucket_starts("hour", start, start + timedelta(hours=4), PARIS, maximum=10)
    assert buckets == [
        datetime(2026, 3, 29, 0),
        datetime(2026, 3, 29, 1),
        datetime(2026, 3, 29, 3),
        datetime(2026, 3, 29, 4),
    ]


def test_an_hour_the_clocks_repeat_is_drawn_once() -> None:
    """25 October 2026 in Paris: 02:00 happens twice, one bucket holds both."""
    start = datetime(2026, 10, 24, 23, 0, tzinfo=UTC)  # 01:00 local, summer time
    buckets = chart_bucket_starts("hour", start, start + timedelta(hours=4), PARIS, maximum=10)
    assert buckets == [
        datetime(2026, 10, 25, 1),
        datetime(2026, 10, 25, 2),
        datetime(2026, 10, 25, 3),
    ]


def test_a_half_hour_zone_draws_its_own_hours() -> None:
    """Kolkata is UTC+05:30: a window ending at :40 UTC still draws its last local hour."""
    start = datetime(2026, 11, 14, 10, 10, tzinfo=UTC)  # 15:40 local
    end = datetime(2026, 11, 14, 12, 40, tzinfo=UTC)  # 18:10 local
    buckets = chart_bucket_starts("hour", start, end, KOLKATA, maximum=10)
    assert buckets == [datetime(2026, 11, 14, hour) for hour in (15, 16, 17, 18)]


@pytest.mark.parametrize(
    ("period", "first"),
    [
        ("week", datetime(2026, 11, 9)),  # the Monday
        ("month", datetime(2026, 11, 1)),
        ("year", datetime(2026, 1, 1)),
    ],
)
def test_longer_buckets_start_on_the_local_calendar(period: str, first: datetime) -> None:
    start = datetime(2026, 11, 13, 23, 30, tzinfo=UTC)  # 14 November, 00:30 in Paris
    buckets = chart_bucket_starts(period, start, start + timedelta(hours=1), PARIS, maximum=10)
    assert buckets == [first]


def test_a_window_drawing_too_many_buckets_is_refused() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="3 buckets"):
        chart_bucket_starts("day", start, start + timedelta(days=5), PARIS, maximum=3)


def test_an_empty_window_is_refused() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="precede"):
        chart_bucket_starts("day", start, start, PARIS, maximum=3)


class TestDefaultChartWindow:
    """What a chart covers when the caller leaves bounds out."""

    def test_the_first_bucket_is_whole(self) -> None:
        """Seven days back from 15:30, moved to that day's local midnight."""
        now = datetime(2026, 11, 14, 15, 30, tzinfo=UTC)
        start, end = default_chart_window("day", zone=PARIS, now=now)
        assert end == now
        assert start == datetime(2026, 11, 7, tzinfo=PARIS).astimezone(UTC)

    def test_the_caller_s_bounds_are_kept(self) -> None:
        now = datetime(2026, 11, 14, 15, 30, tzinfo=UTC)
        asked = datetime(2026, 11, 10, 7, 45, tzinfo=UTC)
        assert default_chart_window("day", zone=PARIS, now=now, from_ts=asked) == (asked, now)
