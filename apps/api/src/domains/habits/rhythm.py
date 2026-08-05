"""Pure rhythm detector — day-presence statistics over local activity (ADR-214).

Ported from the calibrated simulation harness of the habits program plan
(``docs/plans/2026-08-05-habitudes-utilisateur-programme.md`` §4.1). The
statistical unit is the DAY, never the message: per-message counting is
corrupted by within-day bursts (measured false-positive source). A window is
claimed only when presence, a Wilson lower bound, split-half consistency,
recency AND the selectivity gate all hold — and a previously claimed window
is retained under relaxed exit thresholds (hysteresis, anti-flapping).

Everything in this module is pure and I/O-free: inputs are per-local-day
hour histograms, thresholds come in as a frozen dataclass built from
settings, outputs are frozen dataclasses with a round-trip-tested payload
serialization. The service layer owns sessions, SQL and persistence.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from src.domains.habits.models import ProfileVerdict

# Candidate window lengths, in hours. 2-4h windows match how humans describe
# their own routines ("my mornings", "after dinner"); longer claims are the
# diffuse verdict's territory.
WINDOW_LENGTHS: tuple[int, ...] = (2, 3, 4)

# Wilson 99% one-sided z.
_Z99 = 2.326

# A class whose high-presence hours cover at least this fraction of the
# waking-day reference is "active all day": window claims would carry no
# information — the DIFFUSE verdict is decided BEFORE any window scan.
_DIFFUSE_BIN_FRACTION = 0.6

# Payload schema version (bump on shape change; readers must tolerate older).
PROFILE_PAYLOAD_VERSION = 1

WEEKDAY = "weekday"
WEEKEND = "weekend"
DAY_CLASSES: tuple[str, ...] = (WEEKDAY, WEEKEND)


@dataclass(frozen=True, slots=True)
class RhythmThresholds:
    """Detector thresholds — one immutable bundle, built from settings.

    Attributes mirror ``HabitsSettings`` field for field; see
    ``core/config/habits.py`` for semantics and calibration provenance.
    """

    window_days: int
    half_life_days: float
    presence_min: float
    wilson_floor: float
    half_presence_min: float
    capture_min: float
    selectivity_min: float
    exit_presence: float
    exit_capture: float
    exit_selectivity: float
    min_neff_weekday: float
    min_neff_weekend: float
    recent_days: int
    recent_min: float
    max_claimed_hours: int
    waking_hours: float
    sparse_active_days_min: float

    @classmethod
    def from_settings(cls, settings: Any) -> RhythmThresholds:
        """Build the bundle from the composed application settings.

        Args:
            settings: Any object exposing the ``habits_*`` fields.

        Returns:
            Frozen thresholds bundle.
        """
        return cls(
            window_days=settings.habits_window_days,
            half_life_days=settings.habits_half_life_days,
            presence_min=settings.habits_presence_min,
            wilson_floor=settings.habits_wilson_floor,
            half_presence_min=settings.habits_half_presence_min,
            capture_min=settings.habits_capture_min,
            selectivity_min=settings.habits_selectivity_min,
            exit_presence=settings.habits_exit_presence,
            exit_capture=settings.habits_exit_capture,
            exit_selectivity=settings.habits_exit_selectivity,
            min_neff_weekday=settings.habits_min_neff_weekday,
            min_neff_weekend=settings.habits_min_neff_weekend,
            recent_days=settings.habits_recent_days,
            recent_min=settings.habits_recent_min,
            max_claimed_hours=settings.habits_max_claimed_hours,
            waking_hours=settings.habits_waking_hours,
            sparse_active_days_min=settings.habits_sparse_active_days_min,
        )


@dataclass(frozen=True, slots=True)
class ClaimedWindow:
    """One claimed active window within a day class.

    Attributes:
        start_hour: First hour of the window (0-23).
        end_hour: Exclusive end hour (may wrap past midnight).
        presence: Weighted fraction of class days with activity inside.
    """

    start_hour: int
    end_hour: int
    presence: float

    def label(self) -> str:
        """Human window label, e.g. ``"08:00-10:00"`` (single authority —
        the heartbeat block and the ambient block both render through it)."""
        return f"{self.start_hour:02d}:00-{self.end_hour:02d}:00"


@dataclass(frozen=True, slots=True)
class ClassRhythm:
    """Detector output for one day class.

    Attributes:
        verdict: ``ProfileVerdict`` value.
        windows: Claimed windows (empty unless verdict is WINDOWS).
        n_eff: Kish effective number of observed class days.
        bin_presence: Weighted per-hour day-presence, 24 values — the
            distribution-level profile that stays available even when no
            window is claimable (low-volume honesty).
    """

    verdict: str
    windows: tuple[ClaimedWindow, ...]
    n_eff: float
    bin_presence: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RhythmProfile:
    """Full per-user rhythm profile.

    Attributes:
        weekday: Weekday-class result.
        weekend: Weekend-class result.
        active_days_fraction: Weighted fraction of observed days with ANY
            activity (the sparse discriminator).
        sparse: True when the user is too occasional for window claims —
            claims would be factually false; recurrences remain detectable.
    """

    weekday: ClassRhythm
    weekend: ClassRhythm
    active_days_fraction: float
    sparse: bool

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the versioned JSONB payload (round-trip tested)."""
        return {
            "version": PROFILE_PAYLOAD_VERSION,
            "active_days_fraction": self.active_days_fraction,
            "sparse": self.sparse,
            "classes": {
                name: {
                    "verdict": rhythm.verdict,
                    "windows": [
                        {
                            "start_hour": w.start_hour,
                            "end_hour": w.end_hour,
                            "presence": w.presence,
                        }
                        for w in rhythm.windows
                    ],
                    "n_eff": rhythm.n_eff,
                    "bin_presence": list(rhythm.bin_presence),
                }
                for name, rhythm in ((WEEKDAY, self.weekday), (WEEKEND, self.weekend))
            },
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RhythmProfile:
        """Rebuild from the JSONB payload (tolerant of missing keys).

        Args:
            payload: Stored payload, any version ≤ current.

        Returns:
            Reconstructed profile; unknown/missing classes degrade to an
            INSUFFICIENT empty class rather than raising.
        """

        def _class(name: str) -> ClassRhythm:
            raw = (payload.get("classes") or {}).get(name) or {}
            # Normalize to exactly 24 bins: consumers index bin_presence by
            # hour, and a foreshortened stored list (older payload version)
            # must degrade to zeros, never to an IndexError.
            bins = [float(v) for v in raw.get("bin_presence") or []][:24]
            bins += [0.0] * (24 - len(bins))
            return ClassRhythm(
                verdict=str(raw.get("verdict", ProfileVerdict.INSUFFICIENT.value)),
                windows=tuple(
                    ClaimedWindow(
                        start_hour=int(w["start_hour"]),
                        end_hour=int(w["end_hour"]),
                        presence=float(w["presence"]),
                    )
                    for w in raw.get("windows") or []
                ),
                n_eff=float(raw.get("n_eff", 0.0)),
                bin_presence=tuple(bins),
            )

        return cls(
            weekday=_class(WEEKDAY),
            weekend=_class(WEEKEND),
            active_days_fraction=float(payload.get("active_days_fraction", 0.0)),
            sparse=bool(payload.get("sparse", False)),
        )


def wilson_lower_bound(p_hat: float, n: float, z: float = _Z99) -> float:
    """One-sided Wilson score lower bound for a proportion.

    Args:
        p_hat: Observed proportion.
        n: (Effective) sample size.
        z: Normal quantile (default 99%).

    Returns:
        Lower confidence bound in [0, 1]; 0 when n ≤ 0.
    """
    if n <= 0:
        return 0.0
    denom = 1 + z * z / n
    center = p_hat + z * z / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))
    return max(0.0, (center - margin) / denom)


