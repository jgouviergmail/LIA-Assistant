"""Gate-rejection diagnostics of the pure rhythm detector (audit 2026-08-19, lot 0).

The detector rejects candidate windows through six gates (presence, wilson,
recent, halves, capture, selectivity). Until now the rejecting gate was
invisible: answering "why zero habits" required exporting the ledger and
re-implementing the instrumentation offline. These tests pin the diagnostics
contract of ``compute_rhythm_profile_with_diagnostics``:

- the profile is byte-identical to ``compute_rhythm_profile`` (pure refactor);
- each gate is attributed correctly on hand-built patterns;
- non-scanning verdicts (sparse / insufficient / diffuse) report no gate.

Thresholds are read from ``settings`` (never hardcoded).
"""

from __future__ import annotations

from datetime import date, timedelta

from src.core.config import settings
from src.domains.habits.models import ProfileVerdict
from src.domains.habits.rhythm import (
    GATE_CAPTURE,
    GATE_HALVES,
    GATE_PRESENCE,
    GATE_RECENT,
    GATE_SELECTIVITY,
    GATE_WILSON,
    WEEKDAY,
    WEEKEND,
    RhythmThresholds,
    compute_rhythm_profile,
    compute_rhythm_profile_with_diagnostics,
)

AS_OF = date(2026, 8, 4)  # a Tuesday — fixed so day classes are deterministic

THRESHOLDS = RhythmThresholds.from_settings(settings)

ALL_GATES = (
    GATE_PRESENCE,
    GATE_WILSON,
    GATE_RECENT,
    GATE_HALVES,
    GATE_CAPTURE,
    GATE_SELECTIVITY,
)


def _all_days(window_days: int | None = None) -> list[date]:
    n = window_days or THRESHOLDS.window_days
    first = AS_OF - timedelta(days=n - 1)
    return [first + timedelta(days=k) for k in range(n)]


def _routine_user() -> dict[date, dict[int, int]]:
    """Clean 8-10h ritual every day — claims windows in both classes."""
    return {d: {8: 2, 9: 1} for d in _all_days()}


def _diffuse_low_user() -> dict[date, dict[int, int]]:
    """Activity spread over the day at low per-hour presence.

    Mirrors the measured prod profile: presence exists in many bins but no
    2-4h window concentrates it — candidates die on presence/wilson and, when
    a window sneaks through, on capture/selectivity.
    """
    days: dict[date, dict[int, int]] = {}
    for i, d in enumerate(_all_days()):
        # Rotate activity across the day: each day hits 3 spread-out hours.
        h = (i * 5) % 24
        days[d] = {h: 1, (h + 7) % 24: 1, (h + 13) % 24: 1}
    return days


class TestProfileEquivalence:
    """The diagnostics variant must never change the detector's output."""

    def test_profiles_identical_for_routine_user(self) -> None:
        days = _routine_user()
        base = compute_rhythm_profile(days, AS_OF, THRESHOLDS)
        with_diag, _diag = compute_rhythm_profile_with_diagnostics(days, AS_OF, THRESHOLDS)
        assert base.to_payload() == with_diag.to_payload()

    def test_profiles_identical_for_diffuse_user(self) -> None:
        days = _diffuse_low_user()
        base = compute_rhythm_profile(days, AS_OF, THRESHOLDS)
        with_diag, _diag = compute_rhythm_profile_with_diagnostics(days, AS_OF, THRESHOLDS)
        assert base.to_payload() == with_diag.to_payload()


class TestGateAttribution:
    def test_diag_maps_carry_both_classes(self) -> None:
        _profile, diag = compute_rhythm_profile_with_diagnostics(
            _diffuse_low_user(), AS_OF, THRESHOLDS
        )
        assert set(diag.keys()) == {WEEKDAY, WEEKEND}

    def test_unknown_gates_never_emitted(self) -> None:
        _profile, diag = compute_rhythm_profile_with_diagnostics(
            _diffuse_low_user(), AS_OF, THRESHOLDS
        )
        for gates in diag.values():
            assert set(gates).issubset(set(ALL_GATES))

    def test_low_presence_user_rejected_on_presence_or_wilson(self) -> None:
        """Spread activity: most candidates die on the presence-family gates."""
        profile, diag = compute_rhythm_profile_with_diagnostics(
            _diffuse_low_user(), AS_OF, THRESHOLDS
        )
        assert profile.weekday.verdict == ProfileVerdict.NONE.value
        weekday_gates = diag[WEEKDAY]
        assert sum(weekday_gates.values()) > 0
        assert weekday_gates.get(GATE_PRESENCE, 0) + weekday_gates.get(GATE_WILSON, 0) > 0

    def test_clean_routine_reports_rejections_only_for_losing_candidates(self) -> None:
        """A claimed profile still scans 72 candidates: the non-winning ones
        are rejected and must be attributed (the diagnostics are a census of
        the scan, not an error signal)."""
        profile, diag = compute_rhythm_profile_with_diagnostics(_routine_user(), AS_OF, THRESHOLDS)
        assert profile.weekday.verdict == ProfileVerdict.WINDOWS.value
        assert sum(diag[WEEKDAY].values()) > 0

    def test_capture_selectivity_attributed_at_set_level(self) -> None:
        """A window that passes every per-candidate gate but concentrates too
        little of the day's activity dies on capture or selectivity — the
        prod signature (best window captured 26% for a 60% floor)."""
        days: dict[date, dict[int, int]] = {}
        for d in _all_days():
            # Strong daily presence at 8-9h (passes presence gates) but the
            # bulk of activity lives spread across five other hours.
            days[d] = {8: 1, 12: 3, 15: 3, 18: 3, 21: 3, 23: 3}
        profile, diag = compute_rhythm_profile_with_diagnostics(days, AS_OF, THRESHOLDS)
        assert profile.weekday.verdict == ProfileVerdict.NONE.value
        weekday_gates = diag[WEEKDAY]
        assert weekday_gates.get(GATE_CAPTURE, 0) + weekday_gates.get(GATE_SELECTIVITY, 0) > 0


class TestNonScanningVerdicts:
    def test_sparse_user_reports_no_gates(self) -> None:
        days = {AS_OF: {9: 1}}  # one active day out of 56 → sparse
        profile, diag = compute_rhythm_profile_with_diagnostics(days, AS_OF, THRESHOLDS)
        assert profile.sparse is True
        assert diag[WEEKDAY] == {} and diag[WEEKEND] == {}

    def test_insufficient_class_reports_no_gates(self) -> None:
        """A brand-new account (first_observed clips the window) reads
        INSUFFICIENT and never reaches the candidate scan."""
        first_observed = AS_OF - timedelta(days=3)
        days = {d: {9: 2} for d in _all_days() if d >= first_observed}
        profile, diag = compute_rhythm_profile_with_diagnostics(
            days, AS_OF, THRESHOLDS, first_observed=first_observed
        )
        assert profile.weekday.verdict == ProfileVerdict.INSUFFICIENT.value
        assert diag[WEEKDAY] == {}
