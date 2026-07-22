"""Guard the AutomationSettings composition into the Settings MRO (P12, Lot 3)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
class TestAutomationSettings:
    """The automation config module is composed and carries sane defaults."""

    def test_flag_defaults_to_disabled(self):
        assert settings.recurrence_suggestion_enabled is False

    def test_recurrence_thresholds(self):
        assert settings.recurrence_window_days == 14
        assert settings.recurrence_min_distinct_days == 3
        assert settings.recurrence_suggestion_cooldown_days == 30
        assert settings.recurrence_ledger_max_entries == 20