def kish_effective_n(weights: list[float]) -> float:
    """Kish effective sample size of a weight vector."""
    s1 = sum(weights)
    s2 = sum(w * w for w in weights)
    return (s1 * s1 / s2) if s2 > 0 else 0.0


def _window_bins(start: int, length: int) -> frozenset[int]:
    return frozenset((start + k) % 24 for k in range(length))


def _day_hits(hours: Mapping[int, int], bins: frozenset[int]) -> bool:
    return any(h in bins for h in hours)


@dataclass(frozen=True, slots=True)
class _ClassContext:
    """Precomputed per-class data shared by every candidate evaluation."""

    class_days: list[date]
    day_weight: dict[date, float]
    weight_sum: float
    n_eff: float
    day_hours: dict[date, dict[int, int]]
    day_totals: dict[date, int]
    recent_days: list[date]


def _build_class_context(
    days: Mapping[date, Mapping[int, int]],
    as_of: date,
    day_class: str,
    thresholds: RhythmThresholds,
    window_days: int,
) -> _ClassContext:
    """Assemble weights and per-day lookups for one day class.

    Days with no activity are INCLUDED (absence is data): the denominator is
    every class day inside the window, not just active ones.
    """
    first_day = as_of - timedelta(days=window_days - 1)
    is_weekday = day_class == WEEKDAY
    class_days = [
        first_day + timedelta(days=offset)
        for offset in range(window_days)
        if ((first_day + timedelta(days=offset)).weekday() < 5) == is_weekday
    ]
    day_weight = {d: 0.5 ** ((as_of - d).days / thresholds.half_life_days) for d in class_days}
    day_hours: dict[date, dict[int, int]] = {d: dict(days.get(d, {})) for d in class_days}
    recent_cutoff = as_of - timedelta(days=thresholds.recent_days - 1)
    return _ClassContext(
        class_days=class_days,
        day_weight=day_weight,
        weight_sum=sum(day_weight.values()),
        n_eff=kish_effective_n(list(day_weight.values())),
        day_hours=day_hours,
        day_totals={d: sum(day_hours[d].values()) for d in class_days},
        recent_days=[d for d in class_days if d >= recent_cutoff],
    )


