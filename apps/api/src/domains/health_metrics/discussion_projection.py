"""Native daily aggregates remain measurements, never diagnoses or missing-day zeros."""

from datetime import date, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, StrictFloat, StrictInt

from src.core.local_day import local_midnight
from src.domains.health_metrics.kinds import HEALTH_KINDS
from src.domains.health_metrics.schemas import HealthMetricAggregateResponse
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    DiscussionValue,
    SourceKey,
    SourceReadRequest,
    semantic_version,
)


class HealthDay(DiscussionValue):
    """One local day's aggregate of one health metric, over the samples available only.

    ``timezone`` names the zone the day is cut in — the person's, so ``day`` is
    the calendar day they lived (ADR-148 amendment 2026-11-14).
    """

    day: date
    kind: str
    timezone: str
    unit: str
    metrics: dict[str, StrictInt | StrictFloat]
    interval_start: AwareDatetime
    interval_end: AwareDatetime
    full_day_window: bool
    coverage: Literal["available_samples_only"] = "available_samples_only"
    sample_selection: Literal["start_time_in_interval"] = "start_time_in_interval"


def daily_evidence(
    chart: HealthMetricAggregateResponse, request: SourceReadRequest, zone: ZoneInfo
) -> tuple[DiscussionEvidence, ...]:
    """Project a metric's daily aggregates into observed evidence, newest day first.

    A day without samples is skipped; a partial day says so. A day ends at the
    next local midnight, read off the calendar: 29 March lasts 23 hours in Paris.

    Args:
        chart: The metric's daily aggregates, bucketed in ``zone``.
        request: The read.
        zone: The person's zone, where the chart's days were cut.

    Returns:
        The evidence, one per day with data.
    """
    evidence: list[DiscussionEvidence] = []
    for point in reversed(chart.points):
        if not point.has_data:
            continue
        day = point.bucket.astimezone(zone).date()
        day_start = local_midnight(day, zone)
        day_end = local_midnight(day + timedelta(days=1), zone)
        start, end = max(day_start, chart.from_ts), min(day_end, chart.to_ts)
        for kind, metrics in sorted((point.metrics_by_kind or {}).items()):
            frame = HealthDay(
                day=day,
                kind=kind,
                timezone=zone.key,
                unit=HEALTH_KINDS[kind].unit,
                metrics=metrics,
                interval_start=start,
                interval_end=end,
                full_day_window=start == day_start and end == day_end,
            )
            excerpt = frame.model_dump_json()
            if len(excerpt) > request.item_max_chars:
                raise ValueError("A health aggregate must fit whole in the item budget")
            identity = f"{frame.day.isoformat()}:{kind}"
            evidence.append(
                DiscussionEvidence(
                    reference=f"health:{identity}",
                    source=SourceKey.HEALTH,
                    object_id=identity,
                    subject_id=f"health:{kind}",
                    version=semantic_version(
                        (frame.model_dump_json(exclude={"interval_start", "interval_end"}),)
                    ),
                    observed_at=request.now,
                    interval_start=start,
                    interval_end=end,
                    excerpt=excerpt,
                    category=kind,
                    sensitive_topics=("health",),
                    assertion="reported",
                    derived=True,
                )
            )
    return tuple(evidence)
