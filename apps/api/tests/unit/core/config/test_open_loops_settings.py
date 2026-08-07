"""Guard the OpenLoopsSettings composition into the Settings MRO (P5, Lot 2)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
class TestOpenLoopsSettings:
    """The open-loops config module is composed and carries sane defaults."""

    def test_flag_defaults_to_disabled(self):
        # Aligned on production (2026-08-06): open loops ship enabled.
        assert settings.open_loops_enabled is True

    def test_nudge_policy_defaults(self):
        assert settings.open_loops_nudge_due_hours == 48
        assert settings.open_loops_nudge_stale_days == 7
        assert settings.open_loops_nudge_cooldown_days == 3
        assert settings.open_loops_expiry_days == 21

    def test_caps_defaults(self):
        assert settings.open_loops_max_open_per_user == 30
        assert settings.open_loops_extraction_max_items == 5
