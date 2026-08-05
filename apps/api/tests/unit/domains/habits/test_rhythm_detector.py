"""Table-driven tests for the pure rhythm detector (ADR-214).

Deterministic hand-built activity patterns pin the behavioral contract the
simulation harness calibrated (habits plan §4.1): claims on stable peaks,
silence on uniform / sparse / diffuse users, hysteresis retention, honest
verdicts, wrap-aware windows and a round-trip-tested payload.

Thresholds are read from ``settings`` (never hardcoded — configs change and
hardcoded thresholds silently drift the assertion).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from src.core.config import settings
from src.domains.habits.models import ProfileVerdict
from src.domains.habits.rhythm import (
    WEEKDAY,
    WEEKEND,
    ClaimedWindow,
    RhythmProfile,
    RhythmThresholds,
    compute_rhythm_profile,
    hour_in_windows,
)

AS_OF = date(2026, 8, 4)  # a Tuesday — fixed so day classes are deterministic

THRESHOLDS = RhythmThresholds.from_settings(settings)


def _all_days(window_days: int | None = None) -> list[date]:
    n = window_days or THRESHOLDS.window_days
    first = AS_OF - timedelta(days=n - 1)
    return [first + timedelta(days=k) for k in range(n)]


def _regular_user() -> dict[date, dict[int, int]]:
    """Two weekday peaks (8-9h, 21-22h) + one weekend peak (10-11h)."""
    days: dict[date, dict[int, int]] = {}
    for d in _all_days():
        if d.weekday() < 5:
            days[d] = {8: 2, 9: 1, 21: 3, 22: 1}
        else:
            days[d] = {10: 3, 11: 1}
    return days


class TestRegularUser:
    def test_weekday_peaks_are_claimed(self) -> None:
        profile = compute_rhythm_profile(_regular_user(), AS_OF, THRESHOLDS)
        assert profile.weekday.verdict == ProfileVerdict.WINDOWS.value
        assert hour_in_windows(8.5, profile.weekday.windows)
        assert hour_in_windows(21.5, profile.weekday.windows)
        # The claim is selective: the afternoon gap is NOT claimed.
        assert not hour_in_windows(15.0, profile.weekday.windows)

    def test_weekend_peak_is_claimed(self) -> None:
        profile = compute_rhythm_profile(_regular_user(), AS_OF, THRESHOLDS)
        assert profile.weekend.verdict == ProfileVerdict.WINDOWS.value
        assert hour_in_windows(10.5, profile.weekend.windows)

    def test_not_sparse_and_fraction_reported(self) -> None:
        profile = compute_rhythm_profile(_regular_user(), AS_OF, THRESHOLDS)
        assert profile.sparse is False
        assert profile.active_days_fraction > 0.9

    def test_deleted_history_leaves_the_profile(self) -> None:
        """Right-to-be-forgotten follows the source: recompute on emptied
        history claims nothing (the profile is derived data)."""
        profile = compute_rhythm_profile({}, AS_OF, THRESHOLDS)
        assert profile.weekday.windows == ()
        assert profile.weekend.windows == ()


class TestNoHabitUsers:
    def test_moderate_uniform_user_claims_nothing(self) -> None:
        """One message at a rotating waking hour: no stable window exists."""
        days: dict[date, dict[int, int]] = {}
        for i, d in enumerate(_all_days()):
            days[d] = {7 + (i * 5) % 17: 1}
        profile = compute_rhythm_profile(days, AS_OF, THRESHOLDS)
        assert profile.weekday.windows == ()
        assert profile.weekend.windows == ()

    def test_chatty_all_day_user_is_diffuse(self) -> None:
        """Messages every waking hour every day → DIFFUSE, not fake windows."""
        days = {d: dict.fromkeys(range(7, 23), 1) for d in _all_days()}
        profile = compute_rhythm_profile(days, AS_OF, THRESHOLDS)
        assert profile.weekday.verdict == ProfileVerdict.DIFFUSE.value
        assert profile.weekday.windows == ()

    def test_random_block_null_aggregate_fp_bound(self) -> None:
        """The adversarial null (a random 3h block each day) stays under the
        measured FP bound: over 20 fixed seeds, at most 4 weekday claims."""
        claims = 0
        for seed in range(20):
            rng = random.Random(1000 + seed)
            days: dict[date, dict[int, int]] = {}
            for d in _all_days():
                start = rng.uniform(7.0, 21.0)
                hist: dict[int, int] = {}
                for _ in range(6):
                    h = int(start + rng.uniform(0.0, 3.0)) % 24
                    hist[h] = hist.get(h, 0) + 1
                days[d] = hist
            profile = compute_rhythm_profile(days, AS_OF, THRESHOLDS)
            if profile.weekday.windows:
                claims += 1
        assert claims <= 4


class TestHonestVerdicts:
    def test_new_account_two_weeks_old_is_insufficient(self) -> None:
        """A 2-week-old ACCOUNT reads 'still learning', never 'no habit':
        first_observed clips the window so absence-before-signup is not
        counted against the user."""
        first = AS_OF - timedelta(days=13)
        days = {d: {8: 2, 21: 3} for d in _all_days() if d >= first and d.weekday() < 5}
        profile = compute_rhythm_profile(days, AS_OF, THRESHOLDS, first_observed=first)
        # 10 observed weekdays → Kish n_eff below the weekday floor.
        assert profile.weekday.verdict == ProfileVerdict.INSUFFICIENT.value
        assert profile.weekday.windows == ()

    def test_old_account_long_absence_is_not_insufficient(self) -> None:
        """Same activity data, OLD account: the 6 absent weeks are real data
        — the verdict must not pretend the observation just started."""
        first = AS_OF - timedelta(days=200)
        days = {
            d: {8: 2, 21: 3}
            for d in _all_days()
            if d >= AS_OF - timedelta(days=13) and d.weekday() < 5
        }
        profile = compute_rhythm_profile(days, AS_OF, THRESHOLDS, first_observed=first)
        assert profile.weekday.verdict != ProfileVerdict.INSUFFICIENT.value
        assert profile.weekday.windows == ()

    def test_occasional_user_is_sparse_not_windowed(self) -> None:
        """Active one day in four: a 'usually active at H' claim would be
        false — the verdict says sparse, recurrences are the honest level."""
        days = {d: {9: 1} for i, d in enumerate(_all_days()) if i % 4 == 0}
        profile = compute_rhythm_profile(days, AS_OF, THRESHOLDS)
        assert profile.sparse is True
        assert profile.weekday.verdict == ProfileVerdict.SPARSE.value
        assert profile.weekday.windows == ()

    def test_distribution_profile_survives_without_claims(self) -> None:
        """bin_presence stays available even when nothing is claimable."""
        days: dict[date, dict[int, int]] = {}
        for i, d in enumerate(_all_days()):
            days[d] = {7 + (i * 5) % 17: 1}
        profile = compute_rhythm_profile(days, AS_OF, THRESHOLDS)
        assert len(profile.weekday.bin_presence) == 24
        assert any(p > 0 for p in profile.weekday.bin_presence)


class TestHysteresis:
    def _borderline_days(self) -> dict[date, dict[int, int]]:
        """Every weekday: 2 morning messages (8h,9h) + 2 scattered ones.

        Capture of the morning window is exactly 0.5 — under the entry
        capture gate, above the exit gate. Scattered hours rotate so no
        other bin accumulates presence. Weekends active so the user is not
        sparse.
        """
        days: dict[date, dict[int, int]] = {}
        scatter = [11, 13, 15, 17, 19, 12, 14, 16, 18, 20]
        for i, d in enumerate(_all_days()):
            if d.weekday() < 5:
                a = scatter[i % len(scatter)]
                b = scatter[(i + 3) % len(scatter)]
                hist = {8: 1, 9: 1}
                hist[a] = hist.get(a, 0) + 1
                hist[b] = hist.get(b, 0) + 1
                days[d] = hist
            else:
                days[d] = {10: 2}
        return days

    def test_borderline_rhythm_not_claimed_fresh(self) -> None:
        profile = compute_rhythm_profile(self._borderline_days(), AS_OF, THRESHOLDS)
        assert profile.weekday.verdict == ProfileVerdict.NONE.value

    def test_borderline_rhythm_retained_when_previously_claimed(self) -> None:
        profile = compute_rhythm_profile(
            self._borderline_days(), AS_OF, THRESHOLDS, previously_claimed={WEEKDAY: True}
        )
        assert profile.weekday.verdict == ProfileVerdict.WINDOWS.value
        assert hour_in_windows(8.5, profile.weekday.windows)

    def test_gone_rhythm_released_even_with_hysteresis(self) -> None:
        """A habit that truly stopped is dropped despite previous claims."""
        days: dict[date, dict[int, int]] = {}
        for i, d in enumerate(_all_days()):
            days[d] = {7 + (i * 5) % 17: 1}  # no stable window at all
        profile = compute_rhythm_profile(
            days, AS_OF, THRESHOLDS, previously_claimed={WEEKDAY: True, WEEKEND: True}
        )
        assert profile.weekday.windows == ()
        assert profile.weekend.windows == ()


class TestWindowGeometry:
    def test_hour_in_windows_wraps_past_midnight(self) -> None:
        windows = (ClaimedWindow(start_hour=22, end_hour=2, presence=0.9),)
        assert hour_in_windows(23.5, windows)
        assert hour_in_windows(1.0, windows)
        assert not hour_in_windows(3.0, windows)

    def test_claimed_hours_capped(self) -> None:
        profile = compute_rhythm_profile(_regular_user(), AS_OF, THRESHOLDS)
        total = sum((w.end_hour - w.start_hour) % 24 for w in profile.weekday.windows)
        assert total <= settings.habits_max_claimed_hours


class TestPayloadRoundTrip:
    def test_round_trip_equality_over_all_fields(self) -> None:
        """Serialization pairs must round-trip over ALL fields (CLAUDE.md)."""
        profile = compute_rhythm_profile(
            _regular_user(), AS_OF, THRESHOLDS, previously_claimed={WEEKEND: True}
        )
        rebuilt = RhythmProfile.from_payload(profile.to_payload())
        assert rebuilt == profile

    def test_from_payload_tolerates_missing_keys(self) -> None:
        rebuilt = RhythmProfile.from_payload({})
        assert rebuilt.weekday.verdict == ProfileVerdict.INSUFFICIENT.value
        assert rebuilt.weekday.windows == ()
        assert rebuilt.sparse is False
