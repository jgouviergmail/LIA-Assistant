"""Unit tests for the polymorphic Health Metrics aggregator.

Covers:
- Bucket flooring and advancement for every supported period
- Empty-bucket gap preservation (``has_data=False``)
- Heart-rate aggregation (avg/min/max) restricted to ``kind="heart_rate"``
- Steps aggregation (simple sum) restricted to ``kind="steps"``
- Period-wide averages (HR avg, steps-per-day avg)
- Cross-kind interleaving within a bucket
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.core.constants import (
    HEALTH_METRICS_KIND_HEART_RATE,
    HEALTH_METRICS_KIND_STEPS,
)
from src.domains.health_metrics.aggregator import aggregate_samples
from src.domains.health_metrics.models import HealthSample

pytestmark = pytest.mark.unit


# =============================================================================
# Helpers
# =============================================================================


def _make_sample(kind: str, date_start: datetime, value: int) -> HealthSample:
    """Build an in-memory HealthSample for tests (no DB persistence)."""
    return HealthSample(
        id=uuid4(),
        user_id=uuid4(),
        kind=kind,
        date_start=date_start,
        date_end=date_start + timedelta(minutes=5),
        value=value,
        source="test",
    )


def _hr(date_start: datetime, bpm: int) -> HealthSample:
    return _make_sample(HEALTH_METRICS_KIND_HEART_RATE, date_start, bpm)


def _steps(date_start: datetime, count: int) -> HealthSample:
    return _make_sample(HEALTH_METRICS_KIND_STEPS, date_start, count)


# =============================================================================
# Gap preservation
# =============================================================================


class TestGapPreservation:
    """Empty buckets must be emitted so the frontend can render gaps."""

    def test_empty_window_produces_empty_buckets(self) -> None:
        """A window with no samples still yields one point per bucket slot."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
        points, averages = aggregate_samples([], period="hour", from_ts=start, to_ts=end)
        assert len(points) == 3
        assert all(not p.has_data for p in points)
        assert averages.heart_rate_avg is None
        assert averages.steps_per_day_avg is None

    def test_scattered_samples_leave_gaps(self) -> None:
        """Only buckets that contain a sample have has_data=True."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 4, 0, tzinfo=UTC)
        samples = [
            _hr(datetime(2026, 1, 1, 0, 30, tzinfo=UTC), 70),
            _hr(datetime(2026, 1, 1, 2, 15, tzinfo=UTC), 80),
        ]
        points, _ = aggregate_samples(samples, period="hour", from_ts=start, to_ts=end)
        assert len(points) == 4
        assert [p.has_data for p in points] == [True, False, True, False]


# =============================================================================
# Heart-rate aggregation
# =============================================================================


class TestHeartRateAggregation:
    """Heart-rate samples aggregate over a bucket (avg / min / max)."""

    def test_single_bucket_multiple_samples(self) -> None:
        """Multiple HR samples within the same bucket average correctly."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        samples = [
            _hr(datetime(2026, 1, 1, 6, 0, tzinfo=UTC), 60),
            _hr(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), 80),
            _hr(datetime(2026, 1, 1, 18, 0, tzinfo=UTC), 100),
        ]
        points, averages = aggregate_samples(samples, period="day", from_ts=start, to_ts=end)
        assert len(points) == 1
        assert points[0].heart_rate_avg == 80
        assert points[0].heart_rate_min == 60
        assert points[0].heart_rate_max == 100
        assert points[0].steps_total is None  # no steps samples
        assert averages.heart_rate_avg == 80

    def test_steps_samples_do_not_pollute_hr_average(self) -> None:
        """Steps samples in the same bucket must not leak into HR aggregates."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        samples = [
            _steps(datetime(2026, 1, 1, 6, 0, tzinfo=UTC), 500),
            _hr(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), 70),
        ]
        points, _ = aggregate_samples(samples, period="day", from_ts=start, to_ts=end)
        assert points[0].heart_rate_avg == 70
        assert points[0].heart_rate_min == 70
        assert points[0].heart_rate_max == 70


# =============================================================================
# Steps aggregation (simple SUM)
# =============================================================================


class TestStepsAggregation:
    """Steps are summed per bucket; values represent per-interval counts."""

    def test_single_bucket_sum(self) -> None:
        """All steps samples in one bucket sum into steps_total."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        samples = [
            _steps(datetime(2026, 1, 1, 6, 0, tzinfo=UTC), 500),
            _steps(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), 1500),
            _steps(datetime(2026, 1, 1, 18, 0, tzinfo=UTC), 2000),
        ]
        points, averages = aggregate_samples(samples, period="day", from_ts=start, to_ts=end)
        assert len(points) == 1
        assert points[0].steps_total == 4000
        assert averages.steps_per_day_avg == pytest.approx(4000.0)

    def test_multi_day_sum(self) -> None:
        """Each day bucket sums its own samples; period avg = total / days."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
        samples = [
            _steps(datetime(2026, 1, 1, 8, 0, tzinfo=UTC), 3000),
            _steps(datetime(2026, 1, 1, 20, 0, tzinfo=UTC), 4000),
            _steps(datetime(2026, 1, 2, 8, 0, tzinfo=UTC), 2500),
            _steps(datetime(2026, 1, 2, 20, 0, tzinfo=UTC), 2500),
        ]
        points, averages = aggregate_samples(samples, period="day", from_ts=start, to_ts=end)
        assert len(points) == 2
        assert points[0].steps_total == 7000
        assert points[1].steps_total == 5000
        # 12000 steps / 2 days = 6000 / day.
        assert averages.steps_per_day_avg == pytest.approx(6000.0)

    def test_hr_only_bucket_has_no_steps_total(self) -> None:
        """A bucket with only HR samples reports steps_total=None."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        samples = [_hr(datetime(2026, 1, 1, 8, 0, tzinfo=UTC), 70)]
        points, averages = aggregate_samples(samples, period="day", from_ts=start, to_ts=end)
        assert points[0].steps_total is None
        assert averages.steps_per_day_avg is None


