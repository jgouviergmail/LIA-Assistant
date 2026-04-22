"""Bucket-based aggregation for Health Metrics charts.

Given an ordered-ascending sequence of raw health samples (polymorphic —
heart_rate and steps interleaved), this module computes aggregated points
for a requested period (hour / day / week / month / year):

- **heart_rate** samples → AVG / MIN / MAX across the bucket's samples
- **steps** samples → SUM of values (each sample already represents the
  step count for its own inter-sample interval)

Buckets are anchored on each sample's ``date_start``. Period-wide averages
return HR avg and steps per day over the requested window.

Kept standalone (no DB access) so it can be unit-tested in isolation and
reused by a future LLM tool or export endpoint.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — polymorphic samples, kind-discriminated aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from src.core.constants import (
    HEALTH_METRICS_PERIOD_DAY,
    HEALTH_METRICS_PERIOD_HOUR,
    HEALTH_METRICS_PERIOD_MONTH,
    HEALTH_METRICS_PERIOD_WEEK,
    HEALTH_METRICS_PERIOD_YEAR,
)
from src.domains.health_metrics.kinds import (
    HEALTH_KINDS,
    AggregationMethod,
    HealthKindSpec,
)
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.schemas import (
    HealthMetricAggregatePoint,
    HealthMetricPeriodAverages,
)

PeriodLiteral = Literal["hour", "day", "week", "month", "year"]


@dataclass(slots=True)
class _BucketAccumulator:
    """Running aggregate for one bucket (mutable during traversal).

    Internals are polymorphic: ``values_by_kind`` holds the raw samples
    observed in the bucket keyed by kind discriminator. The finalizer
    :meth:`to_point` uses the central registry to compute the correct
    aggregate per kind (SUM, AVG_MIN_MAX, LAST_VALUE) and also populates
    the legacy typed fields on the response schema for backward compat.
    """

    bucket_start: datetime
    values_by_kind: dict[str, list[int]] = field(default_factory=dict)
    has_any_sample: bool = False

    @classmethod
    def empty(cls, bucket_start: datetime) -> _BucketAccumulator:
        """Create an empty bucket anchored at ``bucket_start``."""
        return cls(bucket_start=bucket_start)

    def add(self, kind: str, value: int) -> None:
        """Record a sample into the bucket under its kind."""
        self.values_by_kind.setdefault(kind, []).append(value)
        self.has_any_sample = True

    def to_point(self) -> HealthMetricAggregatePoint:
        """Finalize this bucket to the public response schema.

        Produces:
        - the legacy typed fields (``heart_rate_avg``, ``heart_rate_min``,
          ``heart_rate_max``, ``steps_total``) so the existing frontend keeps
          working unchanged;
        - the new polymorphic ``metrics_by_kind`` dict for future-proof
          per-kind consumption.
        """
        if not self.has_any_sample:
            return HealthMetricAggregatePoint(bucket=self.bucket_start, has_data=False)

        # Legacy fields populated via spec-driven dispatch.
        legacy_fields: dict[str, int | float | None] = {}
        metrics_by_kind: dict[str, dict[str, int | float]] = {}

        for kind, values in self.values_by_kind.items():
            if not values:
                continue
            spec = HEALTH_KINDS.get(kind)
            if spec is None:
                # Forward-compat: a kind in DB but not in registry → skip
                # (should never happen in practice since ingestion gates on
                # registry membership + DB CheckConstraint).
                continue
            kind_metrics = _aggregate_values(spec, values)
            metrics_by_kind[kind] = kind_metrics
            _populate_legacy_fields(legacy_fields, spec, kind_metrics)

        # mypy hints: legacy_fields values are narrowed by Pydantic at field assignment.
        hr_avg_raw = legacy_fields.get("heart_rate_avg")
        hr_min_raw = legacy_fields.get("heart_rate_min")
        hr_max_raw = legacy_fields.get("heart_rate_max")
        steps_raw = legacy_fields.get("steps_total")
        return HealthMetricAggregatePoint(
            bucket=self.bucket_start,
            heart_rate_avg=float(hr_avg_raw) if hr_avg_raw is not None else None,
            heart_rate_min=int(hr_min_raw) if hr_min_raw is not None else None,
            heart_rate_max=int(hr_max_raw) if hr_max_raw is not None else None,
            steps_total=int(steps_raw) if steps_raw is not None else None,
            metrics_by_kind=metrics_by_kind or None,
            has_data=True,
        )


def _aggregate_values(spec: HealthKindSpec, values: list[int]) -> dict[str, int | float]:
    """Produce per-kind metrics dict according to the spec's aggregation method.

    Args:
        spec: The kind spec determining the aggregation semantics.
        values: Raw integer values observed in the bucket (non-empty).

    Returns:
        A dict with keys depending on the aggregation method:
        - ``AVG_MIN_MAX`` → ``{"avg", "min", "max"}``
        - ``SUM`` → ``{"sum"}``
        - ``LAST_VALUE`` → ``{"last"}``
    """
    match spec.aggregation_method:
        case AggregationMethod.AVG_MIN_MAX:
            return {
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            }
        case AggregationMethod.SUM:
            return {"sum": sum(values)}
        case AggregationMethod.LAST_VALUE:
            return {"last": values[-1]}


def _populate_legacy_fields(
    legacy_fields: dict[str, int | float | None],
    spec: HealthKindSpec,
    kind_metrics: dict[str, int | float],
) -> None:
    """Map per-kind metrics to the legacy typed fields on the response.

    The mapping uses naming conventions tied to the spec's
    ``legacy_response_fields`` tuple:
    - Fields ending in ``_avg`` / ``_min`` / ``_max`` map to the
      corresponding keys in ``kind_metrics``.
    - Fields ending in ``_total`` map to ``sum``.
    - Fields ending in ``_last`` map to ``last``.

    Args:
        legacy_fields: Mutable dict accumulating the legacy field values.
        spec: The kind spec.
        kind_metrics: The aggregated metrics dict produced by
            :func:`_aggregate_values`.
    """
    for field_name in spec.legacy_response_fields:
        if field_name.endswith("_avg"):
            legacy_fields[field_name] = kind_metrics.get("avg")
        elif field_name.endswith("_min"):
            legacy_fields[field_name] = kind_metrics.get("min")
        elif field_name.endswith("_max"):
            legacy_fields[field_name] = kind_metrics.get("max")
        elif field_name.endswith("_total"):
            legacy_fields[field_name] = kind_metrics.get("sum")
        elif field_name.endswith("_last"):
            legacy_fields[field_name] = kind_metrics.get("last")


# =============================================================================
# Bucket floor / advance helpers
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
        year = bucket_start.year + (1 if bucket_start.month == 12 else 0)
        month = 1 if bucket_start.month == 12 else bucket_start.month + 1
        return bucket_start.replace(year=year, month=month)
    if period == HEALTH_METRICS_PERIOD_YEAR:
        return bucket_start.replace(year=bucket_start.year + 1)
    raise ValueError(f"Unsupported period: {period}")


# =============================================================================
# Main aggregation entry point
# =============================================================================


def aggregate_samples(
    samples: list[HealthSample],
    period: PeriodLiteral,
    from_ts: datetime,
    to_ts: datetime,
) -> tuple[list[HealthMetricAggregatePoint], HealthMetricPeriodAverages]:
    """Aggregate polymorphic samples into fixed-size buckets.

    Samples of kind ``"heart_rate"`` contribute to HR avg / min / max;
    samples of kind ``"steps"`` contribute to the bucket's steps sum.
    Missing buckets are emitted with ``has_data=False`` so the frontend
    can render gaps without client-side gap detection.

    Args:
        samples: Ordered-ascending list of samples in the window.
        period: Bucket size literal.
        from_ts: Inclusive window start (UTC).
        to_ts: Exclusive window end (UTC).

    Returns:
        Tuple of (points, averages) ready to be serialized to the client.
    """
    from_ts = from_ts.astimezone(UTC)
    to_ts = to_ts.astimezone(UTC)

    buckets: dict[datetime, _BucketAccumulator] = {}
    cursor = _floor_to_bucket(from_ts, period)
    window_end_floor = _floor_to_bucket(to_ts - timedelta(microseconds=1), period)
    while cursor <= window_end_floor:
        buckets[cursor] = _BucketAccumulator.empty(cursor)
        cursor = _advance_bucket(cursor, period)

    # Global period-wide accumulation (for the averages section of the response).
    # Kept polymorphic via per-kind lists; the legacy ``heart_rate_avg`` and
    # ``steps_per_day_avg`` fields are derived below from these lists.
    global_values_by_kind: dict[str, list[int]] = {}

    for sample in samples:
        bucket_start = _floor_to_bucket(sample.date_start, period)
        bucket = buckets.get(bucket_start)
        if bucket is None:
            # Defensive — DB query should respect the window.
            continue
        value = int(sample.value)
        bucket.add(sample.kind, value)
        global_values_by_kind.setdefault(sample.kind, []).append(value)

    points = [buckets[k].to_point() for k in sorted(buckets.keys())]

    # Period-wide averages (legacy typed fields).
    hr_all = global_values_by_kind.get("heart_rate", [])
    hr_avg = (sum(hr_all) / len(hr_all)) if hr_all else None
    steps_all = global_values_by_kind.get("steps", [])
    steps_total_global = sum(steps_all) if steps_all else 0
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
