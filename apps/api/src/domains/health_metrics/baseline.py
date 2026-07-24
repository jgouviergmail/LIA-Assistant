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
LLM prompts) can qualify their statements honestly (e.g. "basé sur
4 jours de données" vs. "moyenne sur 28 jours").

Per-day aggregation follows the kind's
:class:`src.domains.health_metrics.kinds.BaselineKind`:

- ``DAILY_SUM`` → sum samples per day (e.g. steps: total daily count)
- ``DAILY_AVG`` → mean samples per day (e.g. heart_rate: avg daily bpm)
- ``RESTING`` → placeholder (requires sleep-aware filtering, added with
  the future ``sleep_duration`` kind)

Module is DB-access free, and keeps unit-testable in isolation (no Postgres
required). It exposes each computation twice over ONE implementation: a
``*_from_stats`` entry point consuming a pre-aggregated :class:`DailyStat`
series — what
:meth:`~src.domains.health_metrics.repository.HealthSampleRepository.fetch_daily_stats`
returns — and a raw-sample wrapper that groups first via
:func:`daily_stats_from_samples`. The two paths share :func:`_stat_value`, so
the per-day reduction cannot drift between them.

Phase: evolution — Health Metrics (assistant agents v1.17.2)
Created: 2026-04-22
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any, Literal

from src.core.config import settings
from src.core.constants import HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS
from src.domains.health_metrics.kinds import BaselineKind, HealthKindSpec
from src.domains.health_metrics.models import HealthSample

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
    """Aggregate primitives for one UTC day of samples of a single kind.

    Carries **raw integer primitives** rather than a pre-reduced value on
    purpose: every :class:`~src.domains.health_metrics.kinds.BaselineKind`
    aggregation is derivable from them, and ``detect_notable_events`` needs
    the raw daily ``total`` regardless of the kind's baseline aggregation.

    Because ``total`` and ``count`` are exact integers, ``total / count`` is
    the *same* IEEE-754 operation Python performs over the raw sample list —
    a server-side rollup is bit-identical to in-Python grouping, not merely
    close.

    Attributes:
        day: UTC calendar day the samples belong to.
        total: Sum of the day's sample values.
        count: Number of samples recorded that day (always >= 1).
        minimum: Smallest sample value of the day.
    """

    day: date
    total: int
    count: int
    minimum: int


# =============================================================================
# Per-day aggregation helpers
# =============================================================================


def daily_stats_from_samples(samples: list[HealthSample]) -> list[DailyStat]:
    """Reduce raw samples to one :class:`DailyStat` per UTC day, day ascending.

    In-Python counterpart of
    :meth:`~src.domains.health_metrics.repository.HealthSampleRepository.fetch_daily_stats`.
    Callers holding a small, already-fetched sample window (or unit tests)
    use this; callers facing a wide window let PostgreSQL do the rollup.

    Args:
        samples: Samples of a single kind (any order).

    Returns:
        One entry per day having at least one sample, ordered by day ascending.
        Days with no sample are absent — the SQL rollup cannot invent them
        either, so both paths agree.
    """
    by_day = _group_samples_by_day(samples)
    return [
        DailyStat(day=day, total=sum(by_day[day]), count=len(by_day[day]), minimum=min(by_day[day]))
        for day in sorted(by_day)
    ]


def _stat_value(stat: DailyStat, baseline_kind: BaselineKind) -> float:
    """Reduce one day's aggregate primitives to its baseline value.

    Single source of truth for the per-day reduction, shared by the raw-sample
    path and the server-side rollup path — the two must never drift.

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


def _group_samples_by_day(samples: list[HealthSample]) -> dict[date, list[int]]:
    """Group samples by their UTC date (from ``date_start``)."""
    by_day: dict[date, list[int]] = {}
    for s in samples:
        day = s.date_start.astimezone(UTC).date()
        by_day.setdefault(day, []).append(int(s.value))
    return by_day


def daily_values(
    stats: list[DailyStat],
    baseline_kind: BaselineKind,
) -> list[float]:
    """Reduce a per-day series to one value per day, day order preserved.

    Args:
        stats: Per-day aggregates, day ascending (from either the repository
            rollup or :func:`daily_stats_from_samples`).
        baseline_kind: Aggregation semantics for the kind at hand.

    Returns:
        One float per day, in the same order. Empty list if no days.
    """
    return [_stat_value(stat, baseline_kind) for stat in stats]


def _daily_aggregate(
    samples: list[HealthSample],
    baseline_kind: BaselineKind,
) -> list[float]:
    """Reduce samples to one value per day according to the baseline kind.

    Raw-sample entry point: groups, then delegates to :func:`daily_values` so
    the per-day reduction has exactly one implementation shared with the
    server-side rollup path.

    Args:
        samples: Raw samples (any kind — filtering happens upstream).
        baseline_kind: Aggregation semantics for the kind at hand.

    Returns:
        Daily aggregates as a list of floats, sorted by day ascending.
        Empty list if no samples.
    """
    return daily_values(daily_stats_from_samples(samples), baseline_kind)


# =============================================================================
# Baseline computation
# =============================================================================


def compute_baseline(
    samples: list[HealthSample],
    spec: HealthKindSpec,
    window_days: int | None = None,
) -> BaselineResult:
    """Compute an adaptive baseline for a kind over a window.

    Mode selection:
    - If no data at all → ``"empty"`` with ``median_value=None``.
    - If ``days_available < settings.health_metrics_baseline_min_days`` →
      ``"bootstrap"`` (median of whatever is available).
    - Else → ``"rolling"`` (median of the last ``window_days`` of daily
      aggregates, defaulting to
      :data:`HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS`).

    Args:
        samples: Samples in the baseline lookup window. The caller is
            responsible for pre-filtering to the kind and fetching a
            generous enough history (≥ ``window_days``). Ordering is not
            required — daily aggregation groups by UTC date.
        spec: Spec of the kind (drives per-day aggregation via
            ``spec.baseline_kind``).
        window_days: Explicit rolling window size; defaults to
            :data:`HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS`.

    Returns:
        A :class:`BaselineResult` carrying the mode, median, and days count.
    """
    return compute_baseline_from_stats(daily_stats_from_samples(samples), spec, window_days)


def compute_baseline_from_stats(
    stats: list[DailyStat],
    spec: HealthKindSpec,
    window_days: int | None = None,
) -> BaselineResult:
    """Compute an adaptive baseline from a per-day series.

    Same contract and mode selection as :func:`compute_baseline`, one layer
    lower: callers that already hold per-day aggregates (the server-side
    rollup) skip the sample grouping entirely.

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
    series** (not calendar days), the baseline everything before it — the
    exact split the raw-sample path performs on the same cutoff day, because
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


def baseline_window_start(now: datetime, window_days: int | None = None) -> datetime:
    """Return the UTC ``from_ts`` that covers a full rolling baseline window.

    Used by callers to fetch samples from the repository before calling
    :func:`compute_baseline`. Adds a one-day safety margin so the last day
    of the window is always fully populated even across timezone edges.

    Args:
        now: Current UTC datetime.
        window_days: Explicit window size; defaults to
            :data:`HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS`.

    Returns:
        Timezone-aware UTC datetime at the start of the lookup window.
    """
    days = window_days or HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS
    return (now - timedelta(days=days + 1)).astimezone(UTC)