def _weighted_presence(ctx: _ClassContext, bins: frozenset[int], days: list[date]) -> float:
    """Weighted fraction of the given days with ≥1 event inside ``bins``."""
    total = sum(ctx.day_weight[d] for d in days)
    if total <= 0:
        return 0.0
    hit = sum(ctx.day_weight[d] for d in days if _day_hits(ctx.day_hours[d], bins))
    return hit / total


def _candidate_passes(
    ctx: _ClassContext,
    bins: frozenset[int],
    p_hat: float,
    thresholds: RhythmThresholds,
    presence_min: float,
) -> bool:
    """Entry (or exit) gates for one candidate window, selectivity excluded."""
    if p_hat < presence_min:
        return False
    if wilson_lower_bound(p_hat, ctx.n_eff) < thresholds.wilson_floor:
        return False
    if ctx.recent_days:
        recent_hits = sum(1 for d in ctx.recent_days if _day_hits(ctx.day_hours[d], bins))
        if recent_hits / len(ctx.recent_days) < thresholds.recent_min:
            return False
    # Split-half consistency: both interleaved halves of the class days must
    # independently support the window (kills lucky-streak selection noise).
    for half in (ctx.class_days[0::2], ctx.class_days[1::2]):
        if not half:
            return False
        if _weighted_presence(ctx, bins, half) < thresholds.half_presence_min:
            return False
    return True


def _capture_of(ctx: _ClassContext, bins: frozenset[int]) -> float:
    """Weighted mean over days of the fraction of the day's events in bins."""
    num = 0.0
    den = 0.0
    for d in ctx.class_days:
        total = ctx.day_totals[d]
        if not total:
            continue
        inside = sum(n for h, n in ctx.day_hours[d].items() if h in bins)
        num += ctx.day_weight[d] * (inside / total)
        den += ctx.day_weight[d]
    return num / den if den else 0.0


