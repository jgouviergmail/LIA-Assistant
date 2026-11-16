"""Recent-variations detection on health metrics.

Produces **factual signals** (not medical interpretation) describing how
a user's recent history compares to their baseline. Two complementary
detectors:

- :func:`detect_recent_variations_from_stats` — finds directional streaks
  (consecutive days above or below baseline). Flags a variation as
  ``notable`` when the streak is long enough and the average delta large
  enough (both tunable via ``.env``).
- :func:`detect_notable_events_from_stats` — flags structural events such as
  inactivity streaks (steps stuck at 0 for multiple days).

Outputs are pure dicts/lists, ready to feed into LLM prompts or the
Heartbeat context aggregator. No medical conclusions drawn — only
quantified facts.

Module is DB-access free. Both detectors consume a pre-aggregated
:class:`~src.domains.health_metrics.baseline.DailyStat` series — the
repository rollup of the person's local days, counted through the fusion door
(ADR-148 amendment 2026-11-14) — and only ever reason per day.

Phase: evolution — Health Metrics (assistant agents v1.17.2)
Created: 2026-04-22
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from src.core.config import settings
from src.core.constants import HEALTH_METRICS_INACTIVITY_STREAK_MIN_DAYS
from src.domains.health_metrics.baseline import (
    DailyStat,
    compute_baseline_from_stats,
    daily_values,
)
from src.domains.health_metrics.kinds import HealthKindSpec

TrendDirection = Literal["rising", "falling", "stable"]


# =============================================================================
# Streak detection
# =============================================================================


def _find_longest_trend_streak(
    deltas: list[tuple[date, float]],
    min_daily_delta: float,
) -> tuple[TrendDirection, int, float]:
    """Find the longest consecutive-day streak with the same directional sign.

    A day counts as ``rising`` if ``delta > min_daily_delta``, ``falling`` if
    ``delta < -min_daily_delta``, ``stable`` otherwise (and breaks the streak).

    Args:
        deltas: Ordered list of ``(day, delta_pct)`` tuples (window days only).
        min_daily_delta: Per-day threshold (percent) to count as part of a
            streak. Days with absolute delta below this break any ongoing
            streak (treated as ``stable``).

    Returns:
        Tuple ``(trend, days, avg_delta_pct)``:

        - ``trend`` — dominant direction of the longest streak
          (``"rising"``/``"falling"``/``"stable"`` if no directional streak).
        - ``days`` — length of the streak in days.
        - ``avg_delta_pct`` — average delta across the streak (signed).
    """
    if not deltas:
        return "stable", 0, 0.0

    # Classify each day's direction
    directions: list[TrendDirection] = []
    for _, delta in deltas:
        if delta > min_daily_delta:
            directions.append("rising")
        elif delta < -min_daily_delta:
            directions.append("falling")
        else:
            directions.append("stable")

    # Find longest consecutive run of same non-stable direction
    best_dir: TrendDirection = "stable"
    best_length = 0
    best_sum = 0.0
    current_dir: TrendDirection = "stable"
    current_length = 0
    current_sum = 0.0

    for direction, (_, delta) in zip(directions, deltas, strict=True):
        if direction == current_dir and direction != "stable":
            current_length += 1
            current_sum += delta
        else:
            if current_length > best_length and current_dir != "stable":
                best_length = current_length
                best_sum = current_sum
                best_dir = current_dir
            current_dir = direction
            current_length = 1 if direction != "stable" else 0
            current_sum = delta if direction != "stable" else 0.0

    # Final flush
    if current_length > best_length and current_dir != "stable":
        best_length = current_length
        best_sum = current_sum
        best_dir = current_dir

    avg = (best_sum / best_length) if best_length > 0 else 0.0
    return best_dir, best_length, avg


# =============================================================================
# Variations detector
# =============================================================================


def detect_recent_variations_from_stats(
    stats: list[DailyStat],
    spec: HealthKindSpec,
    window_days: int = 7,
) -> dict[str, Any] | None:
    """Detect a notable directional variation for a kind over a recent window.

    Algorithm:

    1. Reduce ``stats`` to per-day values using ``spec.baseline_kind``.
    2. Split the timeline into a *window* (last ``window_days`` days) and a
       *baseline prefix* (everything earlier).
    3. Compute the baseline median with adaptive mode selection (``bootstrap``
       if the prefix is too short, otherwise ``rolling`` over
       :data:`HEALTH_METRICS_BASELINE_ROLLING_WINDOW_DAYS`).
    4. Compute per-day deltas (percent of baseline) for the window days.
    5. Find the longest consecutive-day streak in the same direction.
    6. Flag the variation as ``notable`` iff
       ``streak_days >= settings.health_metrics_variation_min_days`` **and**
       ``abs(avg_delta_pct) >= settings.health_metrics_variation_min_delta_pct``.

    Args:
        stats: Per-day aggregates for a single kind covering the baseline
            lookup window + ``window_days``, day ascending. The window is the
            last ``window_days`` days PRESENT in the series, the baseline the
            prefix before it.
        spec: Spec of the kind under analysis (drives per-day aggregation).
        window_days: Recent-window length in days. Defaults to 7.

    Returns:
        A dict describing the variation when notable::

            {
                "kind": str,
                "trend": "rising" | "falling",
                "days": int,
                "delta_pct": float,          # signed average over the streak
                "notable": True,
                "baseline_mode": "bootstrap" | "rolling",
                "baseline_value": float,
            }

        Returns ``None`` when:
        - There is no data.
        - The baseline is ``empty`` or zero (division would be meaningless).
        - No streak meets the thresholds.
    """
    if not stats:
        return None

    # Window = last N days present; baseline = the prefix before it. With no
    # more days than the window, everything is BOTH (kept from the raw-sample
    # implementation — a short history compares against itself).
    if len(stats) <= window_days:
        window_stats, baseline_stats = stats, stats
    else:
        window_stats, baseline_stats = stats[-window_days:], stats[:-window_days]

    baseline = compute_baseline_from_stats(baseline_stats, spec)
    base = baseline.median_value
    if baseline.mode == "empty" or base is None or base == 0:
        return None

    # strict=True encodes the invariant the raw-sample version defended
    # against at runtime: one reduced value per day, always.
    deltas: list[tuple[date, float]] = [
        (stat.day, (value - base) / base * 100.0)
        for stat, value in zip(
            window_stats, daily_values(window_stats, spec.baseline_kind), strict=True
        )
    ]

    trend, days, avg_delta = _find_longest_trend_streak(
        deltas,
        min_daily_delta=settings.health_metrics_variation_daily_delta_pct,
    )

    if (
        days < settings.health_metrics_variation_min_days
        or abs(avg_delta) < settings.health_metrics_variation_min_delta_pct
    ):
        return None

    return {
        "kind": spec.kind,
        "trend": trend,
        "days": days,
        "delta_pct": round(avg_delta, 1),
        "notable": True,
        "baseline_mode": baseline.mode,
        "baseline_value": round(base, 1),
    }


# =============================================================================
# Notable events detector
# =============================================================================


def detect_notable_events_from_stats(
    stats: list[DailyStat],
    spec: HealthKindSpec,
    *,
    today: date,
    window_days: int = 7,
) -> list[dict[str, Any]]:
    """Detect structural events (not variations) worth reporting.

    Currently covers **inactivity_streak** (``kind == "steps"`` only) —
    consecutive days with total ``steps == 0``, flagged when the streak
    reaches :data:`HEALTH_METRICS_INACTIVITY_STREAK_MIN_DAYS`.

    Reads ``DailyStat.total`` — the daily **sum** — deliberately, not the
    kind's baseline reduction: an inactivity streak is "no steps recorded",
    which stays a sum whatever ``spec.baseline_kind`` says. Reducing via the
    baseline aggregation would silently misread a future ``DAILY_AVG`` kind.

    Args:
        stats: Per-day aggregates for the kind, day ascending.
        spec: Spec of the kind.
        today: The person's current local day: the series' days are theirs.
        window_days: Inspection window size in days.

    Returns:
        A list of event dicts; empty if nothing notable.
    """
    events: list[dict[str, Any]] = []

    if spec.kind == "steps":
        # Inactivity streak: trailing ``window_days`` each summing to 0.
        earliest = today - timedelta(days=window_days)
        recent = [stat for stat in stats if stat.day >= earliest][-window_days:]
        zero_streak = 0
        for stat in recent:
            zero_streak = zero_streak + 1 if stat.total == 0 else 0
        if zero_streak >= HEALTH_METRICS_INACTIVITY_STREAK_MIN_DAYS:
            events.append(
                {
                    "event": "inactivity_streak",
                    "kind": spec.kind,
                    "days": zero_streak,
                }
            )

    return events