# =============================================================================
# Mixed-kind interleaving inside a single bucket
# =============================================================================


class TestMixedKinds:
    """A bucket can hold both HR and steps samples simultaneously."""

    def test_mixed_bucket_reports_both_aggregates(self) -> None:
        """HR avg and steps_total coexist in the same day bucket."""
        start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        samples = [
            _hr(datetime(2026, 1, 1, 6, 0, tzinfo=UTC), 60),
            _steps(datetime(2026, 1, 1, 6, 30, tzinfo=UTC), 1000),
            _hr(datetime(2026, 1, 1, 18, 0, tzinfo=UTC), 80),
            _steps(datetime(2026, 1, 1, 19, 0, tzinfo=UTC), 2500),
        ]
        points, _ = aggregate_samples(samples, period="day", from_ts=start, to_ts=end)
        assert points[0].heart_rate_avg == 70
        assert points[0].steps_total == 3500
        assert points[0].has_data is True


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
        points, _ = aggregate_samples(
            [],
            period=period,  # type: ignore[arg-type]
            from_ts=start,
            to_ts=end,
        )
        assert len(points) == expected_buckets

    def test_week_bucket_starts_monday(self) -> None:
        """Weekly aggregation anchors buckets on the ISO Monday."""
        # Wednesday Jan 7, 2026 is ISO day-of-week 3.
        start = datetime(2026, 1, 7, 12, 0, tzinfo=UTC)
        end = datetime(2026, 1, 21, 12, 0, tzinfo=UTC)
        points, _ = aggregate_samples([], period="week", from_ts=start, to_ts=end)
        # Expect buckets starting on Mondays: Jan 5, 12, 19.
        assert all(p.bucket.weekday() == 0 for p in points)
        assert points[0].bucket.date() == datetime(2026, 1, 5).date()

    def test_month_bucket_starts_on_first(self) -> None:
        """Monthly aggregation anchors buckets on the 1st of each month."""
        start = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        end = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)
        points, _ = aggregate_samples([], period="month", from_ts=start, to_ts=end)
        assert [p.bucket.month for p in points] == [1, 2, 3, 4]
        assert all(p.bucket.day == 1 for p in points)
