"""Unit tests for baseline.py + signals.py.

Covers:

- Per-day reduction via ``daily_values`` for every supported ``BaselineKind``.
- Adaptive baseline mode selection (empty / bootstrap / rolling).
- ``baseline_window_start`` — the person's midnight, every day whole.
- ``_find_longest_trend_streak`` — boundary and direction cases.
- ``detect_recent_variations_from_stats`` — notable vs below-threshold.
- ``detect_notable_events_from_stats`` — inactivity streaks for steps, read
  against the person's local day.

Every detector consumes the per-local-day series the repository rollup
returns (ADR-148 amendment 2026-11-14); the series are built in memory.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.core.constants import HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS
from src.domains.health_metrics.baseline import (
    DailyStat,
    baseline_window_start,
    compute_baseline_from_stats,
    daily_values,
)
from src.domains.health_metrics.kinds import HEALTH_KINDS, BaselineKind
from src.domains.health_metrics.signals import (
    _find_longest_trend_streak,
    detect_notable_events_from_stats,
    detect_recent_variations_from_stats,
)

pytestmark = pytest.mark.unit

TODAY = date(2026, 11, 14)
PARIS = ZoneInfo("Europe/Paris")


def _stat(days_ago: int, total: int, count: int = 1, minimum: int | None = None) -> DailyStat:
    """One local day of the series, ``days_ago`` days before ``TODAY``."""
    return DailyStat(
        day=TODAY - timedelta(days=days_ago),
        total=total,
        count=count,
        minimum=total if minimum is None else minimum,
    )


def _series(*stats: DailyStat) -> list[DailyStat]:
    """A day-ascending series, as the rollup returns it."""
    return sorted(stats, key=lambda stat: stat.day)


# =============================================================================
# daily_values
# =============================================================================


class TestDailyValues:
    """Per-day reduction respects the baseline kind."""

    def test_empty_returns_empty(self) -> None:
        assert daily_values([], BaselineKind.DAILY_SUM) == []

    def test_daily_sum_is_the_counted_total(self) -> None:
        assert daily_values([_stat(1, 600, count=3)], BaselineKind.DAILY_SUM) == [600.0]

    def test_daily_avg_divides_by_the_counted_rows(self) -> None:
        """Three readings of 60, 80 and 100 average to 80."""
        assert daily_values([_stat(1, 240, count=3)], BaselineKind.DAILY_AVG) == [80.0]

    def test_resting_reads_the_minimum(self) -> None:
        assert daily_values([_stat(1, 240, count=3, minimum=55)], BaselineKind.RESTING) == [55.0]

    def test_order_is_preserved(self) -> None:
        series = _series(_stat(0, 1000), _stat(1, 500))
        assert daily_values(series, BaselineKind.DAILY_SUM) == [500.0, 1000.0]


# =============================================================================
# compute_baseline_from_stats — adaptive mode
# =============================================================================


class TestComputeBaseline:
    """Adaptive mode selection between bootstrap and rolling."""

    def test_empty_yields_empty_mode(self) -> None:
        result = compute_baseline_from_stats([], HEALTH_KINDS["steps"])
        assert result.mode == "empty"
        assert result.median_value is None
        assert result.days_available == 0

    def test_bootstrap_when_few_days(self) -> None:
        """Below the min-days threshold → bootstrap mode."""
        series = _series(_stat(2, 5000), _stat(1, 7000), _stat(0, 9000))
        result = compute_baseline_from_stats(series, HEALTH_KINDS["steps"])
        assert result.mode == "bootstrap"
        assert result.median_value == 7000.0
        assert result.days_available == 3

    def test_rolling_when_enough_history(self) -> None:
        """At or above the min-days threshold (default 7) → rolling mode."""
        series = _series(*(_stat(i, 60 + i) for i in range(10)))
        result = compute_baseline_from_stats(series, HEALTH_KINDS["heart_rate"])
        assert result.mode == "rolling"
        assert result.median_value is not None
        assert result.days_available == 10


class TestBaselineWindowStart:
    """The read starts at the person's midnight, the rolling window whole."""

    @pytest.mark.parametrize("recent_days", [0, 7])
    def test_it_is_a_local_midnight_that_many_days_back(self, recent_days: int) -> None:
        now = datetime(2026, 11, 14, 15, 30, tzinfo=UTC)
        start = baseline_window_start(now, PARIS, recent_days=recent_days)

        local = start.astimezone(PARIS)
        assert (local.hour, local.minute) == (0, 0)
        expected_days = HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS + 1 + recent_days
        assert local.date() == TODAY - timedelta(days=expected_days)
        assert start.tzinfo is UTC

    def test_a_day_a_clock_change_shortened_is_still_counted_whole(self) -> None:
        """29 March 2026 lasts 23 hours in Paris; the read starts at its midnight."""
        now = datetime(2026, 4, 27, 8, 0, tzinfo=UTC)  # 27 April, 29 days after
        start = baseline_window_start(now, PARIS, recent_days=0)
        assert start.astimezone(PARIS).replace(tzinfo=None) == datetime(2026, 3, 29)
        # That midnight is still on winter time: 23:00 UTC the day before.
        assert start == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)

    def test_the_day_is_the_person_s_not_the_server_s(self) -> None:
        """At 00:30 in Auckland it is still yesterday in UTC."""
        now = datetime(2026, 11, 14, 11, 30, tzinfo=UTC)  # 00:30 on the 15th in Auckland
        auckland = ZoneInfo("Pacific/Auckland")
        start = baseline_window_start(now, auckland, recent_days=0)
        expected = date(2026, 11, 15) - timedelta(
            days=HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS + 1
        )
        assert start.astimezone(auckland).date() == expected


