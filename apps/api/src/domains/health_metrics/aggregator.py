"""Bucket-based aggregation for Health Metrics charts.

Given an ordered-ascending sequence of raw metric samples, this module
computes aggregated points for a requested period (hour / day / week /
month / year). Each ``steps`` field is the count attributable to the
inter-sample period and is therefore summed (not differentiated) per
bucket.

Kept as a standalone module (no DB access) so it can be unit-tested
in isolation and reused by a future LLM tool.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from src.core.constants import (
    HEALTH_METRICS_PERIOD_DAY,
    HEALTH_METRICS_PERIOD_HOUR,
    HEALTH_METRICS_PERIOD_MONTH,
    HEALTH_METRICS_PERIOD_WEEK,
    HEALTH_METRICS_PERIOD_YEAR,
)
from src.domains.health_metrics.models import HealthMetric
from src.domains.health_metrics.schemas import (
    HealthMetricAggregatePoint,
    HealthMetricPeriodAverages,
)

PeriodLiteral = Literal["hour", "day", "week", "month", "year"]


@dataclass(slots=True)
class _BucketAccumulator:
    """Running aggregate for one bucket (mutable during traversal)."""

    bucket_start: datetime
    hr_values: list[int]
    steps_total: int
    has_steps_sample: bool
    has_any_sample: bool

    @classmethod
    def empty(cls, bucket_start: datetime) -> _BucketAccumulator:
        """Create an empty bucket anchored at ``bucket_start``."""
        return cls(
            bucket_start=bucket_start,
            hr_values=[],
            steps_total=0,
            has_steps_sample=False,
            has_any_sample=False,
        )

    def to_point(self) -> HealthMetricAggregatePoint:
        """Finalize this bucket to the public response schema."""
        if not self.has_any_sample:
            return HealthMetricAggregatePoint(
                bucket=self.bucket_start,
                heart_rate_avg=None,
                heart_rate_min=None,
                heart_rate_max=None,
                steps_total=None,
                has_data=False,
            )
        hr_avg = (sum(self.hr_values) / len(self.hr_values)) if self.hr_values else None
        hr_min = min(self.hr_values) if self.hr_values else None
        hr_max = max(self.hr_values) if self.hr_values else None
        return HealthMetricAggregatePoint(
            bucket=self.bucket_start,
            heart_rate_avg=hr_avg,
            heart_rate_min=hr_min,
            heart_rate_max=hr_max,
            steps_total=self.steps_total if self.has_steps_sample else None,
            has_data=True,
        )


# =============================================================================
# Bucket floor/advance helpers
# =============================================================================


def _floor_to_bucket(ts: datetime, period: PeriodLiteral) -> datetime:
    """Return the start-of-bucket timestamp containing ts, in UTC.

    Args:
        ts: Timezone-aware datetime. Converted to UTC before flooring.
        period: Bucket size literal.

    Returns:
        A UTC datetime aligned on the start of the bucket that contains ts.

    Raises:
        ValueError: If ``period`` is not one of the supported literals.
    """
    ts = ts.astimezone(UTC)
    if period == HEALTH_METRICS_PERIOD_HOUR:
        return ts.replace(minute=0, second=0, microsecond=0)
    if period == HEALTH_METRICS_PERIOD_DAY:
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == HEALTH_METRICS_PERIOD_WEEK:
        # ISO week starts Monday.
        day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        return day - timedelta(days=day.weekday())
    if period == HEALTH_METRICS_PERIOD_MONTH:
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == HEALTH_METRICS_PERIOD_YEAR:
        return ts.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unsupported period: {period}")


def _advance_bucket(bucket_start: datetime, period: PeriodLiteral) -> datetime:
    """Return the start of the bucket immediately following ``bucket_start``.

    Args:
        bucket_start: Start-of-bucket datetime (must already be aligned).
        period: Bucket size literal.

    Returns:
        The start of the next bucket in the sequence.

    Raises:
        ValueError: If ``period`` is not one of the supported literals.
    """
    if period == HEALTH_METRICS_PERIOD_HOUR:
        return bucket_start + timedelta(hours=1)
    if period == HEALTH_METRICS_PERIOD_DAY:
        return bucket_start + timedelta(days=1)
    if period == HEALTH_METRICS_PERIOD_WEEK:
        return bucket_start + timedelta(days=7)
    if period == HEALTH_METRICS_PERIOD_MONTH:
        # Month arithmetic without dateutil.
        year = bucket_start.year + (1 if bucket_start.month == 12 else 0)
        month = 1 if bucket_start.month == 12 else bucket_start.month + 1
        return bucket_start.replace(year=year, month=month)
    if period == HEALTH_METRICS_PERIOD_YEAR:
        return bucket_start.replace(year=bucket_start.year + 1)
    raise ValueError(f"Unsupported period: {period}")


# =============================================================================
# Main aggregation entry point
# =============================================================================


def aggregate_metrics(
    metrics: list[HealthMetric],
    period: PeriodLiteral,
    from_ts: datetime,
    to_ts: datetime,
) -> tuple[list[HealthMetricAggregatePoint], HealthMetricPeriodAverages]:
    """Aggregate a list of metric samples into fixed-size buckets.

    The samples MUST be ordered by ``recorded_at`` ascending. Missing buckets
    (no samples at all) are emitted with ``has_data=False`` so the frontend
    can display gaps without client-side gap detection.

    Each ``steps`` field counts steps for the inter-sample period — buckets
    therefore aggregate by simple SUM. Heart rate is averaged.

    Args:
        metrics: Ordered-ascending list of HealthMetric rows in the window.
        period: Bucket size literal.
        from_ts: Inclusive window start (UTC).
        to_ts: Exclusive window end (UTC).

    Returns:
        Tuple of (points, averages) ready to be serialized to the client.
    """
    from_ts = from_ts.astimezone(UTC)
    to_ts = to_ts.astimezone(UTC)

    # Initialize empty bucket map anchored on the full window, to preserve gaps.
    buckets: dict[datetime, _BucketAccumulator] = {}
    cursor = _floor_to_bucket(from_ts, period)
    window_end_floor = _floor_to_bucket(to_ts - timedelta(microseconds=1), period)
    while cursor <= window_end_floor:
        buckets[cursor] = _BucketAccumulator.empty(cursor)
        cursor = _advance_bucket(cursor, period)

    hr_all: list[int] = []
    steps_total_global: int = 0

    for metric in metrics:
        bucket_start = _floor_to_bucket(metric.recorded_at, period)
        bucket = buckets.get(bucket_start)
        if bucket is None:
            # Outside the requested window — skip. This should not happen if
            # the DB query respects from/to, but defensively preserve semantics.
            continue

        bucket.has_any_sample = True

        if metric.heart_rate is not None:
            bucket.hr_values.append(int(metric.heart_rate))
            hr_all.append(int(metric.heart_rate))

        if metric.steps is not None:
            bucket.steps_total += int(metric.steps)
            bucket.has_steps_sample = True
            steps_total_global += int(metric.steps)

    points = [buckets[k].to_point() for k in sorted(buckets.keys())]

    # Period-wide averages.
    hr_avg = (sum(hr_all) / len(hr_all)) if hr_all else None
    total_seconds = (to_ts - from_ts).total_seconds()
    total_days = total_seconds / 86400.0
    steps_per_day_avg = (
        steps_total_global / total_days if total_days > 0 and steps_total_global > 0 else None
    )
    averages = HealthMetricPeriodAverages(
        heart_rate_avg=hr_avg,
        steps_per_day_avg=steps_per_day_avg,
    )
    return points, averages