def _detect_class_windows(
    ctx: _ClassContext,
    thresholds: RhythmThresholds,
    presence_min: float,
    capture_min: float,
    selectivity_min: float,
) -> tuple[list[ClaimedWindow], str]:
    """Candidate scan → marginal-capture greedy → selectivity gate."""
    prelim: list[tuple[float, float, int, int]] = []
    for length in WINDOW_LENGTHS:
        for start in range(24):
            bins = _window_bins(start, length)
            p_hat = _weighted_presence(ctx, bins, ctx.class_days)
            if not _candidate_passes(ctx, bins, p_hat, thresholds, presence_min):
                continue
            prelim.append((_capture_of(ctx, bins), p_hat, start, length))

    if not prelim:
        return [], ProfileVerdict.NONE.value

    chosen, used, total_hours = _greedy_select(prelim, ctx, thresholds)
    if not chosen:
        return [], ProfileVerdict.NONE.value

    capture = _capture_of(ctx, frozenset(used))
    share = total_hours / thresholds.waking_hours
    if share <= 0 or capture < capture_min or capture / share < selectivity_min:
        # Nothing stood out enough to be informative — the claim is withheld.
        return [], ProfileVerdict.NONE.value

    chosen.sort(key=lambda w: w.start_hour)
    return chosen, ProfileVerdict.WINDOWS.value


def _best_marginal_candidate(
    remaining: list[tuple[float, float, int, int]],
    ctx: _ClassContext,
    used: set[int],
    total_hours: int,
    max_hours: int,
) -> tuple[float, int, int] | None:
    """The next window to claim, by MARGINAL capture.

    Selection key: marginal capture first, then the SHORTEST window (the
    tightest honest claim — an equal-capture longer window merely sprawls
    around the same activity), then presence, then earliest start for
    determinism.
    """
    best: tuple[float, int, int] | None = None
    best_key: tuple[float, int, float, int] | None = None
    for _cap, p_hat, start, length in remaining:
        bins = _window_bins(start, length)
        if bins & used or total_hours + length > max_hours:
            continue
        gain = _capture_of(ctx, frozenset(b for b in bins if b not in used))
        key = (gain, -length, p_hat, -start)
        if gain > 0 and (best_key is None or key > best_key):
            best_key = key
            best = (p_hat, start, length)
    return best


def _greedy_select(
    prelim: list[tuple[float, float, int, int]],
    ctx: _ClassContext,
    thresholds: RhythmThresholds,
) -> tuple[list[ClaimedWindow], set[int], int]:
    """Greedy non-overlapping selection by marginal capture, capped hours.

    Presence-greedy picks wide windows that evict the second peak under the
    cap and then fail selectivity — measured in the calibration harness.
    """
    chosen: list[ClaimedWindow] = []
    used: set[int] = set()
    total_hours = 0
    remaining = sorted(prelim, reverse=True)
    while remaining:
        best = _best_marginal_candidate(
            remaining, ctx, used, total_hours, thresholds.max_claimed_hours
        )
        if best is None:
            break
        p_hat, start, length = best
        used |= _window_bins(start, length)
        total_hours += length
        chosen.append(
            ClaimedWindow(start_hour=start, end_hour=(start + length) % 24, presence=p_hat)
        )
        remaining = [c for c in remaining if not (_window_bins(c[2], c[3]) & used)]
    return chosen, used, total_hours


def _detect_class(
    days: Mapping[date, Mapping[int, int]],
    as_of: date,
    day_class: str,
    thresholds: RhythmThresholds,
    had_claim: bool,
    window_days: int,
) -> ClassRhythm:
    """Full per-class detection with hysteresis."""
    ctx = _build_class_context(days, as_of, day_class, thresholds, window_days)
    min_neff = thresholds.min_neff_weekday if day_class == WEEKDAY else thresholds.min_neff_weekend
    bin_presence = tuple(_weighted_presence(ctx, frozenset({b}), ctx.class_days) for b in range(24))
    if ctx.n_eff < min_neff:
        return ClassRhythm(
            verdict=ProfileVerdict.INSUFFICIENT.value,
            windows=(),
            n_eff=ctx.n_eff,
            bin_presence=bin_presence,
        )

    # Diffuse pre-check: a user with high day-presence across most of the
    # waking day has no time habit — claiming windows for them would be
    # noise-picking, and the honest answer is itself useful information.
    high_bins = sum(1 for p in bin_presence if p >= thresholds.presence_min)
    if high_bins >= _DIFFUSE_BIN_FRACTION * thresholds.waking_hours:
        return ClassRhythm(
            verdict=ProfileVerdict.DIFFUSE.value,
            windows=(),
            n_eff=ctx.n_eff,
            bin_presence=bin_presence,
        )

    windows, verdict = _detect_class_windows(
        ctx,
        thresholds,
        thresholds.presence_min,
        thresholds.capture_min,
        thresholds.selectivity_min,
    )
    if not windows and had_claim:
        # Hysteresis: a previously claimed rhythm is retained under relaxed
        # exit thresholds — anti-flapping, measured 0.18% claim loss vs 5.5%.
        windows, verdict = _detect_class_windows(
            ctx,
            thresholds,
            thresholds.exit_presence,
            thresholds.exit_capture,
            thresholds.exit_selectivity,
        )
    return ClassRhythm(
        verdict=verdict,
        windows=tuple(windows),
        n_eff=ctx.n_eff,
        bin_presence=bin_presence,
    )


