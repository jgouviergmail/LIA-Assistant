"""Adaptive baseline computation for health metrics.

Produces a per-user, per-kind **baseline value** — the central tendency
of a user's recent samples, used by assistant tools and the Heartbeat
source to phrase relative comparisons ("steps today: 3 200, baseline:
8 500, −62 %").

Two modes, chosen automatically based on data availability:

- **bootstrap** — median of all available samples. Used when the history
  is too short for a trustworthy rolling median (``days_available <
  settings.health_metrics_baseline_min_days``, default 7 days).
- **rolling** — median of the last 28 days of per-day aggregates. Used
  once enough history is accumulated.

The output dict carries the mode label so downstream consumers (tools,
LLM prompts) can qualify their statements honestly (e.g. "based on
4 days of data" vs. "28-day average").

Per-day aggregation follows the kind's
:class:`src.domains.health_metrics.kinds.BaselineKind`:

- ``DAILY_SUM`` → sum samples per day (e.g. steps: total daily count)
- ``DAILY_AVG`` → mean samples per day (e.g. heart_rate: avg daily bpm)
- ``RESTING`` → placeholder (requires sleep-aware filtering, added with
  the future ``sleep_duration`` kind)

Module is DB-access free, and keeps unit-testable in isolation (no Postgres
required). Every computation consumes a pre-aggregated :class:`DailyStat`
series — what
:meth:`~src.domains.health_metrics.repository.HealthSampleRepository.fetch_daily_stats`
returns, the person's local days counted through the fusion door
(``fusion.counted_samples``). There is no second, raw-sample path: an
in-Python grouping by UTC day over unfused samples was one, and it would now
disagree with every reader (ADR-148 amendment 2026-11-14).

Phase: evolution — Health Metrics (assistant agents v1.17.2)
Created: 2026-04-22
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Literal
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS
from src.core.local_day import local_midnight, local_today
from src.domains.health_metrics.kinds import BaselineKind, HealthKindSpec

BaselineMode = Literal["empty", "bootstrap", "rolling"]


@dataclass(frozen=True, slots=True)
class BaselineResult:
    """Baseline computation outcome.

    Attributes:
        mode: Which mode produced the result (``"empty"`` / ``"bootstrap"``
            / ``"rolling"``). Consumers should surface this to the LLM so
            claims can be qualified appropriately.
        median_value: The computed baseline (None if no data at all).
        days_available: How many distinct days of data contributed.
    """

    mode: BaselineMode
    median_value: float | None
    days_available: int


@dataclass(frozen=True, slots=True)
class DailyStat:
    """Aggregate primitives for one local day of a single kind.

    Carries **raw integer primitives** rather than a pre-reduced value on
    purpose: every :class:`~src.domains.health_metrics.kinds.BaselineKind`
    aggregation is derivable from them, and ``detect_notable_events`` needs
    the raw daily ``total`` regardless of the kind's baseline aggregation.

    Attributes:
        day: The person's calendar day the counted rows start on.
        total: Sum of the day's counted values, rounded to a whole count.
        count: Counted rows that day (always >= 1): samples of a ``KEEP_ALL``
            kind, fused slices of a ``MAX_RATE`` one.
        minimum: Smallest counted value of the day, rounded.
    """

    day: date
    total: int
    count: int
    minimum: int


# =============================================================================
# Per-day aggregation helpers
# =============================================================================


def _stat_value(stat: DailyStat, baseline_kind: BaselineKind) -> float:
    """Reduce one day's aggregate primitives to its baseline value.

    Single source of truth for the per-day reduction.

    Args:
        stat: One day's aggregate primitives.
        baseline_kind: Aggregation semantics for the kind at hand.

    Returns:
        The day's scalar value for baseline/variation computations.
    """
    match baseline_kind:
        case BaselineKind.DAILY_SUM:
            return float(stat.total)
        case BaselineKind.DAILY_AVG:
            return stat.total / stat.count
        case BaselineKind.RESTING:
            # Placeholder: until sleep-aware filtering, treat as min
            # (conservative — the lowest value tends to be the resting
            # sample of the day). Will be revised when sleep_duration
            # kind lands.
            return float(stat.minimum)


def daily_values(
    stats: list[DailyStat],
    baseline_kind: BaselineKind,
) -> list[float]:
    """Reduce a per-day series to one value per day, day order preserved.

    Args:
        stats: Per-day aggregates, day ascending (the repository rollup).
        baseline_kind: Aggregation semantics for the kind at hand.

    Returns:
        One float per day, in the same order. Empty list if no days.
    """
    return [_stat_value(stat, baseline_kind) for stat in stats]


# =============================================================================
# Baseline computation
# =============================================================================


def compute_baseline_from_stats(
    stats: list[DailyStat],
    spec: HealthKindSpec,
    window_days: int | None = None,
) -> BaselineResult:
    """Compute an adaptive baseline from a per-day series.

    Mode selection:
    - If no data at all → ``"empty"`` with ``median_value=None``.
    - If ``days_available < settings.health_metrics_baseline_min_days`` →
      ``"bootstrap"`` (median of whatever is available).
    - Else → ``"rolling"`` (median of the last ``window_days`` of daily
      aggregates, defaulting to
      :data:`HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS`).

    Args:
        stats: Per-day aggregates covering the baseline lookup window, day
            ascending. Days without a sample are simply absent.
        spec: Spec of the kind (drives per-day reduction via
            ``spec.baseline_kind``).
        window_days: Explicit rolling window size; defaults to
            :data:`HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS`.

    Returns:
        A :class:`BaselineResult` carrying the mode, median, and days count.
    """
    daily = daily_values(stats, spec.baseline_kind)
    days_available = len(daily)

    if days_available == 0:
        return BaselineResult(mode="empty", median_value=None, days_available=0)

    if days_available < settings.health_metrics_baseline_min_days:
        return BaselineResult(
            mode="bootstrap",
            median_value=median(daily),
            days_available=days_available,
        )

    rolling_window = window_days or HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS
    rolling_slice = daily[-rolling_window:]
    return BaselineResult(
        mode="rolling",
        median_value=median(rolling_slice),
        days_available=len(rolling_slice),
    )


def compute_kind_delta_from_stats(
    stats: list[DailyStat],
    spec: HealthKindSpec,
    window_days: int,
) -> dict[str, Any]:
    """Compare the tail of a per-day series to the baseline that precedes it.

    Pure counterpart of
    :meth:`~src.domains.health_metrics.service.HealthMetricsService.compute_kind_baseline_delta`:
    the service owns the window fetch, this owns the payload.

    The recent window is the last ``window_days`` **days present in the
    series** (not calendar days), the baseline everything before it:
    ``stats`` is day-ascending with one entry per day.

    Args:
        stats: Per-day aggregates covering the baseline window *plus* the
            recent window, day ascending.
        spec: Spec of the kind.
        window_days: Recent window length in days.

    Returns:
        A dict shaped for LLM consumption. On an empty series, mode is
        ``"empty"`` with null values and **no** ``days_available`` key —
        consumers branch on ``mode``.
    """
    if not stats:
        return {
            "kind": spec.kind,
            "unit": spec.unit,
            "mode": "empty",
            "baseline_value": None,
            "window_value": None,
            "delta_pct": None,
            "window_days": window_days,
        }

    split = min(window_days, len(stats))
    baseline = compute_baseline_from_stats(stats[:-split], spec)
    window_values = daily_values(stats[-split:], spec.baseline_kind)
    window_value = sum(window_values) / len(window_values) if window_values else None

    delta_pct: float | None = None
    if baseline.median_value and window_value is not None and baseline.median_value != 0:
        delta_pct = round((window_value - baseline.median_value) / baseline.median_value * 100.0, 1)

    return {
        "kind": spec.kind,
        "unit": spec.unit,
        "mode": baseline.mode,
        "baseline_value": (
            round(baseline.median_value, 1) if baseline.median_value is not None else None
        ),
        "window_value": round(window_value, 1) if window_value is not None else None,
        "delta_pct": delta_pct,
        "window_days": window_days,
        "days_available": baseline.days_available,
    }


# =============================================================================
# Public helper: resolve baseline for a user/kind (thin DB wrapper)
# =============================================================================


def baseline_window_start(now: datetime, zone: ZoneInfo, *, recent_days: int) -> datetime:
    """The local midnight a baseline read starts at.

    The rolling window, one day of margin, and the recent window compared
    against it on top — every day of the series whole, cut at the person's
    midnight (ADR-148 amendment 2026-11-14).

    Args:
        now: The current instant.
        zone: The person's zone.
        recent_days: The recent window the read compares (0 for none).

    Returns:
        The UTC instant of that local midnight.
    """
    days = HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS + 1 + recent_days
    return local_midnight(local_today(now, zone) - timedelta(days=days), zone)
