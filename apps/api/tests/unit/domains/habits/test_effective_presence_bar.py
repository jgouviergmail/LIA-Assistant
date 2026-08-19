"""Effective presence bar publication (audit C-02, lot 3).

``n_eff`` is the Kish effective n of the day WEIGHTS — calendar-determined,
constant per class (≈25.4 weekday / ≈10.28 weekend on a full window). The
Wilson floor therefore dominates ``presence_min`` systematically, and the
REAL bar was 0.572 weekday vs 0.699 weekend while the config displayed 0.55
for both. A constraint the system applies must be published (ADR-184): these
tests pin the pure computation and its exposure in the API schema.

This lot PUBLISHES; it does not recalibrate — the thresholds' authority
remains the simulation harness (config docstring).
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.habits.rhythm import (
    RhythmThresholds,
    effective_presence_bar,
    wilson_lower_bound,
)

THRESHOLDS = RhythmThresholds.from_settings(settings)


class _CalibratedDefaults:
    """The audited 2026-08-19 calibration, pinned EXPLICITLY.

    The numeric prod-bar assertions must not drift with env overrides
    (CLAUDE.md: never hardcode a settings-driven threshold in a test —
    here the test OWNS its thresholds instead of reading the live ones).
    """

    habits_window_days = 56
    habits_half_life_days = 14.0
    habits_presence_min = 0.55
    habits_wilson_floor = 0.35
    habits_half_presence_min = 0.45
    habits_capture_min = 0.60
    habits_selectivity_min = 1.9
    habits_exit_presence = 0.45
    habits_exit_capture = 0.50
    habits_exit_selectivity = 1.6
    habits_min_neff_weekday = 12.0
    habits_min_neff_weekend = 6.0
    habits_recent_days = 14
    habits_recent_min = 0.30
    habits_max_claimed_hours = 6
    habits_waking_hours = 16.0
    habits_sparse_active_days_min = 0.30


CALIBRATED = RhythmThresholds.from_settings(_CalibratedDefaults())


class TestEffectivePresenceBar:
    def test_matches_prod_weekend_bar(self) -> None:
        """The measured prod asymmetry: n_eff=10.28 → bar ≈ 0.699 (under the
        pinned calibration — independent of live env overrides)."""
        bar = effective_presence_bar(10.28, CALIBRATED)
        assert bar == pytest.approx(0.699, abs=0.005)

    def test_matches_prod_weekday_bar(self) -> None:
        bar = effective_presence_bar(25.4, CALIBRATED)
        assert bar == pytest.approx(0.572, abs=0.005)

    def test_never_below_configured_presence_min(self) -> None:
        """With huge n_eff, Wilson stops binding: the bar IS presence_min."""
        assert effective_presence_bar(10_000.0, THRESHOLDS) == pytest.approx(
            THRESHOLDS.presence_min, abs=1e-6
        )

    def test_monotone_decreasing_in_n_eff(self) -> None:
        bars = [effective_presence_bar(n, THRESHOLDS) for n in (6.0, 10.0, 20.0, 40.0)]
        assert bars == sorted(bars, reverse=True)

    def test_zero_n_eff_returns_the_impossible_bar(self) -> None:
        """No effective observation → nothing can pass: bar = 1.0."""
        assert effective_presence_bar(0.0, THRESHOLDS) == 1.0

    def test_bar_actually_clears_wilson(self) -> None:
        """The published bar is sufficient: a candidate AT the bar passes the
        Wilson gate (the publication must never understate the constraint)."""
        for n_eff in (8.0, 12.0, 25.4):
            bar = effective_presence_bar(n_eff, THRESHOLDS)
            assert wilson_lower_bound(bar, n_eff) >= THRESHOLDS.wilson_floor - 1e-9


class TestSchemaPublication:
    def test_class_schema_carries_the_effective_bar(self) -> None:
        from src.domains.habits.schemas import HabitsProfileClassSchema

        assert "effective_presence_min" in HabitsProfileClassSchema.model_fields
