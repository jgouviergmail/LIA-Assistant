"""Unit tests for the Health Metrics aggregator.

Covers:
- Bucket flooring and advancement for every supported period
- Empty-bucket gap preservation (``has_data=False``)
- Per-bucket step total derivation (simple SUM)
- Heart rate aggregation (avg/min/max)
- Period-wide averages across multi-day windows
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.domains.health_metrics.aggregator import aggregate_metrics
from src.domains.health_metrics.models import HealthMetric

pytestmark = pytest.mark.unit


# =============================================================================
# Helpers
# =============================================================================


def _make_metric(
    recorded_at: datetime,
    heart_rate: int | None = None,
    steps: int | None = None,
) -> HealthMetric:
    """Build a HealthMetric instance for tests (no DB persistence)."""
    return HealthMetric(
        id=uuid4(),
        user_id=uuid4(),
        recorded_at=recorded_at,
        heart_rate=heart_rate,
        steps=steps,
        source="test",
    )


# =============================================================================
# Gap preservation
# =============================================================================


class TestGapPreservation:
    """Empty buckets must be emitted so the frontend can render gaps."""

    def test_empty_window_produces_empty_buckets(self) -> None:
        """A window with no samples still yields one point per bucket slot."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
        points, averages = aggregate_metrics([], period="hour", from_ts=start, to_ts=end)
        assert len(points) == 3
        assert all(not p.has_data for p in points)
        assert averages.heart_rate_avg is None
        assert averages.steps_per_day_avg is None

    def test_scattered_samples_leave_gaps(self) -> None:
        """Only buckets that contain a sample have has_data=True."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 4, 0, tzinfo=UTC)
        metrics = [
            _make_metric(datetime(2026, 1, 1, 0, 30, tzinfo=UTC), heart_rate=70, steps=100),
            # 01:00 bucket missing
            _make_metric(datetime(2026, 1, 1, 2, 15, tzinfo=UTC), heart_rate=80, steps=200),
            # 03:00 bucket missing
        ]
        points, _ = aggregate_metrics(metrics, period="hour", from_ts=start, to_ts=end)
        assert len(points) == 4
        assert [p.has_data for p in points] == [True, False, True, False]


# =============================================================================
# Heart rate aggregation
# =============================================================================


class TestHeartRateAggregation:
    """Heart rate aggregates over a bucket (avg, min, max)."""

    def test_single_bucket_multiple_samples(self) -> None:
        """Multiple HR samples within the same bucket average correctly.

        Also asserts steps_total = sum to confirm both HR and steps
        aggregations behave consistently on shared rows.
        """
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        metrics = [
            _make_metric(datetime(2026, 1, 1, 6, 0, tzinfo=UTC), heart_rate=60, steps=100),
            _make_metric(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), heart_rate=80, steps=200),
            _make_metric(datetime(2026, 1, 1, 18, 0, tzinfo=UTC), heart_rate=100, steps=300),
        ]
        points, averages = aggregate_metrics(metrics, period="day", from_ts=start, to_ts=end)
        assert len(points) == 1
        assert points[0].heart_rate_avg == 80
        assert points[0].heart_rate_min == 60
        assert points[0].heart_rate_max == 100
        assert points[0].steps_total == 600
        assert averages.heart_rate_avg == 80

    def test_null_heart_rate_ignored(self) -> None:
        """Samples with heart_rate=None do not pollute the average."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        metrics = [
            _make_metric(datetime(2026, 1, 1, 6, 0, tzinfo=UTC), heart_rate=None, steps=100),
            _make_metric(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), heart_rate=70, steps=200),
        ]
        points, _ = aggregate_metrics(metrics, period="day", from_ts=start, to_ts=end)
        assert points[0].heart_rate_avg == 70


# =============================================================================
# Step aggregation (simple SUM, since values are already per-period)
# =============================================================================


