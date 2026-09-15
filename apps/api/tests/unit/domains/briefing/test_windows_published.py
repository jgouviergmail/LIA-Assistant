"""The briefing's windows have ONE authority, and it is published (prompt audit 2026-09-12, A.6).

Measured: the synthesis prompt said « next 14 days » and « last 14 days » in prose, the
setting descriptions said « Default 14 » and « Default 5 », the constants said 7 and 10,
and the six locales said « Rien dans les 14 prochains jours » — five places for one
number, none of them the fetcher's. Now the settings are the authority: the prompt
reads them through placeholders, the descriptions derive from the constants, and the
cards endpoint publishes them so the UI can say what the fetcher actually looked at.
"""

from __future__ import annotations

import re

import pytest
from pydantic_settings import BaseSettings

from src.core.config import settings
from src.core.config.briefing import BriefingSettings
from src.domains.agents.prompts import load_prompt
from src.domains.briefing.constants import BRIEFING_SYNTHESIS_PROMPT_NAME
from src.domains.briefing.schemas import BriefingWindows, CardsResponse
from src.domains.briefing.service import build_briefing_windows

_DEFAULT_CLAIM = re.compile(r"Default (\d+)")


class TestPublishedWindows:
    def test_windows_are_the_settings(self) -> None:
        windows = build_briefing_windows()
        assert windows.birthdays_horizon_days == settings.briefing_max_birthdays_horizon_days
        assert windows.health_window_days == settings.briefing_health_window_days
        assert windows.agenda_lookahead_hours == settings.briefing_agenda_lookahead_hours
        assert windows.tasks_horizon_days == settings.briefing_tasks_horizon_days
        assert windows.weather_forecast_days == settings.briefing_weather_daily_forecast_days

    def test_cards_response_carries_them(self) -> None:
        assert "windows" in CardsResponse.model_fields
        assert CardsResponse.model_fields["windows"].annotation is BriefingWindows
        assert CardsResponse.model_fields["windows"].is_required()


class TestSynthesisPromptReadsTheSettings:
    def test_no_window_is_written_in_prose(self) -> None:
        text = load_prompt(BRIEFING_SYNTHESIS_PROMPT_NAME)
        assert not re.search(r"\b\d+ days\b", text), re.findall(r"\b\d+ days\b", text)
        assert "{birthdays_horizon_days}" in text
        assert "{health_window_days}" in text


class TestDescriptionsTellTheTruth:
    """A « Default N » in a field description equals the field's default."""

    @pytest.mark.parametrize(
        "name",
        [
            n
            for n in BriefingSettings.model_fields
            if "Default" in (BriefingSettings.model_fields[n].description or "")
        ],
    )
    def test_default_claim_matches_the_default(self, name: str) -> None:
        field = BriefingSettings.model_fields[name]
        claims = _DEFAULT_CLAIM.findall(field.description or "")
        assert claims, f"{name}: description mentions Default without a number"
        assert int(claims[0]) == int(field.default), (name, claims[0], field.default)

    def test_the_parametrization_is_not_empty(self) -> None:
        assert issubclass(BriefingSettings, BaseSettings)
        assert any(
            "Default" in (f.description or "") for f in BriefingSettings.model_fields.values()
        )
