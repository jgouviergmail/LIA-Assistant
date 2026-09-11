"""Guard the AutomationSettings composition into the Settings MRO (P12, Lot 3)."""

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.config.automation import AutomationSettings


@pytest.mark.unit
class TestAutomationSettings:
    """The automation config module is composed and carries sane defaults."""

    def test_flag_defaults_to_disabled(self):
        # Aligned on production (2026-08-06): the feature has been on for
        # months, so a fresh instance no longer starts without it.
        assert settings.recurrence_suggestion_enabled is True

    def test_recurrence_thresholds(self):
        # v3 defaults (ADR-214, recalibrated 2026-09-11): 35-day window — five
        # weekly slots, so one missed week no longer kills a weekly lock (the
        # 28-day window demanded a 4/4 perfect month: lock stability measured
        # 71 % at d28 falling to 64 % at d42). Day-entry cap = window days.
        assert settings.recurrence_window_days == 35
        assert settings.recurrence_min_distinct_days == 4
        assert settings.recurrence_suggestion_cooldown_days == 30
        assert settings.recurrence_ledger_max_entries == 35

    def test_lock_thresholds_composed(self):
        assert settings.recurrence_lock_min_occurrences == 6
        assert settings.recurrence_lock_r_min == 0.8
        assert settings.recurrence_shape_min_span_days == 10
        assert settings.recurrence_daily_density_min == 0.6
        assert settings.recurrence_intermittent_r_min == 0.9
        assert settings.recurrence_weekly_min_same_dow == 4

    def test_the_distinct_days_labeling_key_is_retired(self):
        """``recurrence_shape_min_days`` counted DISTINCT days; the 2026-09-11
        labeling counts the calendar SPAN. A changed meaning gets a new name:
        a production .env still carrying the old key must not silently feed
        an old number into a new rule."""
        assert not hasattr(settings, "recurrence_shape_min_days")


@pytest.mark.unit
class TestLedgerCapCoversTheWindow:
    """The ledger stores DAY entries, trimmed to the cap; the lock reads the
    window. A cap below the window silently shortens every window — the v1
    occurrence cap starved the spread lock exactly this way (ADR-214). The
    boot refuses the incoherence rather than learning on a truncated ledger."""

    def test_cap_below_window_refuses_to_boot(self, monkeypatch):
        monkeypatch.setenv("RECURRENCE_WINDOW_DAYS", "35")
        monkeypatch.setenv("RECURRENCE_LEDGER_MAX_ENTRIES", "28")
        with pytest.raises(ValidationError, match="RECURRENCE_LEDGER_MAX_ENTRIES"):
            AutomationSettings()

    def test_cap_equal_to_window_boots(self, monkeypatch):
        monkeypatch.setenv("RECURRENCE_WINDOW_DAYS", "35")
        monkeypatch.setenv("RECURRENCE_LEDGER_MAX_ENTRIES", "35")
        assert AutomationSettings().recurrence_ledger_max_entries == 35

    def test_cap_above_window_boots(self, monkeypatch):
        monkeypatch.setenv("RECURRENCE_WINDOW_DAYS", "28")
        monkeypatch.setenv("RECURRENCE_LEDGER_MAX_ENTRIES", "35")
        assert AutomationSettings().recurrence_window_days == 28

    def test_shipped_defaults_are_coherent(self):
        assert settings.recurrence_ledger_max_entries >= settings.recurrence_window_days
