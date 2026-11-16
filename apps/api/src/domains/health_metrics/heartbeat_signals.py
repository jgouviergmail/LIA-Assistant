"""Heartbeat health-signals payload builder.

Builds the ``health_signals`` block the Heartbeat context aggregator attaches
to its LLM decision context: today's summary per kind, the baseline delta per
kind, and the notable variations / events across kinds.

Extracted from ``service.py`` (v1.25.18): the builder is the only consumer of
this composition, and ``HealthMetricsService`` had no room left under the
600-SLOC cap. Keeping it inside the health domain — rather than in
``domains/heartbeat/`` — preserves the boundary: the heartbeat asks for a
payload, it does not learn how kinds, baselines and specs work.

**Read path.** One per-day rollup per kind, fetched ONCE and reused for both
the baseline delta and the variation detectors. The previous shape called
``compute_kind_baseline_delta`` and ``detect_all_variations``, each re-fetching
the same 36-day window per kind: 6 queries and ~30 000 raw rows per heartbeat
tick, whose decode blocked the event loop long enough to blow the aggregator's
2-second budget on roughly half the ticks. The 24-hour ``summary_today`` window
is one SQL summary (``fetch_window_summary``): its value counted through the
fusion door, its freshness read off the latest sample received. Days are the
person's, cut at their midnight (ADR-148 amendment 2026-11-14).

Phase: evolution — Health Metrics × Heartbeat
Created: 2026-07-24
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS,
    HEALTH_METRICS_HEARTBEAT_FRESHNESS_MINUTES,
)
from src.core.local_day import local_today
from src.domains.health_metrics.baseline import (
    DailyStat,
    baseline_window_start,
    compute_kind_delta_from_stats,
)
from src.domains.health_metrics.kinds import (
    HEALTH_KINDS,
    AggregationMethod,
    HealthKindSpec,
)
from src.domains.health_metrics.repository import HealthSampleRepository, WindowSummary
from src.domains.health_metrics.signals import (
    detect_notable_events_from_stats,
    detect_recent_variations_from_stats,
)


async def build_heartbeat_health_signals(
    db: AsyncSession,
    user_id: UUID,
    *,
    zone: ZoneInfo,
) -> dict[str, Any] | None:
    """Return the structured health-signals payload for the Heartbeat source.

    Combines:

    - ``summary_today`` — aggregated value + freshness per kind, over the last
      :data:`HEALTH_METRICS_HEARTBEAT_FRESHNESS_MINUTES`.
    - ``baseline_deltas_7d`` — recent window vs baseline, per kind.
    - ``recent_variations`` / ``notable_events`` — directional streaks and
      structural events across kinds.

    All windows derive from a single ``now``, so every number in one payload
    describes the same instant (the previous shape let each sub-computation
    take its own clock reading).

    Args:
        db: Session owned by the caller; the fetches are sequential, so it is
            never used concurrently.
        user_id: Owner user UUID.
        zone: The person's zone, where days are cut.

    Returns:
        A dict ready to attach to ``HeartbeatContext.health_signals``, or
        ``None`` when the user has neither fresh samples nor any baseline
        across every kind (nothing meaningful to inject).
    """
    repo = HealthSampleRepository(db)
    now = datetime.now(UTC)
    freshness_cutoff = now - timedelta(minutes=HEALTH_METRICS_HEARTBEAT_FRESHNESS_MINUTES)
    # Same window as compute_kind_baseline_delta: the full rolling baseline
    # span PLUS the recent window on top of it, at the person's midnight.
    from_ts = baseline_window_start(now, zone, recent_days=HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS)
    today = local_today(now, zone)

    summary_today: dict[str, dict[str, Any]] = {}
    baseline_deltas: dict[str, dict[str, Any]] = {}
    stats_by_kind: dict[str, list[DailyStat]] = {}
    any_data = False

    for spec in HEALTH_KINDS.values():
        stats = await repo.fetch_daily_stats(
            user_id, kind=spec.kind, zone=zone, from_ts=from_ts, to_ts=now
        )
        stats_by_kind[spec.kind] = stats

        recent = await repo.fetch_window_summary(
            user_id, kind=spec.kind, from_ts=freshness_cutoff, to_ts=now
        )
        value = _summary_value(spec, recent)
        if value is not None and recent.last_start is not None:
            any_data = True
            summary_today[spec.kind] = {
                "value": value,
                "unit": spec.unit,
                "last_update_minutes_ago": int((now - recent.last_start).total_seconds() / 60),
            }

        delta = compute_kind_delta_from_stats(stats, spec, HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS)
        if delta["mode"] != "empty":
            baseline_deltas[spec.kind] = {
                "pct": delta["delta_pct"],
                "mode": delta["mode"],
                "baseline_value": delta["baseline_value"],
            }

    if not any_data and not baseline_deltas:
        return None

    recent_variations: list[dict[str, Any]] = []
    notable_events: list[dict[str, Any]] = []
    for spec in HEALTH_KINDS.values():
        stats = stats_by_kind[spec.kind]
        if not stats:
            continue
        variation = detect_recent_variations_from_stats(
            stats, spec, window_days=HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS
        )
        if variation is not None:
            recent_variations.append(variation)
        notable_events.extend(
            detect_notable_events_from_stats(
                stats, spec, today=today, window_days=HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS
            )
        )

    return {
        "summary_today": summary_today,
        "baseline_deltas_7d": baseline_deltas,
        "recent_variations": recent_variations,
        "notable_events": notable_events,
    }


def _summary_value(spec: HealthKindSpec, window: WindowSummary) -> int | float | None:
    """Single-scalar representation of the recent window for the Heartbeat card.

    - ``SUM`` aggregation → the counted total (e.g. steps, overlaps fused).
    - ``AVG_MIN_MAX`` aggregation → rounded average (e.g. heart rate).
    - ``LAST_VALUE`` aggregation → last recorded value.

    Args:
        spec: Kind spec.
        window: The recent window's summary.

    Returns:
        A scalar summarizing the window for the kind, or None when nothing
        counts in it.
    """
    counted = window.counted
    if counted is None:
        return None
    match spec.aggregation_method:
        case AggregationMethod.SUM:
            return round(counted.total)
        case AggregationMethod.AVG_MIN_MAX:
            return round(counted.total / counted.rows, 1)
        case AggregationMethod.LAST_VALUE:
            return window.last_value
