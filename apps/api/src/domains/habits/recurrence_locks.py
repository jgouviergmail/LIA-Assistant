"""Recurrence locks — the pure shape-lock evaluation of ADR-214 (v2 of ADR-140).

Owned by the habits domain since 2026-09-11: the nightly recompute needs to
evaluate every signature of a person's ledger (promotion and demotion no
longer wait for a chat turn), and ``habits`` importing the agents service
would close the agents↔habits cycle the coupling ratchet forbids — agents
already imports habits for the promotion path. The agents module keeps the
chat-side semantics (record on a turn, suggest, promote immediately) and
re-exports every name below, so its historical importers and the calibration
harness keep working unchanged.

Everything here is deterministic and I/O-free: per-day occurrence hours in,
a proven lock (or None) out. The thresholds come from settings, calibrated by
``scripts/habits/measure_calibration.py`` (ADR-214 amendment b) — recalibrate
with the harness, never by hand.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

SHAPE_DAILY = "daily"
SHAPE_WORKDAYS = "workdays"
SHAPE_WEEKLY = "weekly"
# A steady hour proven a few times a week, on no particular weekday: the
# honest label for the owner's "rare but targeted" usage (2026-09-11). The
# lock is as proven as a daily one (same R, split-half, spread and volume
# gates); only the CALENDAR promise is withheld.
SHAPE_INTERMITTENT = "intermittent"
#: The closed vocabulary every reader of a lock's shape is pinned to (the
#: suggestion text, the settings row, the heartbeat, ``days_of_week``).
RECURRENCE_SHAPES: tuple[str, ...] = (
    SHAPE_DAILY,
    SHAPE_WORKDAYS,
    SHAPE_WEEKLY,
    SHAPE_INTERMITTENT,
)


@dataclass(frozen=True, slots=True)
class RecurrenceLock:
    """A proven temporal shape for a recurring request.

    Attributes:
        shape: ``daily`` | ``workdays`` | ``weekly`` | ``intermittent``.
        trigger_hour: Learned circular-mean hour (None when the weekly lock
            held without hour concentration).
        modal_weekday: 0=Monday..6=Sunday for weekly locks, else None.
        distinct_days: Distinct days observed inside the window.
        occurrences: Total occurrences inside the window.
    """

    shape: str
    trigger_hour: float | None
    modal_weekday: int | None
    distinct_days: int
    occurrences: int

    def days_of_week(self) -> list[int]:
        """Schedule days implied by the shape (0=Monday..6=Sunday)."""
        if self.shape == SHAPE_WEEKLY and self.modal_weekday is not None:
            return [self.modal_weekday]
        if self.shape == SHAPE_WORKDAYS:
            return [0, 1, 2, 3, 4]
        if self.shape == SHAPE_INTERMITTENT:
            return []  # no calendar is implied — the hour is the habit
        return [0, 1, 2, 3, 4, 5, 6]


#: Shapes that promise a calendar slot the heartbeat can find MISSED.
#: ``intermittent`` is deliberately absent: it promises no calendar day, so
#: there is no slot to miss and nothing to offer.
SLOTTED_SHAPES: tuple[str, ...] = (SHAPE_DAILY, SHAPE_WORKDAYS, SHAPE_WEEKLY)


def circular_r(hours: list[float]) -> tuple[float, float]:
    """Resultant length R and circular mean hour of a set of hours (period 24)."""
    if not hours:
        return 0.0, 0.0
    z = sum(cmath.exp(2j * math.pi * h / 24.0) for h in hours) / len(hours)
    return abs(z), (cmath.phase(z) * 24.0 / (2 * math.pi)) % 24


def circular_hour_dist(a: float, b: float) -> float:
    """Shortest circular distance between two hours (period 24)."""
    return min((a - b) % 24, (b - a) % 24)


def evaluate_locks(
    days: dict[date, list[float]],
    today: date,
    settings: Any,
) -> RecurrenceLock | None:
    """Pure shape-lock evaluation over per-day occurrence hours.

    Rules (all deterministic, calibrated — habits plan §4.2):
    - existence: ≥ ``recurrence_min_distinct_days`` distinct days in window;
    - weekly lock: ≥ ``recurrence_weekly_min_same_dow`` distinct days on the
      modal weekday AND that weekday holds ≥ ``recurrence_weekly_dow_fraction``
      of distinct days;
    - time lock: ≥ ``recurrence_lock_min_occurrences`` occurrences spread over
      ≥ ``recurrence_lock_min_spread_days`` days with circular R ≥
      ``recurrence_lock_r_min`` AND split-half consistency (both interleaved
      halves R ≥ half_r_min, means within half_agree_hours) — the split-half
      test is what keeps sporadic usage at 0% false locks;
    - shape labeling (``_label_shape``) deferred to a calendar SPAN of ≥
      ``recurrence_shape_min_span_days``; 'workdays' when ≤
      ``recurrence_weekend_tolerance`` weekend days, else 'daily' — and either
      only when the distinct-day density over the eligible span reaches
      ``recurrence_daily_density_min``; below it the lock is 'intermittent'
      (a steady hour, no calendar promised) provided R ≥
      ``recurrence_intermittent_r_min``.

    Args:
        days: Per-local-date occurrence hours inside (or beyond) the window.
        today: The user's local date (window anchor).
        settings: Settings view (thresholds).

    Returns:
        The proven lock, or None (not recurrent enough / no stable shape yet).
    """
    window_start = today - timedelta(days=settings.recurrence_window_days)
    recent = {d: h for d, h in days.items() if d > window_start and h}
    distinct = sorted(recent.keys())
    if len(distinct) < settings.recurrence_min_distinct_days:
        return None

    occurrences = [h for d in distinct for h in recent[d]]
    r_all, mean_hour = circular_r(occurrences)

    weekly = _weekly_lock(distinct, occurrences, r_all, mean_hour, settings)
    if weekly is not None:
        return weekly
    return _time_lock(recent, distinct, occurrences, r_all, mean_hour, settings)


def _weekly_lock(
    distinct: list[date],
    occurrences: list[float],
    r_all: float,
    mean_hour: float,
    settings: Any,
) -> RecurrenceLock | None:
    """Weekly lock — distinct DAYS per weekday (same-day repeats count once)."""
    dow_days: dict[int, int] = {}
    for d in distinct:
        dow_days[d.weekday()] = dow_days.get(d.weekday(), 0) + 1
    modal_dow, modal_n = max(dow_days.items(), key=lambda kv: kv[1])
    if (
        modal_n < settings.recurrence_weekly_min_same_dow
        or modal_n / len(distinct) < settings.recurrence_weekly_dow_fraction
    ):
        return None
    return RecurrenceLock(
        shape=SHAPE_WEEKLY,
        trigger_hour=mean_hour if r_all >= settings.recurrence_lock_r_min else None,
        modal_weekday=modal_dow,
        distinct_days=len(distinct),
        occurrences=len(occurrences),
    )


def _split_halves_agree(
    recent: dict[date, list[float]], distinct: list[date], settings: Any
) -> bool:
    """Split-half consistency — what keeps sporadic usage at 0% false locks."""
    ordered = [h for d in distinct for h in sorted(recent[d])]
    r1, m1 = circular_r(ordered[0::2])
    r2, m2 = circular_r(ordered[1::2])
    return bool(
        r1 >= settings.recurrence_lock_half_r_min
        and r2 >= settings.recurrence_lock_half_r_min
        and circular_hour_dist(m1, m2) <= settings.recurrence_lock_half_agree_hours
    )


def _label_shape(distinct: list[date], r_all: float, settings: Any) -> str | None:
    """Name the temporal shape of a PROVEN time lock, or None to defer.

    Labeling is deferred until the CALENDAR has spoken (early labeling
    mislabeled daily habits as workdays — measured). Counting DISTINCT days
    here made a light-but-steady user unlabelable forever: 3x/week never
    reaches 14 distinct days, however long the pattern holds (measured
    2026-09-11 — 31 % of such users locked, every one labeled "daily").

    Density over the ELIGIBLE span (weekdays only for a workdays candidate)
    decides the LABEL, never the lock: a steady hour proven a few times a
    week is a real habit, and calling it "daily" would put a false promise
    in the suggestion text.

    Args:
        distinct: Sorted distinct occurrence days inside the window.
        r_all: Circular concentration of every occurrence hour.
        settings: Settings view (span, density, intermittent-R thresholds).

    Returns:
        A ``SHAPE_*`` value, or None (span still building, or an
        under-concentrated hour on the intermittent path).
    """
    span_days = (distinct[-1] - distinct[0]).days + 1
    if span_days < settings.recurrence_shape_min_span_days:
        return None
    weekend_days = sum(1 for d in distinct if d.weekday() >= 5)
    if weekend_days <= settings.recurrence_weekend_tolerance:
        candidate = SHAPE_WORKDAYS
        eligible = sum(
            1 for k in range(span_days) if (distinct[0] + timedelta(days=k)).weekday() < 5
        )
    else:
        candidate = SHAPE_DAILY
        eligible = span_days
    density = len(distinct) / eligible if eligible else 0.0
    if density >= settings.recurrence_daily_density_min:
        return candidate
    # An hour promised WITHOUT a calendar must be tighter still: waking-arc
    # uniform hours carry R~0.53 intrinsically and clear the 0.8 gate by
    # luck 3 % of the time at light volumes (measured 2026-09-11).
    if r_all < settings.recurrence_intermittent_r_min:
        return None
    return SHAPE_INTERMITTENT


def _time_lock(
    recent: dict[date, list[float]],
    distinct: list[date],
    occurrences: list[float],
    r_all: float,
    mean_hour: float,
    settings: Any,
) -> RecurrenceLock | None:
    """Time lock (daily/workdays) with split-half consistency and deferred labeling."""
    if len(occurrences) < settings.recurrence_lock_min_occurrences:
        return None
    if (distinct[-1] - distinct[0]).days < settings.recurrence_lock_min_spread_days:
        return None
    if r_all < settings.recurrence_lock_r_min:
        return None
    if not _split_halves_agree(recent, distinct, settings):
        return None
    shape = _label_shape(distinct, r_all, settings)
    if shape is None:
        return None
    return RecurrenceLock(
        shape=shape,
        trigger_hour=mean_hour,
        modal_weekday=None,
        distinct_days=len(distinct),
        occurrences=len(occurrences),
    )
