"""Unit tests for baseline.py + signals.py.

Covers:

- Per-day aggregation via ``_daily_aggregate`` for every supported
  ``BaselineKind``.
- Adaptive baseline mode selection (empty / bootstrap / rolling).
- ``_find_longest_trend_streak`` — boundary and direction cases.
- ``detect_recent_variations`` — notable vs below-threshold scenarios.
- ``detect_notable_events`` — inactivity streak detection for steps.

Fixtures build synthetic ``HealthSample`` lists in memory without DB.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.domains.health_metrics.baseline import (
    _daily_aggregate,
    _group_samples_by_day,
    baseline_window_start,
    compute_baseline,
)
from src.domains.health_metrics.kinds import HEALTH_KINDS, BaselineKind
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.signals import (
    _find_longest_trend_streak,
    detect_notable_events,
    detect_recent_variations,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Fixtures / helpers
# =============================================================================


def _make_sample(
    kind: str,
    date_start: datetime,
    value: int,
) -> HealthSample:
    """Build a detached HealthSample in memory (no DB session required)."""
    return HealthSample(
        id=uuid4(),
        user_id=uuid4(),
        kind=kind,
        date_start=date_start,
        date_end=date_start + timedelta(minutes=5),
        value=value,
        source="test",
    )


def _days_ago(n: int) -> datetime:
    """Return a UTC datetime at the start of the day N days before now."""
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    return now - timedelta(days=n)


# =============================================================================
# _daily_aggregate
# =============================================================================


class TestDailyAggregate:
    """Per-day aggregation respects the baseline kind."""

    def test_empty_returns_empty(self) -> None:
        assert _daily_aggregate([], BaselineKind.DAILY_SUM) == []

    def test_daily_sum(self) -> None:
        """Multiple steps samples on the same day sum to the daily total."""
        day = _days_ago(1)
        samples = [
            _make_sample("steps", day, 100),
            _make_sample("steps", day.replace(hour=14), 200),
            _make_sample("steps", day.replace(hour=20), 300),
        ]
        result = _daily_aggregate(samples, BaselineKind.DAILY_SUM)
        assert result == [600.0]

    def test_daily_avg(self) -> None:
        """Multiple HR samples on the same day average into the daily mean."""
        day = _days_ago(1)
        samples = [
            _make_sample("heart_rate", day, 60),
            _make_sample("heart_rate", day.replace(hour=14), 80),
            _make_sample("heart_rate", day.replace(hour=20), 100),
        ]
        result = _daily_aggregate(samples, BaselineKind.DAILY_AVG)
        assert result == [80.0]

    def test_multi_day_sorted(self) -> None:
        """Output order is ascending by day regardless of input order."""
        s_today = _make_sample("steps", _days_ago(0), 1000)
        s_yesterday = _make_sample("steps", _days_ago(1), 500)
        result = _daily_aggregate([s_today, s_yesterday], BaselineKind.DAILY_SUM)
        assert result == [500.0, 1000.0]


# =============================================================================
# compute_baseline — adaptive mode
# =============================================================================


class TestComputeBaseline:
    """Adaptive mode selection between bootstrap and rolling."""

    def test_empty_yields_empty_mode(self) -> None:
        spec = HEALTH_KINDS["steps"]
        result = compute_baseline([], spec)
        assert result.mode == "empty"
        assert result.median_value is None
        assert result.days_available == 0

    def test_bootstrap_when_few_days(self) -> None:
        """Below the min-days threshold → bootstrap mode."""
        spec = HEALTH_KINDS["steps"]
        samples = [
            _make_sample("steps", _days_ago(2), 5000),
            _make_sample("steps", _days_ago(1), 7000),
            _make_sample("steps", _days_ago(0), 9000),
        ]
        result = compute_baseline(samples, spec)
        assert result.mode == "bootstrap"
        assert result.median_value == 7000.0
        assert result.days_available == 3

    def test_rolling_when_enough_history(self) -> None:
        """At or above the min-days threshold (default 7) → rolling mode."""
        spec = HEALTH_KINDS["heart_rate"]
        samples = [_make_sample("heart_rate", _days_ago(i), 60 + i) for i in range(10)]
        result = compute_baseline(samples, spec)
        assert result.mode == "rolling"
        assert result.median_value is not None
        assert result.days_available == 10

    def test_baseline_window_start_returns_utc(self) -> None:
        now = datetime.now(UTC)
        start = baseline_window_start(now)
        assert start.tzinfo is not None
        # Default is rolling_window + 1 day margin = 29 days
        assert (now - start) >= timedelta(days=28)


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
        today = _days_ago(0).date()
        deltas = [
            (today - timedelta(days=2), 15.0),
            (today - timedelta(days=1), 20.0),
            (today, 25.0),
        ]
        trend, days, avg = _find_longest_trend_streak(deltas, min_daily_delta=10.0)
        assert trend == "rising"
        assert days == 3
        assert avg == pytest.approx(20.0)

    def test_falling_streak(self) -> None:
        """Three consecutive days below -10% threshold → falling."""
        today = _days_ago(0).date()
        deltas = [
            (today - timedelta(days=2), -15.0),
            (today - timedelta(days=1), -20.0),
            (today, -25.0),
        ]
        trend, days, avg = _find_longest_trend_streak(deltas, min_daily_delta=10.0)
        assert trend == "falling"
        assert days == 3
        assert avg == pytest.approx(-20.0)

    def test_stable_day_breaks_streak(self) -> None:
        """A day within ±threshold resets the streak."""
        today = _days_ago(0).date()
        deltas = [
            (today - timedelta(days=3), 15.0),
            (today - timedelta(days=2), 5.0),  # stable, breaks
            (today - timedelta(days=1), 20.0),
            (today, 25.0),
        ]
        trend, days, avg = _find_longest_trend_streak(deltas, min_daily_delta=10.0)
        assert trend == "rising"
        assert days == 2
        assert avg == pytest.approx(22.5)


# =============================================================================
# detect_recent_variations — integration
# =============================================================================


class TestDetectRecentVariations:
    """End-to-end detection on synthetic data."""

    def test_no_data_returns_none(self) -> None:
        spec = HEALTH_KINDS["steps"]
        assert detect_recent_variations([], spec) is None

    def test_stable_data_returns_none(self) -> None:
        """All days near baseline → not notable."""
        spec = HEALTH_KINDS["steps"]
        # 14 days all ~8000 steps
        samples = [_make_sample("steps", _days_ago(i), 8000) for i in range(14)]
        assert detect_recent_variations(samples, spec, window_days=7) is None

    def test_falling_trend_notable(self) -> None:
        """Clear 4-day drop → notable variation (above 20% avg threshold)."""
        spec = HEALTH_KINDS["steps"]
        # 20 baseline days at 10 000 + 4 recent days at 5 000 (−50 %)
        baseline = [_make_sample("steps", _days_ago(i), 10000) for i in range(10, 30)]
        window = [_make_sample("steps", _days_ago(i), 5000) for i in range(4)]
        samples = baseline + window

        result = detect_recent_variations(samples, spec, window_days=7)
        assert result is not None
        assert result["kind"] == "steps"
        assert result["trend"] == "falling"
        assert result["days"] >= 3
        assert result["delta_pct"] < -20.0
        assert result["notable"] is True


# =============================================================================
# detect_notable_events — inactivity
# =============================================================================


class TestDetectNotableEvents:
    """Structural event detection."""

    def test_no_inactivity_returns_empty(self) -> None:
        spec = HEALTH_KINDS["steps"]
        samples = [_make_sample("steps", _days_ago(i), 5000) for i in range(7)]
        assert detect_notable_events(samples, spec) == []

    def test_inactivity_streak_flagged(self) -> None:
        """Three consecutive days with 0 steps → inactivity event."""
        spec = HEALTH_KINDS["steps"]
        samples = [_make_sample("steps", _days_ago(i), 0) for i in range(3)]
        events = detect_notable_events(samples, spec)
        assert len(events) == 1
        assert events[0]["event"] == "inactivity_streak"
        assert events[0]["kind"] == "steps"
        assert events[0]["days"] >= 3

    def test_inactivity_not_flagged_for_non_steps_kind(self) -> None:
        """HR kind has no inactivity concept in v1.17.2."""
        spec = HEALTH_KINDS["heart_rate"]
        samples = [_make_sample("heart_rate", _days_ago(i), 70) for i in range(3)]
        # HR inactivity event isn't defined — helper returns []
        assert detect_notable_events(samples, spec) == []


# =============================================================================
# _group_samples_by_day
# =============================================================================


class TestGroupSamplesByDay:
    """Grouping uses UTC-date of ``date_start``."""

    def test_different_hours_same_day(self) -> None:
        """Two samples at different hours on the same UTC day group together."""
        day = _days_ago(1)
        samples = [
            _make_sample("steps", day.replace(hour=1), 100),
            _make_sample("steps", day.replace(hour=23), 200),
        ]
        result = _group_samples_by_day(samples)
        assert len(result) == 1
        values = next(iter(result.values()))
        assert sorted(values) == [100, 200]
