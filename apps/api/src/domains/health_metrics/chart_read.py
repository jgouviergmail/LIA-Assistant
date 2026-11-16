"""Health chart statistics: one bounded SQL read per kind, at the person's clock.

The settings chart (``GET /health-metrics/aggregate``), the assistant's chart
command and the proactive-discussion source read the same statistics here
(ADR-148 amendment 2026-11-14). A second, in-Python aggregator served the
settings chart until then: it would have had to learn the overlap fusion and
the local day a second time, so it is gone.

- Values come through the fusion door (:func:`~.fusion.counted_samples`), one
  kind at a time: a ``MAX_RATE`` kind counts overlapping samples once.
- Buckets are the person's: a day starts at their midnight, an hour is an hour
  of their clock (``date_trunc`` over ``timezone(<zone>, ...)``, independent of
  the session ``TimeZone``). A point's ``bucket`` is the aware local start of
  its bucket, in the person's zone, so ``bucket.date()`` is their day.
- Where clocks repeat an hour, both readings share one hourly bucket; where
  they skip one, no bucket is drawn for it — the hours that happened.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    HEALTH_METRICS_PERIOD_DAY,
    HEALTH_METRICS_PERIOD_HOUR,
    HEALTH_METRICS_PERIOD_MONTH,
    HEALTH_METRICS_PERIOD_WEEK,
    HEALTH_METRICS_PERIOD_YEAR,
)
from src.domains.health_metrics.fusion import counted_samples
from src.domains.health_metrics.kinds import HEALTH_KINDS, AggregationMethod, HealthKindSpec
from src.domains.health_metrics.schemas import (
    HealthMetricAggregatePoint,
    HealthMetricAggregateResponse,
    HealthMetricPeriodAverages,
)

PeriodLiteral = Literal["hour", "day", "week", "month", "year"]

#: How far back a chart reads when its caller gives no start.
_DEFAULT_SPANS: dict[str, timedelta] = {
    HEALTH_METRICS_PERIOD_HOUR: timedelta(hours=24),
    HEALTH_METRICS_PERIOD_DAY: timedelta(days=7),
    HEALTH_METRICS_PERIOD_WEEK: timedelta(days=7 * 12),
    HEALTH_METRICS_PERIOD_MONTH: timedelta(days=365),
    HEALTH_METRICS_PERIOD_YEAR: timedelta(days=365 * 5),
}

#: Every UTC offset in use is a multiple of a quarter hour: stepping instants by
#: one meets every local hour, whatever the zone.
_QUARTER_HOUR = timedelta(minutes=15)


def default_chart_window(
    period: PeriodLiteral,
    *,
    zone: ZoneInfo,
    now: datetime,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> tuple[datetime, datetime]:
    """The window a chart covers, the caller's bounds kept.

    A missing end is ``now``. A missing start is the period's default span back
    from the end, moved to the start of its local bucket so the first bucket
    is a whole one.

    Args:
        period: The bucket size.
        zone: The person's zone.
        now: The current instant.
        from_ts: Inclusive start the caller asked for, or None.
        to_ts: Exclusive end the caller asked for, or None.

    Returns:
        ``(start, end)`` as UTC instants.
    """
    end = to_ts or now
    if from_ts is not None:
        return from_ts, end
    first = _floor_local(end - _DEFAULT_SPANS[period], period, zone)
    return _instant(first, zone), end


def _floor_local(moment: datetime, period: PeriodLiteral, zone: ZoneInfo) -> datetime:
    """The local start of the bucket holding ``moment``, as a naive wall time.

    Args:
        moment: An aware instant.
        period: The bucket size.
        zone: The person's zone.

    Returns:
        The bucket's start on the person's clock (naive).

    Raises:
        ValueError: An unsupported period.
    """
    local = moment.astimezone(zone).replace(tzinfo=None)
    if period == HEALTH_METRICS_PERIOD_HOUR:
        return local.replace(minute=0, second=0, microsecond=0)
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == HEALTH_METRICS_PERIOD_DAY:
        return day
    if period == HEALTH_METRICS_PERIOD_WEEK:
        return day - timedelta(days=day.weekday())
    if period == HEALTH_METRICS_PERIOD_MONTH:
        return day.replace(day=1)
    if period == HEALTH_METRICS_PERIOD_YEAR:
        return day.replace(month=1, day=1)
    raise ValueError(f"Unsupported period: {period}")


def _next_local(start: datetime, period: PeriodLiteral) -> datetime:
    """The next calendar bucket after a day-or-longer local bucket start.

    Args:
        start: A naive local bucket start.
        period: A day-or-longer bucket size.

    Returns:
        The following bucket's naive local start.

    Raises:
        ValueError: An unsupported period.
    """
    if period == HEALTH_METRICS_PERIOD_DAY:
        return start + timedelta(days=1)
    if period == HEALTH_METRICS_PERIOD_WEEK:
        return start + timedelta(days=7)
    if period == HEALTH_METRICS_PERIOD_MONTH:
        rolls = start.month == 12
        return start.replace(year=start.year + rolls, month=1 if rolls else start.month + 1)
    if period == HEALTH_METRICS_PERIOD_YEAR:
        return start.replace(year=start.year + 1)
    raise ValueError(f"Unsupported period: {period}")


def _instant(local: datetime, zone: ZoneInfo) -> datetime:
    """The UTC instant a naive local wall time happens at (the earlier reading)."""
    return local.replace(tzinfo=zone, fold=0).astimezone(UTC)


def chart_bucket_starts(
    period: PeriodLiteral,
    from_ts: datetime,
    to_ts: datetime,
    zone: ZoneInfo,
    *,
    maximum: int,
) -> list[datetime]:
    """Every local bucket the window touches, as naive local starts, in order.

    Args:
        period: The bucket size.
        from_ts: Inclusive window start.
        to_ts: Exclusive window end.
        zone: The person's zone.
        maximum: The most buckets a read may draw.

    Returns:
        The buckets' naive local starts, ascending, each once.

    Raises:
        ValueError: An empty window, or one needing more than ``maximum`` buckets.
    """
    if from_ts >= to_ts:
        raise ValueError("Window start must precede its exclusive end")
    last = _floor_local(to_ts - timedelta(microseconds=1), period, zone)
    buckets: list[datetime] = []

    def add(bucket: datetime) -> None:
        if buckets and buckets[-1] == bucket:
            return
        if len(buckets) >= maximum:
            raise ValueError(
                f"Chart exceeds {maximum} buckets; use a coarser period or narrower window"
            )
        buckets.append(bucket)

    if period == HEALTH_METRICS_PERIOD_HOUR:
        # Hours are read off instants: a skipped hour is never drawn, a
        # repeated one is drawn once.
        cursor = from_ts
        while cursor < to_ts:
            add(_floor_local(cursor, period, zone))
            cursor += _QUARTER_HOUR
        add(last)
        return buckets
    bucket = _floor_local(from_ts, period, zone)
    while True:
        add(bucket)
        # Never step past the last bucket: the step after year 9999 does not exist.
        if bucket >= last:
            return buckets
        bucket = _next_local(bucket, period)


def _kind_metrics(
    spec: HealthKindSpec, count: int, total: float, minimum: float, maximum: float
) -> dict[str, int | float]:
    if spec.aggregation_method == AggregationMethod.AVG_MIN_MAX:
        return {"avg": total / count, "min": round(minimum), "max": round(maximum)}
    if spec.aggregation_method == AggregationMethod.SUM:
        return {"sum": round(total)}
    raise ValueError("Review SQL chart semantics before adding a new aggregation method")


def _populate_legacy_fields(
    legacy_fields: dict[str, int | float | None],
    spec: HealthKindSpec,
    kind_metrics: dict[str, int | float],
) -> None:
    """Map per-kind metrics to the legacy typed fields of a point.

    ``*_avg`` / ``*_min`` / ``*_max`` read the matching metric, ``*_total``
    the sum, ``*_last`` the last value.

    Args:
        legacy_fields: Mutable dict accumulating the legacy field values.
        spec: The kind spec.
        kind_metrics: The kind's metrics in the bucket.
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
    zone: ZoneInfo,
    from_ts: datetime,
    to_ts: datetime,
    maximum_buckets: int,
) -> HealthMetricAggregateResponse:
    """Bucketed statistics of every kind over a window, at the person's clock.

    Args:
        db: The caller's session (sequential statements only).
        actor_id: The owner.
        period: The bucket size.
        zone: The person's zone, where buckets are cut.
        from_ts: Inclusive window start.
        to_ts: Exclusive window end.
        maximum_buckets: The most buckets the read may draw.

    Returns:
        The chart: one point per local bucket (``has_data=False`` where no
        sample counts), and the window's averages.

    Raises:
        ValueError: An empty window, or one needing more than the maximum.
    """
    observed: dict[datetime, dict[str, dict[str, int | float]]] = {
        key: {}
        for key in chart_bucket_starts(period, from_ts, to_ts, zone, maximum=maximum_buckets)
    }
    hr_count = 0
    hr_total = 0.0
    steps_total = 0.0
    for spec in HEALTH_KINDS.values():
        counted = counted_samples(actor_id, spec.kind, from_ts=from_ts, to_ts=to_ts)
        bucket = func.date_trunc(period, func.timezone(zone.key, counted.c.date_start))
        statement = select(
            bucket,
            func.count(),
            func.sum(counted.c.value),
            func.min(counted.c.value),
            func.max(counted.c.value),
        ).group_by(bucket)
        for started, count, total, minimum, maximum in (await db.execute(statement)).tuples():
            metrics = _kind_metrics(spec, count, float(total), float(minimum), float(maximum))
            # A bucket the window touches is always listed; one the list did
            # not foresee is still data, kept rather than dropped.
            observed.setdefault(started, {})[spec.kind] = metrics
            if spec.kind == "heart_rate":
                hr_count += count
                hr_total += float(total)
            if spec.kind == "steps":
                steps_total += float(total)
    days = (to_ts - from_ts).total_seconds() / 86400
    averages = HealthMetricPeriodAverages(
        heart_rate_avg=hr_total / hr_count if hr_count else None,
        steps_per_day_avg=steps_total / days if steps_total > 0 else None,
    )
    return HealthMetricAggregateResponse(
        period=period,
        from_ts=from_ts,
        to_ts=to_ts,
        points=[
            _point(key.replace(tzinfo=zone, fold=0), observed[key]) for key in sorted(observed)
        ],
        averages=averages,
    )
