"""Unit tests for BriefingSettings — env-overridable briefing widget limits."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.briefing import BriefingSettings


@pytest.mark.unit
class TestBriefingSettings:
    def test_defaults(self, monkeypatch):
        # Isolate from any ambient env so we assert the code defaults.
        for var in (
            "BRIEFING_MAX_AGENDA_ITEMS",
            "BRIEFING_AGENDA_LOOKAHEAD_HOURS",
            "BRIEFING_MAX_MAILS_ITEMS",
            "BRIEFING_MAX_BIRTHDAYS_ITEMS",
            "BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS",
            "BRIEFING_MAX_REMINDERS_ITEMS",
            "BRIEFING_HEALTH_WINDOW_DAYS",
            "BRIEFING_WEATHER_DAILY_FORECAST_DAYS",
        ):
            monkeypatch.delenv(var, raising=False)
        s = BriefingSettings()
        assert s.briefing_max_agenda_items == 10  # bumped from 3
        assert s.briefing_agenda_lookahead_hours == 24
        # Aligned on the proven production values (2026-08-06): the briefing
        # has been showing ten items per section, and looking a week ahead for
        # birthdays rather than a fortnight.
        assert s.briefing_max_mails_items == 10
        assert s.briefing_max_birthdays_items == 10
        assert s.briefing_max_birthdays_horizon_days == 7
        assert s.briefing_max_reminders_items == 10
        assert s.briefing_health_window_days == 14
        assert s.briefing_weather_daily_forecast_days == 5

    def test_env_override_propagates(self, monkeypatch):
        monkeypatch.setenv("BRIEFING_MAX_AGENDA_ITEMS", "25")
        monkeypatch.setenv("BRIEFING_AGENDA_LOOKAHEAD_HOURS", "72")
        s = BriefingSettings()
        assert s.briefing_max_agenda_items == 25
        assert s.briefing_agenda_lookahead_hours == 72

    def test_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            BriefingSettings(briefing_max_agenda_items=999)  # le=50
        with pytest.raises(ValidationError):
            BriefingSettings(briefing_weather_daily_forecast_days=10)  # le=5 (free-tier cap)
