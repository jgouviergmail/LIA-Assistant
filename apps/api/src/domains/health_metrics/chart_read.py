"""Bounded SQL chart statistics reuse source bucket boundaries, kind registry and DTOs."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.aggregator import (
    PeriodLiteral,
    _advance_bucket,
    _floor_to_bucket,
    _populate_legacy_fields,
)
from src.domains.health_metrics.kinds import HEALTH_KINDS, AggregationMethod
from src.domains.health_metrics.management_read import health_sample_statement
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.schemas import (
    HealthMetricAggregatePoint,
    HealthMetricAggregateResponse,
    HealthMetricPeriodAverages,
)


def chart_bucket_starts(
    period: PeriodLiteral, from_ts: datetime, to_ts: datetime, *, maximum: int
) -> list[datetime]:
    if from_ts >= to_ts:
        raise ValueError("Window start must precede its exclusive end")
    cursor = _floor_to_bucket(from_ts, period)
    last = _floor_to_bucket(to_ts - timedelta(microseconds=1), period)
    buckets: list[datetime] = []
    while cursor <= last:
        if len(buckets) >= maximum:
            raise ValueError(
                f"Chart exceeds {maximum} buckets; use a coarser period or narrower window"
            )
        buckets.append(cursor)
        if cursor == last:
            break
        cursor = _advance_bucket(cursor, period)
    return buckets


def _kind_metrics(
    kind: str, count: int, total: int, minimum: int, maximum: int
) -> dict[str, int | float]:
    method = HEALTH_KINDS[kind].aggregation_method
    if method == AggregationMethod.AVG_MIN_MAX:
        return {"avg": total / count, "min": minimum, "max": maximum}
    if method == AggregationMethod.SUM:
        return {"sum": total}
    raise ValueError("Review SQL chart semantics before adding a new aggregation method")


def _point(
    bucket: datetime, metrics: dict[str, dict[str, int | float]]
) -> HealthMetricAggregatePoint:
    if not metrics:
        return HealthMetricAggregatePoint(bucket=bucket, has_data=False)
    legacy: dict[str, int | float | None] = {}
    for kind, observed in metrics.items():
        _populate_legacy_fields(legacy, HEALTH_KINDS[kind], observed)
    return HealthMetricAggregatePoint.model_validate(
        {"bucket": bucket, "has_data": True, "metrics_by_kind": metrics, **legacy}
    )


async def read_chart_statistics(
    db: AsyncSession,
    actor_id: UUID,
    *,
    period: PeriodLiteral,
    from_ts: datetime,
    to_ts: datetime,
    maximum_buckets: int,
) -> HealthMetricAggregateResponse:
    buckets = chart_bucket_starts(period, from_ts, to_ts, maximum=maximum_buckets)
    # UTC flooring agrees with the source, independently of the PostgreSQL session timezone.
    bucket = func.date_trunc(period, func.timezone("UTC", HealthSample.date_start))
    owned = health_sample_statement(actor_id, from_ts=from_ts, to_ts=to_ts).where(
        HealthSample.kind.in_(tuple(HEALTH_KINDS))
    )
    statement = owned.with_only_columns(
        bucket,
        HealthSample.kind,
        func.count(),
        func.sum(HealthSample.value),
        func.min(HealthSample.value),
        func.max(HealthSample.value),
    ).group_by(bucket, HealthSample.kind)
    observed: dict[datetime, dict[str, dict[str, int | float]]] = {key: {} for key in buckets}
    hr_count = hr_total = steps_total = 0
    for started, kind, count, total, minimum, maximum in (await db.execute(statement)).tuples():
        key = started.replace(tzinfo=UTC)
        observed[key][kind] = _kind_metrics(kind, count, total, minimum, maximum)
        if kind == "heart_rate":
            hr_count += count
            hr_total += total
        if kind == "steps":
            steps_total += total
    days = (to_ts - from_ts).total_seconds() / 86400
    averages = HealthMetricPeriodAverages(
        heart_rate_avg=hr_total / hr_count if hr_count else None,
        steps_per_day_avg=steps_total / days if steps_total > 0 else None,
    )
    return HealthMetricAggregateResponse(
        period=period,
        from_ts=from_ts,
        to_ts=to_ts,
        points=[_point(key, observed[key]) for key in buckets],
        averages=averages,
    )