def compute_rhythm_profile(
    days: Mapping[date, Mapping[int, int]],
    as_of: date,
    thresholds: RhythmThresholds,
    previously_claimed: Mapping[str, bool] | None = None,
    first_observed: date | None = None,
) -> RhythmProfile:
    """Compute the full rhythm profile for one user.

    Args:
        days: Per-LOCAL-day hour histograms of HUMAN user messages (automated
            rows excluded upstream). Keys outside the window are ignored;
            missing days count as inactive (absence is data).
        as_of: Last complete local day to consider (the nightly job passes
            "yesterday" in the user's timezone so a partial day never dilutes
            presence).
        thresholds: Detector thresholds (see ``RhythmThresholds``).
        previously_claimed: Per day-class hysteresis input — True when the
            stored profile currently claims windows for that class.
        first_observed: Date of the user's first observed message. Clips the
            observation window so a NEW account reads INSUFFICIENT ("still
            learning") instead of NONE — without it, a 2-week-old account is
            indistinguishable from a long absence. An OLD account keeps the
            full window: its absences are real data.

    Returns:
        The computed profile. When the user is too occasional
        (``active_days_fraction`` under the sparse floor) both classes carry
        the SPARSE verdict and no windows: a "usually active at H" claim
        would be factually false — recurrences remain the honest granularity.
    """
    previously_claimed = previously_claimed or {}

    window_days = thresholds.window_days
    if first_observed is not None and first_observed > as_of - timedelta(days=window_days - 1):
        window_days = max(1, (as_of - first_observed).days + 1)

    # Sparse discriminator across ALL observed days (both classes).
    first_day = as_of - timedelta(days=window_days - 1)
    all_days = [first_day + timedelta(days=k) for k in range(window_days)]
    weights = [0.5 ** ((as_of - d).days / thresholds.half_life_days) for d in all_days]
    wsum = sum(weights)
    active = sum(
        w for d, w in zip(all_days, weights, strict=True) if sum(days.get(d, {}).values()) > 0
    )
    active_fraction = active / wsum if wsum else 0.0

    if active_fraction < thresholds.sparse_active_days_min:
        empty = ClassRhythm(
            verdict=ProfileVerdict.SPARSE.value,
            windows=(),
            n_eff=0.0,
            bin_presence=tuple([0.0] * 24),
        )
        return RhythmProfile(
            weekday=empty,
            weekend=empty,
            active_days_fraction=active_fraction,
            sparse=True,
        )

    return RhythmProfile(
        weekday=_detect_class(
            days,
            as_of,
            WEEKDAY,
            thresholds,
            bool(previously_claimed.get(WEEKDAY)),
            window_days,
        ),
        weekend=_detect_class(
            days,
            as_of,
            WEEKEND,
            thresholds,
            bool(previously_claimed.get(WEEKEND)),
            window_days,
        ),
        active_days_fraction=active_fraction,
        sparse=False,
    )


def hour_in_windows(hour: float, windows: tuple[ClaimedWindow, ...]) -> bool:
    """Whether a local hour falls inside any claimed window (wrap-aware)."""
    for w in windows:
        length = (w.end_hour - w.start_hour) % 24
        if (hour - w.start_hour) % 24 < length:
            return True
    return False
