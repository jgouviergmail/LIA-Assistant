"""Native daily aggregates remain measurements, never diagnoses or missing-day zeros."""

from datetime import date, timedelta
from typing import Literal

from pydantic import AwareDatetime, StrictFloat, StrictInt

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
    """One day's aggregate of one health metric, over the samples available only."""

    day: date
    kind: str
    timezone: Literal["UTC"] = "UTC"
    unit: str
    metrics: dict[str, StrictInt | StrictFloat]
    interval_start: AwareDatetime
    interval_end: AwareDatetime
    full_day_window: bool
    coverage: Literal["available_samples_only"] = "available_samples_only"
    sample_selection: Literal["start_time_in_interval"] = "start_time_in_interval"


def daily_evidence(
    chart: HealthMetricAggregateResponse, request: SourceReadRequest
) -> tuple[DiscussionEvidence, ...]:
    """Project a metric's daily aggregates into observed evidence, newest day first.

    A day without samples is skipped; a partial day says so.

    Args:
        chart: The metric's daily aggregates.
        request: The read.

    Returns:
        The evidence, one per day with data.
    """
    evidence: list[DiscussionEvidence] = []
    for point in reversed(chart.points):
        if not point.has_data:
            continue
        day_end = point.bucket + timedelta(days=1)
        start, end = max(point.bucket, chart.from_ts), min(day_end, chart.to_ts)
        for kind, metrics in sorted((point.metrics_by_kind or {}).items()):
            frame = HealthDay(
                day=point.bucket.date(),
                kind=kind,
                unit=HEALTH_KINDS[kind].unit,
                metrics=metrics,
                interval_start=start,
                interval_end=end,
                full_day_window=start == point.bucket and end == day_end,
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
