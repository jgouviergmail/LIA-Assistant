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
stays on raw samples on purpose — it is a few hundred rows and needs
per-sample semantics (``_summary_value``, last-sample freshness) that a per-day
rollup cannot express.

Phase: evolution — Health Metrics × Heartbeat
Created: 2026-07-24
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS,
    HEALTH_METRICS_HEARTBEAT_FRESHNESS_MINUTES,
)
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
from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.repository import HealthSampleRepository
from src.domains.health_metrics.signals import (
    detect_notable_events_from_stats,
    detect_recent_variations_from_stats,
)


async def build_heartbeat_health_signals(
    db: AsyncSession,
    user_id: UUID,
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

    Returns:
        A dict ready to attach to ``HeartbeatContext.health_signals``, or
        ``None`` when the user has neither fresh samples nor any baseline
        across every kind (nothing meaningful to inject).
    """
    repo = HealthSampleRepository(db)
    now = datetime.now(UTC)
    freshness_cutoff = now - timedelta(minutes=HEALTH_METRICS_HEARTBEAT_FRESHNESS_MINUTES)
    # Same window as compute_kind_baseline_delta: the full rolling baseline
    # span PLUS the recent window on top of it.
    from_ts = baseline_window_start(now) - timedelta(days=HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS)

    summary_today: dict[str, dict[str, Any]] = {}
    baseline_deltas: dict[str, dict[str, Any]] = {}
    stats_by_kind: dict[str, list[DailyStat]] = {}
    any_data = False

    for spec in HEALTH_KINDS.values():
        stats = await repo.fetch_daily_stats(user_id, kind=spec.kind, from_ts=from_ts, to_ts=now)
        stats_by_kind[spec.kind] = stats

        samples_today = await repo.fetch_samples_kind(
            user_id, kind=spec.kind, from_ts=freshness_cutoff, to_ts=now
        )
        if samples_today:
            any_data = True
            last_sample = samples_today[-1]
            summary_today[spec.kind] = {
                "value": _summary_value(spec, samples_today),
                "unit": spec.unit,
                "last_update_minutes_ago": int((now - last_sample.date_start).total_seconds() / 60),
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
                stats, spec, window_days=HEALTH_METRICS_AGENT_SUMMARY_WINDOW_DAYS
            )
        )

    return {
        "summary_today": summary_today,
        "baseline_deltas_7d": baseline_deltas,
        "recent_variations": recent_variations,
        "notable_events": notable_events,
    }


def _summary_value(spec: HealthKindSpec, samples: list[HealthSample]) -> int | float:
    """Single-scalar representation of today's samples for the Heartbeat card.

    - ``SUM`` aggregation → total across the window (e.g. steps).
    - ``AVG_MIN_MAX`` aggregation → rounded average (e.g. heart rate).
    - ``LAST_VALUE`` aggregation → last recorded value.

    Args:
        spec: Kind spec.
        samples: Non-empty list of samples, ordered by ``date_start`` ascending.

    Returns:
        A scalar summarizing today's data for the kind.
    """
    values = [int(s.value) for s in samples]
    match spec.aggregation_method:
        case AggregationMethod.SUM:
            return sum(values)
        case AggregationMethod.AVG_MIN_MAX:
            return round(sum(values) / len(values), 1)
        case AggregationMethod.LAST_VALUE:
            return values[-1]