# =============================================================================
# _find_longest_trend_streak
# =============================================================================


class TestFindLongestTrendStreak:
    """Streak detection with directional and threshold semantics."""

    def test_empty_returns_stable(self) -> None:
        trend, days, avg = _find_longest_trend_streak([], min_daily_delta=10.0)
        assert (trend, days, avg) == ("stable", 0, 0.0)

    def test_rising_streak(self) -> None:
        """Three consecutive days above +10% threshold → rising, 3, avg."""
        deltas = [
            (TODAY - timedelta(days=2), 15.0),
            (TODAY - timedelta(days=1), 20.0),
            (TODAY, 25.0),
        ]
        trend, days, avg = _find_longest_trend_streak(deltas, min_daily_delta=10.0)
        assert trend == "rising"
        assert days == 3
        assert avg == pytest.approx(20.0)

    def test_falling_streak(self) -> None:
        """Three consecutive days below -10% threshold → falling."""
        deltas = [
            (TODAY - timedelta(days=2), -15.0),
            (TODAY - timedelta(days=1), -20.0),
            (TODAY, -25.0),
        ]
        trend, days, avg = _find_longest_trend_streak(deltas, min_daily_delta=10.0)
        assert trend == "falling"
        assert days == 3
        assert avg == pytest.approx(-20.0)

    def test_stable_day_breaks_streak(self) -> None:
        """A day within ±threshold resets the streak."""
        deltas = [
            (TODAY - timedelta(days=3), 15.0),
            (TODAY - timedelta(days=2), 5.0),  # stable, breaks
            (TODAY - timedelta(days=1), 20.0),
            (TODAY, 25.0),
        ]
        trend, days, avg = _find_longest_trend_streak(deltas, min_daily_delta=10.0)
        assert trend == "rising"
        assert days == 2
        assert avg == pytest.approx(22.5)


# =============================================================================
# detect_recent_variations_from_stats
# =============================================================================


class TestDetectRecentVariations:
    """End-to-end detection on synthetic series."""

    def test_no_data_returns_none(self) -> None:
        assert detect_recent_variations_from_stats([], HEALTH_KINDS["steps"]) is None

    def test_stable_data_returns_none(self) -> None:
        """All days near baseline → not notable."""
        series = _series(*(_stat(i, 8000) for i in range(14)))
        assert detect_recent_variations_from_stats(series, HEALTH_KINDS["steps"], 7) is None

    def test_falling_trend_notable(self) -> None:
        """Clear 4-day drop → notable variation (above 20% avg threshold)."""
        # 20 baseline days at 10 000 + 4 recent days at 5 000 (−50 %)
        series = _series(
            *(_stat(i, 10000) for i in range(10, 30)), *(_stat(i, 5000) for i in range(4))
        )
        result = detect_recent_variations_from_stats(series, HEALTH_KINDS["steps"], window_days=7)
        assert result is not None
        assert result["kind"] == "steps"
        assert result["trend"] == "falling"
        assert result["days"] >= 3
        assert result["delta_pct"] < -20.0
        assert result["notable"] is True


# =============================================================================
# detect_notable_events_from_stats — inactivity
# =============================================================================


class TestDetectNotableEvents:
    """Structural event detection, read against the person's day."""

    def test_no_inactivity_returns_empty(self) -> None:
        series = _series(*(_stat(i, 5000) for i in range(7)))
        assert detect_notable_events_from_stats(series, HEALTH_KINDS["steps"], today=TODAY) == []

    def test_inactivity_streak_flagged(self) -> None:
        """Three consecutive days with 0 steps → inactivity event."""
        series = _series(*(_stat(i, 0) for i in range(3)))
        events = detect_notable_events_from_stats(series, HEALTH_KINDS["steps"], today=TODAY)
        assert events == [{"event": "inactivity_streak", "kind": "steps", "days": 3}]

    def test_days_older_than_the_window_are_not_read(self) -> None:
        """The window is counted back from the person's today, not the server's."""
        series = _series(*(_stat(i, 0) for i in range(8, 11)), _stat(0, 4000))
        assert (
            detect_notable_events_from_stats(
                series, HEALTH_KINDS["steps"], today=TODAY, window_days=7
            )
            == []
        )

    def test_inactivity_not_flagged_for_non_steps_kind(self) -> None:
        """HR kind has no inactivity concept."""
        series = _series(*(_stat(i, 0) for i in range(3)))
        assert (
            detect_notable_events_from_stats(series, HEALTH_KINDS["heart_rate"], today=TODAY) == []
        )
