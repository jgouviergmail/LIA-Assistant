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

Module is DB-access free: it works on a list of
:class:`src.domains.health_metrics.models.HealthSample` passed by the
caller. This keeps it unit-testable in isolation (no Postgres required).

Phase: evolution — Health Metrics (assistant agents v1.17.2)
Created: 2026-04-22
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Literal

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


# =============================================================================
# Per-day aggregation helpers
# =============================================================================


def _group_samples_by_day(samples: list[HealthSample]) -> dict[date, list[int]]:
    """Group samples by their UTC date (from ``date_start``)."""
    by_day: dict[date, list[int]] = {}
    for s in samples:
        day = s.date_start.astimezone(UTC).date()
        by_day.setdefault(day, []).append(int(s.value))
    return by_day


def _daily_aggregate(
    samples: list[HealthSample],
    baseline_kind: BaselineKind,
) -> list[float]:
    """Reduce samples to one value per day according to the baseline kind.

    Args:
        samples: Raw samples (any kind — filtering happens upstream).
        baseline_kind: Aggregation semantics for the kind at hand.

    Returns:
        Daily aggregates as a list of floats, sorted by day ascending.
        Empty list if no samples.
    """
    by_day = _group_samples_by_day(samples)
    if not by_day:
        return []
    sorted_days = sorted(by_day.keys())
    result: list[float] = []
    for day in sorted_days:
        values = by_day[day]
        match baseline_kind:
            case BaselineKind.DAILY_SUM:
                result.append(float(sum(values)))
            case BaselineKind.DAILY_AVG:
                result.append(sum(values) / len(values))
            case BaselineKind.RESTING:
                # Placeholder: until sleep-aware filtering, treat as min
                # (conservative — the lowest value tends to be the resting
                # sample of the day). Will be revised when sleep_duration
                # kind lands.
                result.append(float(min(values)))
    return result


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
    daily = _daily_aggregate(samples, spec.baseline_kind)
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
