"""Pure-logic tests for PeersRepository helpers (peers program, Lot 1, Task 5)."""

from datetime import UTC, datetime

import pytest

from src.domains.peers.repository import utc_day_bounds


@pytest.mark.unit
class TestUtcDayBounds:
    """Quota windows are UTC calendar days (spec §4.2)."""

    def test_covers_the_whole_utc_day(self):
        now = datetime(2026, 7, 29, 23, 59, 59, tzinfo=UTC)
        start, end = utc_day_bounds(now)
        assert start == datetime(2026, 7, 29, 0, 0, 0, tzinfo=UTC)
        assert end == datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)

    def test_midnight_belongs_to_the_new_day(self):
        now = datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)
        start, _end = utc_day_bounds(now)
        assert start == datetime(2026, 7, 30, 0, 0, 0, tzinfo=UTC)

    def test_bounds_are_timezone_aware_utc(self):
        start, end = utc_day_bounds(datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))
        assert start.tzinfo is UTC
        assert end.tzinfo is UTC
