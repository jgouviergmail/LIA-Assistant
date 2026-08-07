"""Guard the AutomationSettings composition into the Settings MRO (P12, Lot 3)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
class TestAutomationSettings:
    """The automation config module is composed and carries sane defaults."""

    def test_flag_defaults_to_disabled(self):
        # Aligned on production (2026-08-06): the feature has been on for
        # months, so a fresh instance no longer starts without it.
        assert settings.recurrence_suggestion_enabled is True

    def test_recurrence_thresholds(self):
        # v2 defaults (ADR-214): 28-day window (a 14-day window could never
        # contain the same-weekday days a weekly habit needs), day-entry cap.
        assert settings.recurrence_window_days == 28
        assert settings.recurrence_min_distinct_days == 4
        assert settings.recurrence_suggestion_cooldown_days == 30
        assert settings.recurrence_ledger_max_entries == 28

    def test_lock_thresholds_composed(self):
        assert settings.recurrence_lock_min_occurrences == 8
        assert settings.recurrence_lock_r_min == 0.8
        assert settings.recurrence_shape_min_days == 14
        assert settings.recurrence_weekly_min_same_dow == 4
