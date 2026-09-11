"""Measure the habit detectors' calibration — a MEASUREMENT, never a gate.

The thresholds in ``core/config/habits.py`` and ``core/config/automation.py``
were calibrated by a simulation harness that lived in a scratchpad and was
lost (ADR-214 says "replay the harness" — there was nothing left to replay).
This script is that harness, kept in the repository, and it runs the REAL
detectors (``compute_rhythm_profile``, ``evaluate_locks``) over:

- deterministic synthetic populations — a user with no time structure (the
  false-positive floor), a habitual user with 15 % and 35 % off-window noise
  (the detection ceiling), a night-owl whose activity spreads over 24 h;
- MODERATE populations (2026-09-11, owner direction): a personal assistant
  is proactive, so a person may interact rarely but at targeted moments —
  a few evenings a week always 20-22h, a weekly ritual, a request made a
  few times a week at a steady hour. Each targeted population has a
  same-volume scattered control, because the false-positive risk of a
  relaxed threshold lives at LOW volume (fewer points, luckier windows);
- optionally, a REAL activity series exported from an instance (counts only:
  per-day hour histograms and per-signature occurrence hours).

Two kinds of tables come out:

- the historical grids (capture x selectivity, R): false-positive and
  detection rates at the FULL window — the anchors the unit tests pin;
- trajectory tables per named THRESHOLD SET: detection rate at each horizon
  (days since first activity). Time-to-detection is the product metric for
  a proactive assistant — "after how long does LIA know my rhythm?".

For each candidate set the tables show the false-positive cost next to the
detection gain. Lowering a threshold until a series "passes" is exactly what
this tool exists to make VISIBLE as a false-positive cost, not to hide.

Usage (from apps/api):
    .venv/Scripts/python scripts/habits/measure_calibration.py --trials 100
    .venv/Scripts/python scripts/habits/measure_calibration.py --real series.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core import constants as C  # noqa: E402
from src.domains.habits.recurrence_locks import evaluate_locks  # noqa: E402
from src.domains.habits.rhythm import RhythmThresholds, compute_rhythm_profile  # noqa: E402

# The baseline every sweep starts from is the SHIPPED calibration — the
# ``*_DEFAULT`` constants, never the live ``settings``: under ``task`` the
# root .env is injected into every command, so a developer's or an
# operator's overrides would silently become the "current" row and the
# measurement would differ by launcher (the trap ``tests/conftest.py`` closes
# for the test suite). Reading constants also spares the four placeholder
# secrets a ``settings`` import would demand.
SHIPPED_RHYTHM = SimpleNamespace(
    habits_window_days=C.HABITS_WINDOW_DAYS_DEFAULT,
    habits_half_life_days=C.HABITS_HALF_LIFE_DAYS_DEFAULT,
    habits_presence_min=C.HABITS_PRESENCE_MIN_DEFAULT,
    habits_wilson_floor=C.HABITS_WILSON_FLOOR_DEFAULT,
    habits_half_presence_min=C.HABITS_HALF_PRESENCE_MIN_DEFAULT,
    habits_capture_min=C.HABITS_CAPTURE_MIN_DEFAULT,
    habits_selectivity_min=C.HABITS_SELECTIVITY_MIN_DEFAULT,
    habits_exit_presence=C.HABITS_EXIT_PRESENCE_DEFAULT,
    habits_exit_capture=C.HABITS_EXIT_CAPTURE_DEFAULT,
    habits_exit_selectivity=C.HABITS_EXIT_SELECTIVITY_DEFAULT,
    habits_min_neff_weekday=C.HABITS_MIN_NEFF_WEEKDAY_DEFAULT,
    habits_min_neff_weekend=C.HABITS_MIN_NEFF_WEEKEND_DEFAULT,
    habits_recent_days=C.HABITS_RECENT_DAYS_DEFAULT,
    habits_recent_min=C.HABITS_RECENT_MIN_DEFAULT,
    habits_max_claimed_hours=C.HABITS_MAX_CLAIMED_HOURS_DEFAULT,
    habits_waking_hours=C.HABITS_WAKING_HOURS_DEFAULT,
    habits_sparse_active_days_min=C.HABITS_SPARSE_ACTIVE_DAYS_MIN_DEFAULT,
)
SHIPPED_RECURRENCE = SimpleNamespace(
    recurrence_window_days=C.RECURRENCE_WINDOW_DAYS_DEFAULT,
    recurrence_min_distinct_days=C.RECURRENCE_MIN_DISTINCT_DAYS_DEFAULT,
    recurrence_weekly_min_same_dow=C.RECURRENCE_WEEKLY_MIN_SAME_DOW_DEFAULT,
    recurrence_weekly_dow_fraction=C.RECURRENCE_WEEKLY_DOW_FRACTION_DEFAULT,
    recurrence_lock_min_occurrences=C.RECURRENCE_LOCK_MIN_OCCURRENCES_DEFAULT,
    recurrence_lock_min_spread_days=C.RECURRENCE_LOCK_MIN_SPREAD_DAYS_DEFAULT,
    recurrence_lock_r_min=C.RECURRENCE_LOCK_R_MIN_DEFAULT,
    recurrence_lock_half_r_min=C.RECURRENCE_LOCK_HALF_R_MIN_DEFAULT,
    recurrence_lock_half_agree_hours=C.RECURRENCE_LOCK_HALF_AGREE_HOURS_DEFAULT,
    recurrence_shape_min_span_days=C.RECURRENCE_SHAPE_MIN_SPAN_DAYS_DEFAULT,
    recurrence_daily_density_min=C.RECURRENCE_DAILY_DENSITY_MIN_DEFAULT,
    recurrence_intermittent_r_min=C.RECURRENCE_INTERMITTENT_R_MIN_DEFAULT,
    recurrence_weekend_tolerance=C.RECURRENCE_WEEKEND_TOLERANCE_DEFAULT,
)

AS_OF = date(2026, 9, 10)
WINDOW_DAYS = 56
RECURRENCE_DAYS = 28
# Trajectory generators run past the largest swept recurrence window so a
# window sweep never reads a series shorter than itself.
RECURRENCE_GEN_DAYS = 42
START = AS_OF - timedelta(days=WINDOW_DAYS - 1)
RECURRENCE_START = AS_OF - timedelta(days=RECURRENCE_GEN_DAYS - 1)
RHYTHM_HORIZONS: tuple[int, ...] = (14, 21, 28, 42, 56)
RECURRENCE_HORIZONS: tuple[int, ...] = (14, 21, 28, 35, 42)

RHYTHM_GRID: tuple[tuple[float, float], ...] = tuple(
    (capture, selectivity)
    for capture in (0.6, 0.5, 0.4, 0.3)
    for selectivity in (1.9, 1.6, 1.3, 1.1)
)
R_GRID: tuple[float, ...] = (0.8, 0.7, 0.6, 0.5, 0.4)

# Named coherent threshold sets for the trajectory sweep. The presence bar a
# candidate really faces is max(presence_min, Wilson^-1(wilson_floor, n_eff))
# — lowering presence_min without wilson_floor changes NOTHING (the Wilson
# side binds at ~0.572 for weekday n_eff ~25.4), so the axes move TOGETHER.
# capture stays 0.6 everywhere (the published anchor: 0 % FP grid-wide).
RHYTHM_SETS: tuple[tuple[str, dict[str, float]], ...] = (
    # The shipped defaults (recalibrated 2026-09-11: selectivity 1.9 -> 1.6,
    # +12.6 pts detection on noisy habitual users for ~1 % weekend FP).
    ("current", {"presence": 0.55, "wilson": 0.35, "sparse": 0.30, "half": 0.45, "sel": 1.6}),
    # The 2026-08-19 calibration, kept as the historical reference row.
    ("aug26", {"presence": 0.55, "wilson": 0.35, "sparse": 0.30, "half": 0.45, "sel": 1.9}),
    # Counter-examples, kept so the tables SHOW the cost (measured at 300
    # trials: 8-37 % permanent claims on the structureless dense user, while
    # the targeted 3-evenings/week user only reaches 34-74 % — the absolute
    # presence gates cannot serve rare-but-targeted without manufacturing
    # windows; that user is served by the RECURRENCE detector instead).
    ("relaxed_a", {"presence": 0.45, "wilson": 0.22, "sparse": 0.20, "half": 0.35, "sel": 1.6}),
    ("relaxed_b", {"presence": 0.40, "wilson": 0.18, "sparse": 0.15, "half": 0.30, "sel": 1.6}),
    ("relaxed_c", {"presence": 0.35, "wilson": 0.15, "sparse": 0.12, "half": 0.25, "sel": 1.6}),
)

# Named lock sets. R stays 0.8/0.7 everywhere: the R grid already measured
# the cost of lowering it (2.7-52 % false locks) and nothing here re-opens
# that. What moves is the VOLUME side (occurrences, shape labeling days,
# weekly slots) and the window itself: 28 d holds exactly 4 weekly slots, so
# the current weekly lock demands a 4/4 perfect month.
LOCK_SETS: tuple[tuple[str, dict[str, float]], ...] = (
    # The shipped defaults (recalibrated 2026-09-11): a 35-day window holds
    # five weekly slots (one missed week keeps the lock — at 28 d the weekly
    # lock demanded a 4/4 perfect month and DIED on the missed week: 71 % at
    # d28 falling to 64 % at d42), 6 occurrences + 10-day SPAN labeling make
    # a daily habit recognisable at d14 (87 %) and a 3x/week steady hour
    # lockable at all — labeled ``intermittent``, never "daily".
    ("current", {"min_occ": 6, "shape_days": 10, "wk_dow": 4, "wk_frac": 0.75, "window": 35}),
    # August's THRESHOLDS on today's code — the labeling semantics (calendar
    # span, density, the intermittent R bar) are current, so this row is NOT
    # a replay of the pre-change world; the true pre-change numbers (ritual
    # 64 %, 3x/week 31 % — labeled "daily", daily-at-d14 4 %) are recorded in
    # the ADR-214 amendment of 2026-09-11 (b).
    ("aug26", {"min_occ": 8, "shape_days": 14, "wk_dow": 4, "wk_frac": 0.75, "window": 28}),
    # Counter-examples, kept so the tables SHOW the cost: relaxing the weekly
    # slots (3/0.60) bought NOTHING on the reliable ritual (existence already
    # demands 4 distinct days) and put lucky weekly locks on the sparse
    # control; the floor set leaks up to 3.3 % false locks.
    ("wk_relaxed", {"min_occ": 6, "shape_days": 10, "wk_dow": 3, "wk_frac": 0.60, "window": 35}),
    ("floor", {"min_occ": 5, "shape_days": 8, "wk_dow": 3, "wk_frac": 0.60, "window": 35}),
)

#: Lock sets measured CLEAN on every FP population (20 seeded CI trials; the
#: 300-trial tables carry the exact residuals). wk_relaxed/floor stay in the
#: sweep as measured counter-examples.
LOCK_SETS_FP_CLEAN: tuple[str, ...] = ("current", "aug26")

DayHistograms = dict[date, dict[int, int]]
DayHours = dict[date, list[float]]


# --------------------------------------------------------------------------
# Synthetic populations (seeded — every run reproduces the same numbers)
# --------------------------------------------------------------------------
def _days_range(n: int) -> list[date]:
    return [AS_OF - timedelta(days=k) for k in range(n)]


def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < limit:
            return k
        k += 1


def gen_uniform(rng: random.Random) -> DayHistograms:
    """No time structure: active most days, hours uniform over waking hours."""
    days: DayHistograms = {}
    for d in _days_range(WINDOW_DAYS):
        if rng.random() < 0.9:
            hist: dict[int, int] = {}
            for _ in range(1 + _poisson(rng, 3.0)):
                h = rng.randrange(7, 23)
                hist[h] = hist.get(h, 0) + 1
            days[d] = hist
    return days


def gen_night_spread(rng: random.Random) -> DayHistograms:
    """A night owl: present almost daily, 30 % of events between 0h and 7h."""
    days: DayHistograms = {}
    for d in _days_range(WINDOW_DAYS):
        if rng.random() < 0.94:
            hist: dict[int, int] = {}
            for _ in range(1 + _poisson(rng, 6.0)):
                h = rng.randrange(0, 7) if rng.random() < 0.3 else rng.randrange(7, 24)
                hist[h] = hist.get(h, 0) + 1
            days[d] = hist
    return days


def gen_habitual(rng: random.Random, noise: float) -> DayHistograms:
    """Weekday mornings 8-10h and evenings 21-23h, weekend mornings 10-12h."""
    days: DayHistograms = {}
    for d in _days_range(WINDOW_DAYS):
        weekday = d.weekday() < 5
        if rng.random() >= (0.85 if weekday else 0.7):
            continue
        slots = [8, 9, 21, 22] if weekday else [10, 11]
        hist: dict[int, int] = {}
        for base in slots:
            h = rng.randrange(0, 24) if rng.random() < noise else base
            hist[h] = hist.get(h, 0) + 1
        days[d] = hist
    return days


def gen_moderate_focused(rng: random.Random, days_per_week: float) -> DayHistograms:
    """A light but TARGETED user: a few sessions a week, almost always 20-22h.

    Day presence is Bernoulli-uniform over the whole week — the WORST case
    for the detector (no preferred weekday concentrates the presence), so
    the measured detection is a lower bound. 10 % of events stray.
    """
    days: DayHistograms = {}
    for offset in range(WINDOW_DAYS):
        d = START + timedelta(days=offset)
        if rng.random() >= days_per_week / 7.0:
            continue
        hist: dict[int, int] = {}
        for base in (20, 21):
            if rng.random() < 0.75:
                h = rng.randrange(7, 23) if rng.random() < 0.10 else base
                hist[h] = hist.get(h, 0) + 1
        if hist:
            days[d] = hist
    return days


def gen_moderate_scattered(rng: random.Random, days_per_week: float) -> DayHistograms:
    """The SAME light volume with uniform hours — the moderate FP control.

    Any threshold set that claims windows for this population manufactures
    a habit out of sampling luck at exactly the volume the relaxation aims
    to serve.
    """
    days: DayHistograms = {}
    for offset in range(WINDOW_DAYS):
        d = START + timedelta(days=offset)
        if rng.random() >= days_per_week / 7.0:
            continue
        hist: dict[int, int] = {}
        for _ in range(1 + (1 if rng.random() < 0.5 else 0)):
            h = rng.randrange(7, 23)
            hist[h] = hist.get(h, 0) + 1
        days[d] = hist
    return days


def gen_daily_recurrence(rng: random.Random, sigma: float) -> DayHours:
    """A request every day (80 %) around 9h with Gaussian jitter."""
    days: DayHours = {}
    for d in _days_range(RECURRENCE_DAYS):
        if rng.random() < 0.8:
            n = 2 if rng.random() < 0.3 else 1
            days[d] = [min(23.9, max(0.0, rng.gauss(9.0, sigma))) for _ in range(n)]
    return days


def gen_random_recurrence(rng: random.Random) -> DayHours:
    """The same domain asked often, at no particular hour."""
    days: DayHours = {}
    for d in _days_range(RECURRENCE_DAYS):
        if rng.random() < 0.6:
            n = 2 if rng.random() < 0.3 else 1
            days[d] = [rng.uniform(8.0, 22.0) for _ in range(n)]
    return days


# Trajectory-sweep recurrence generators run over RECURRENCE_GEN_DAYS and
# ascend from RECURRENCE_START. The four generators above keep their exact
# iteration order and span: the anchor tests pin their published numbers,
# and changing the draw order would silently remeasure them.
def gen_daily_long(rng: random.Random, sigma: float) -> DayHours:
    """``gen_daily_recurrence`` over the trajectory span (dense anchor)."""
    days: DayHours = {}
    for offset in range(RECURRENCE_GEN_DAYS):
        d = RECURRENCE_START + timedelta(days=offset)
        if rng.random() < 0.8:
            n = 2 if rng.random() < 0.3 else 1
            days[d] = [min(23.9, max(0.0, rng.gauss(9.0, sigma))) for _ in range(n)]
    return days


def gen_random_long(rng: random.Random) -> DayHours:
    """``gen_random_recurrence`` over the trajectory span (dense FP control)."""
    days: DayHours = {}
    for offset in range(RECURRENCE_GEN_DAYS):
        d = RECURRENCE_START + timedelta(days=offset)
        if rng.random() < 0.6:
            n = 2 if rng.random() < 0.3 else 1
            days[d] = [rng.uniform(8.0, 22.0) for _ in range(n)]
    return days


def gen_weekly_ritual(rng: random.Random, reliability: float, sigma: float) -> DayHours:
    """Once a week, same weekday, around 19h — misses a week now and then."""
    days: DayHours = {}
    for offset in range(RECURRENCE_GEN_DAYS):
        d = RECURRENCE_START + timedelta(days=offset)
        if d.weekday() == 6 and rng.random() < reliability:
            days[d] = [min(23.9, max(0.0, rng.gauss(19.0, sigma)))]
    return days


def gen_few_weekly(rng: random.Random, per_week: float, sigma: float) -> DayHours:
    """A few times a week at a steady hour, on no particular weekday.

    The owner's "rare but targeted" shape: too few distinct days for the
    current time lock, no modal weekday for the weekly lock.
    """
    days: DayHours = {}
    for offset in range(RECURRENCE_GEN_DAYS):
        d = RECURRENCE_START + timedelta(days=offset)
        if rng.random() < per_week / 7.0:
            days[d] = [min(23.9, max(0.0, rng.gauss(9.0, sigma)))]
    return days


def gen_workdays_recurrence(rng: random.Random, presence: float, sigma: float) -> DayHours:
    """A Mon-Fri request around 9h — the workdays-label regression control."""
    days: DayHours = {}
    for offset in range(RECURRENCE_GEN_DAYS):
        d = RECURRENCE_START + timedelta(days=offset)
        if d.weekday() < 5 and rng.random() < presence:
            days[d] = [min(23.9, max(0.0, rng.gauss(9.0, sigma)))]
    return days


def gen_sparse_random(rng: random.Random, per_week: float) -> DayHours:
    """A light user with no hour structure — the moderate false-LOCK control.

    Few points make lucky concentration MORE likely (E[R] ~ 1/sqrt(n)), so
    the false-lock rate of a relaxed volume bar is measured here, never on
    the dense control alone.
    """
    days: DayHours = {}
    for offset in range(RECURRENCE_GEN_DAYS):
        d = RECURRENCE_START + timedelta(days=offset)
        if rng.random() < per_week / 7.0:
            days[d] = [rng.uniform(8.0, 22.0)]
    return days


# --------------------------------------------------------------------------
# Measurements
# --------------------------------------------------------------------------
def _thresholds(capture: float, selectivity: float) -> RhythmThresholds:
    base = RhythmThresholds.from_settings(SHIPPED_RHYTHM)
    return dataclasses.replace(
        base,
        capture_min=capture,
        selectivity_min=selectivity,
        # Hysteresis exits must stay below their entry — the invariant the
        # config holds (0.5/1.6 under 0.6/1.9).
        exit_capture=min(base.exit_capture, capture * 0.85),
        exit_selectivity=min(base.exit_selectivity, selectivity * 0.85),
    )


def _set_thresholds(spec: dict[str, float]) -> RhythmThresholds:
    """Thresholds for one named rhythm set (capture stays at the shipped value)."""
    base = RhythmThresholds.from_settings(SHIPPED_RHYTHM)
    return dataclasses.replace(
        base,
        presence_min=spec["presence"],
        wilson_floor=spec["wilson"],
        sparse_active_days_min=spec["sparse"],
        half_presence_min=spec["half"],
        selectivity_min=spec["sel"],
        recent_min=min(base.recent_min, spec["presence"] - 0.10),
        exit_presence=max(0.0, spec["presence"] - 0.10),
        exit_capture=min(base.exit_capture, base.capture_min * 0.85),
        exit_selectivity=min(base.exit_selectivity, spec["sel"] * 0.85),
    )


def _claims(days: DayHistograms, th: RhythmThresholds) -> bool:
    profile = compute_rhythm_profile(days, AS_OF, th, first_observed=min(days) if days else None)
    return profile.weekday.verdict == "windows"


def _claims_any(days: DayHistograms, as_of: date, th: RhythmThresholds) -> bool:
    """Either day class claims windows at ``as_of`` (trajectory probe)."""
    if not days:
        return False
    profile = compute_rhythm_profile(days, as_of, th, first_observed=min(days))
    return "windows" in (profile.weekday.verdict, profile.weekend.verdict)


def measure_rhythm(trials: int, real: DayHistograms | None) -> list[dict[str, Any]]:
    populations = (
        ("uniform", lambda r: gen_uniform(r)),
        ("night_spread", lambda r: gen_night_spread(r)),
        ("habitual_15", lambda r: gen_habitual(r, 0.15)),
        ("habitual_35", lambda r: gen_habitual(r, 0.35)),
    )
    rows: list[dict[str, Any]] = []
    for capture, selectivity in RHYTHM_GRID:
        th = _thresholds(capture, selectivity)
        row: dict[str, Any] = {"capture_min": capture, "selectivity_min": selectivity}
        for name, gen in populations:
            hits = sum(1 for i in range(trials) if _claims(gen(random.Random(1000 * i + 7)), th))
            row[name] = hits / trials
        if real is not None:
            profile = compute_rhythm_profile(real, AS_OF, th, first_observed=min(real))
            labels = ",".join(w.label() for w in profile.weekday.windows)
            row["real_weekday"] = profile.weekday.verdict + (f" {labels}" if labels else "")
        rows.append(row)
    return rows


RHYTHM_TRAJECTORY_POPULATIONS: tuple[tuple[str, Any], ...] = (
    ("uniform", lambda r: gen_uniform(r)),
    ("night_spread", lambda r: gen_night_spread(r)),
    ("scattered_3pw", lambda r: gen_moderate_scattered(r, 3.0)),
    ("scattered_2pw", lambda r: gen_moderate_scattered(r, 2.0)),
    ("habitual_15", lambda r: gen_habitual(r, 0.15)),
    ("focused_3pw", lambda r: gen_moderate_focused(r, 3.0)),
    ("focused_2pw", lambda r: gen_moderate_focused(r, 2.0)),
)

#: Trajectory populations that carry NO claimable time structure — every
#: claim on them is a false positive (read by the anchor tests too).
RHYTHM_FP_POPULATIONS: frozenset[str] = frozenset(
    {"uniform", "night_spread", "scattered_3pw", "scattered_2pw"}
)

#: Rhythm sets measured CLEAN on every FP population (20 seeded CI trials;
#: the 300-trial tables carry the exact residuals). The relaxed_* sets are
#: deliberately NOT here — measured at 300 trials they claim windows on the
#: structureless populations (relaxed_a: 8-17 % on the dense uniform user;
#: a 20-trial run had blanked it by luck, P~19 %) — and the harness keeps
#: them in the sweep precisely so the tables show that cost.
RHYTHM_SETS_FP_CLEAN: tuple[str, ...] = ("current", "aug26")


def measure_rhythm_sets(trials: int, real: DayHistograms | None) -> list[dict[str, Any]]:
    """Claim rate per named set x population at each horizon."""
    series: dict[str, list[DayHistograms]] = {
        name: [gen(random.Random(1000 * i + 7)) for i in range(trials)]
        for name, gen in RHYTHM_TRAJECTORY_POPULATIONS
    }
    rows: list[dict[str, Any]] = []
    for set_name, spec in RHYTHM_SETS:
        th = _set_thresholds(spec)
        for pop_name, _gen in RHYTHM_TRAJECTORY_POPULATIONS:
            row: dict[str, Any] = {"set": set_name, "population": pop_name}
            for horizon in RHYTHM_HORIZONS:
                as_of_h = START + timedelta(days=horizon - 1)
                hits = sum(
                    1
                    for full in series[pop_name]
                    if _claims_any({d: h for d, h in full.items() if d <= as_of_h}, as_of_h, th)
                )
                row[f"d{horizon}"] = hits / trials
            rows.append(row)
        if real is not None:
            profile = compute_rhythm_profile(real, AS_OF, th, first_observed=min(real))
            labels = ",".join(w.label() for w in profile.weekday.windows)
            rows.append(
                {
                    "set": set_name,
                    "population": "real",
                    "real_weekday": profile.weekday.verdict + (f" {labels}" if labels else ""),
                }
            )
    return rows


def _recurrence_settings(r_min: float) -> SimpleNamespace:
    """The shipped lock settings with the main R bar swept.

    The split-half bar tracks the main bar the way the defaults do (0.7 under
    0.8): a lowered R with an unchanged half bar would silently keep the old
    strictness.
    """
    stg = SimpleNamespace(**vars(SHIPPED_RECURRENCE))
    stg.recurrence_lock_r_min = r_min
    stg.recurrence_lock_half_r_min = max(0.0, r_min - 0.1)
    return stg


def _lock_set_settings(spec: dict[str, float]) -> SimpleNamespace:
    """Settings view for one named lock set (R stays at the proven 0.8/0.7)."""
    base = _recurrence_settings(SHIPPED_RECURRENCE.recurrence_lock_r_min)
    base.recurrence_window_days = int(spec["window"])
    base.recurrence_lock_min_occurrences = int(spec["min_occ"])
    base.recurrence_shape_min_span_days = int(spec["shape_days"])
    base.recurrence_weekly_min_same_dow = int(spec["wk_dow"])
    base.recurrence_weekly_dow_fraction = spec["wk_frac"]
    return base


def _format_lock(sig: str, lock: Any) -> str:
    hour = f"{lock.trigger_hour:.1f}h" if lock.trigger_hour is not None else "no-hour"
    return f"{sig}:{lock.shape}@{hour}"


def measure_recurrence(trials: int, real: dict[str, DayHours] | None) -> list[dict[str, Any]]:
    populations = (
        ("random_hours", lambda r: gen_random_recurrence(r)),
        ("daily_s0.5", lambda r: gen_daily_recurrence(r, 0.5)),
        ("daily_s1.5", lambda r: gen_daily_recurrence(r, 1.5)),
        ("daily_s3.0", lambda r: gen_daily_recurrence(r, 3.0)),
    )
    rows: list[dict[str, Any]] = []
    for r_min in R_GRID:
        stg = _recurrence_settings(r_min)
        row: dict[str, Any] = {"r_min": r_min}
        for name, gen in populations:
            hits = sum(
                1
                for i in range(trials)
                if evaluate_locks(gen(random.Random(5000 * i + 11)), AS_OF, stg) is not None
            )
            row[name] = hits / trials
        if real is not None:
            locked = [
                _format_lock(sig, lock)
                for sig, days in real.items()
                if (lock := evaluate_locks(days, AS_OF, stg)) is not None
            ]
            row["real_locks"] = ", ".join(locked) or "-"
        rows.append(row)
    return rows


RECURRENCE_TRAJECTORY_POPULATIONS: tuple[tuple[str, Any], ...] = (
    ("random_hours", lambda r: gen_random_long(r)),
    ("sparse_random_2pw", lambda r: gen_sparse_random(r, 2.0)),
    ("daily_s1.5", lambda r: gen_daily_long(r, 1.5)),
    ("workdays_85", lambda r: gen_workdays_recurrence(r, 0.85, 0.75)),
    ("few_weekly_3pw", lambda r: gen_few_weekly(r, 3.0, 0.75)),
    ("weekly_ritual", lambda r: gen_weekly_ritual(r, 0.9, 0.75)),
)

#: Trajectory populations with NO hour/weekday structure — every lock on
#: them is a false lock (read by the anchor tests too).
RECURRENCE_FP_POPULATIONS: frozenset[str] = frozenset({"random_hours", "sparse_random_2pw"})


def measure_recurrence_sets(trials: int, real: dict[str, DayHours] | None) -> list[dict[str, Any]]:
    """Lock rate per named set x population at each horizon + final shapes.

    The shape census at the final horizon is decision data, not decoration:
    a set that detects ``few_weekly`` by labeling it ``daily`` would put a
    false promise in the suggestion text.
    """
    series: dict[str, list[DayHours]] = {
        name: [gen(random.Random(5000 * i + 11)) for i in range(trials)]
        for name, gen in RECURRENCE_TRAJECTORY_POPULATIONS
    }
    rows: list[dict[str, Any]] = []
    for set_name, spec in LOCK_SETS:
        stg = _lock_set_settings(spec)
        for pop_name, _gen in RECURRENCE_TRAJECTORY_POPULATIONS:
            row: dict[str, Any] = {"set": set_name, "population": pop_name}
            shapes: dict[str, int] = {}
            for horizon in RECURRENCE_HORIZONS:
                as_of_h = RECURRENCE_START + timedelta(days=horizon - 1)
                hits = 0
                for full in series[pop_name]:
                    trunc = {d: h for d, h in full.items() if d <= as_of_h}
                    lock = evaluate_locks(trunc, as_of_h, stg)
                    if lock is not None:
                        hits += 1
                        if horizon == RECURRENCE_HORIZONS[-1]:
                            shapes[lock.shape] = shapes.get(lock.shape, 0) + 1
                row[f"d{horizon}"] = hits / trials
            row["shapes"] = shapes
            rows.append(row)
        if real is not None:
            locked = [
                _format_lock(sig, lock)
                for sig, days in real.items()
                if (lock := evaluate_locks(days, AS_OF, stg)) is not None
            ]
            rows.append(
                {"set": set_name, "population": "real", "real_locks": ", ".join(locked) or "-"}
            )
    return rows


def _load_real(path: str) -> tuple[DayHistograms, dict[str, DayHours]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rhythm = {
        date.fromisoformat(d): {int(h): int(n) for h, n in hs.items()}
        for d, hs in data["rhythm"].items()
    }
    recurrence = {
        sig: {date.fromisoformat(d): [float(h) for h in hs] for d, hs in days.items()}
        for sig, days in data["recurrence"].items()
    }
    return rhythm, recurrence


def _print_rhythm_grid(rows: list[dict[str, Any]], trials: int) -> None:
    print(
        f"RHYTHM — {trials} trials/population, window {WINDOW_DAYS} d, shipped = "
        f"{SHIPPED_RHYTHM.habits_capture_min} / {SHIPPED_RHYTHM.habits_selectivity_min}"
    )
    print(
        f"{'capture':>8} {'select.':>8} | {'FP uniform':>10} {'FP night':>9} "
        f"| {'DET 15%':>8} {'DET 35%':>8} | real"
    )
    for r in rows:
        print(
            f"{r['capture_min']:>8} {r['selectivity_min']:>8} | {r['uniform']:>10.1%} "
            f"{r['night_spread']:>9.1%} | {r['habitual_15']:>8.1%} {r['habitual_35']:>8.1%} "
            f"| {r.get('real_weekday', '')}"
        )


def _print_recurrence_grid(rows: list[dict[str, Any]], trials: int) -> None:
    print(
        f"RECURRENCE — {trials} trials/population, {RECURRENCE_DAYS} d generated, "
        f"window {SHIPPED_RECURRENCE.recurrence_window_days} d, shipped R = "
        f"{SHIPPED_RECURRENCE.recurrence_lock_r_min}"
    )
    print(
        f"{'R min':>6} | {'FP random':>9} | {'DET s0.5':>8} {'DET s1.5':>8} {'DET s3.0':>8} "
        "| real locks"
    )
    for r in rows:
        print(
            f"{r['r_min']:>6} | {r['random_hours']:>9.1%} | {r['daily_s0.5']:>8.1%} "
            f"{r['daily_s1.5']:>8.1%} {r['daily_s3.0']:>8.1%} | {r.get('real_locks', '')}"
        )


def _print_trajectories(title: str, rows: list[dict[str, Any]], horizons: tuple[int, ...]) -> None:
    print(title)
    header = " ".join(f"{'d' + str(h):>6}" for h in horizons)
    print(f"{'set':>10} {'population':>17} | {header} | notes")
    for r in rows:
        if "real_weekday" in r or "real_locks" in r:
            note = r.get("real_weekday") or r.get("real_locks") or ""
            print(f"{r['set']:>10} {r['population']:>17} | {'':>{7 * len(horizons)}}| {note}")
            continue
        cells = " ".join(f"{r[f'd{h}']:>6.1%}" for h in horizons)
        shapes = r.get("shapes") or {}
        note = " ".join(f"{k}:{v}" for k, v in sorted(shapes.items()))
        print(f"{r['set']:>10} {r['population']:>17} | {cells} | {note}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the habit detectors' calibration.")
    parser.add_argument("--trials", type=int, default=100, help="trials per population")
    parser.add_argument("--real", type=str, default=None, help="exported real series (JSON)")
    parser.add_argument("--json", type=str, default=None, help="write the tables as JSON")
    parser.add_argument(
        "--only",
        choices=("all", "rhythm", "recurrence"),
        default="all",
        help="measure one detector only (the rhythm sweep dominates runtime)",
    )
    args = parser.parse_args()

    real_rhythm = real_recurrence = None
    if args.real:
        real_rhythm, real_recurrence = _load_real(args.real)

    rhythm_rows: list[dict[str, Any]] = []
    rhythm_set_rows: list[dict[str, Any]] = []
    recurrence_rows: list[dict[str, Any]] = []
    recurrence_set_rows: list[dict[str, Any]] = []
    if args.only in ("all", "rhythm"):
        rhythm_rows = measure_rhythm(args.trials, real_rhythm)
        _print_rhythm_grid(rhythm_rows, args.trials)
        print(flush=True)
    if args.only in ("all", "recurrence"):
        recurrence_rows = measure_recurrence(args.trials, real_recurrence)
        _print_recurrence_grid(recurrence_rows, args.trials)
        print(flush=True)
    if args.only in ("all", "rhythm"):
        rhythm_set_rows = measure_rhythm_sets(args.trials, real_rhythm)
        _print_trajectories(
            f"RHYTHM SETS — claim rate by horizon (days since first activity), "
            f"{args.trials} trials",
            rhythm_set_rows,
            RHYTHM_HORIZONS,
        )
        print(flush=True)
    if args.only in ("all", "recurrence"):
        recurrence_set_rows = measure_recurrence_sets(args.trials, real_recurrence)
        _print_trajectories(
            f"RECURRENCE SETS — lock rate by horizon + shapes at d{RECURRENCE_HORIZONS[-1]}, "
            f"{args.trials} trials",
            recurrence_set_rows,
            RECURRENCE_HORIZONS,
        )

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "rhythm": rhythm_rows,
                    "recurrence": recurrence_rows,
                    "rhythm_sets": rhythm_set_rows,
                    "recurrence_sets": recurrence_set_rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