class TestStepAggregation:
    """Steps are per-sample increments — bucketing is a simple SUM."""

    def test_single_bucket_sum(self) -> None:
        """All samples in one bucket sum into steps_total."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        metrics = [
            _make_metric(datetime(2026, 1, 1, 6, 0, tzinfo=UTC), steps=500),
            _make_metric(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), steps=1500),
            _make_metric(datetime(2026, 1, 1, 18, 0, tzinfo=UTC), steps=2000),
        ]
        points, averages = aggregate_metrics(metrics, period="day", from_ts=start, to_ts=end)
        assert len(points) == 1
        assert points[0].steps_total == 4000
        assert averages.steps_per_day_avg == pytest.approx(4000.0)

    def test_multi_day_sum(self) -> None:
        """Each day bucket sums its own samples; period avg = total / days."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
        metrics = [
            # Day 1: 3000 + 4000 = 7000
            _make_metric(datetime(2026, 1, 1, 8, 0, tzinfo=UTC), steps=3000),
            _make_metric(datetime(2026, 1, 1, 20, 0, tzinfo=UTC), steps=4000),
            # Day 2: 2500 + 2500 = 5000
            _make_metric(datetime(2026, 1, 2, 8, 0, tzinfo=UTC), steps=2500),
            _make_metric(datetime(2026, 1, 2, 20, 0, tzinfo=UTC), steps=2500),
        ]
        points, averages = aggregate_metrics(metrics, period="day", from_ts=start, to_ts=end)
        assert len(points) == 2
        assert points[0].steps_total == 7000
        assert points[1].steps_total == 5000
        # 12000 steps over 2 days = 6000 / day
        assert averages.steps_per_day_avg == pytest.approx(6000.0)

    def test_null_steps_yield_none_total(self) -> None:
        """A bucket whose samples all carry steps=None gets steps_total=None."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        metrics = [
            _make_metric(datetime(2026, 1, 1, 8, 0, tzinfo=UTC), heart_rate=70, steps=None),
            _make_metric(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), heart_rate=72, steps=None),
        ]
        points, averages = aggregate_metrics(metrics, period="day", from_ts=start, to_ts=end)
        assert points[0].steps_total is None
        assert averages.steps_per_day_avg is None

    def test_partial_null_steps(self) -> None:
        """Mixed null/non-null steps in a bucket sum the valid ones only."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        metrics = [
            _make_metric(datetime(2026, 1, 1, 8, 0, tzinfo=UTC), steps=1000),
            _make_metric(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), steps=None, heart_rate=70),
            _make_metric(datetime(2026, 1, 1, 18, 0, tzinfo=UTC), steps=2000),
        ]
        points, _ = aggregate_metrics(metrics, period="day", from_ts=start, to_ts=end)
        assert points[0].steps_total == 3000


# =============================================================================
# Period buckets
# =============================================================================


class TestPeriodBuckets:
    """Each supported period floors samples consistently."""

    @pytest.mark.parametrize(
        "period, expected_buckets",
        [
            ("hour", 24),
            ("day", 1),
        ],
    )
    def test_bucket_count(self, period: str, expected_buckets: int) -> None:
        """A 24h window produces the expected number of buckets per period."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = start + timedelta(hours=24)
        points, _ = aggregate_metrics([], period=period, from_ts=start, to_ts=end)  # type: ignore[arg-type]
        assert len(points) == expected_buckets

    def test_week_bucket_starts_monday(self) -> None:
        """Weekly aggregation anchors buckets on the ISO Monday."""
        # Wednesday Jan 7, 2026 is ISO day-of-week 3.
        start = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)
        end = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)
        points, _ = aggregate_metrics([], period="week", from_ts=start, to_ts=end)
        # Expect buckets starting on Mondays: Jan 5, 12, 19.
        assert all(p.bucket.weekday() == 0 for p in points)
        assert points[0].bucket.date() == datetime(2026, 1, 5).date()
