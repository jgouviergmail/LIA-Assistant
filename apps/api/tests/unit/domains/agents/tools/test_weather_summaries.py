"""The three weather tool summaries follow the user's language.

``format_registry_response`` builds the text handed to the response LLM — the
model reads it and routinely quotes it, so it is user-visible output and must go
through the central i18n tables. All three summaries used to be hardcoded French
(observed in prod on 2026-07-23: "Prévisions météo pour Cappaghnanool, IE" reached
an English-speaking prompt path verbatim).

The language travels from the async ``execute_api_call`` to the sync formatter
inside the result dict (``LanguagePropagationMixin``) — never on ``self``, since
tool instances are singletons shared across concurrent requests.
"""

from __future__ import annotations

import pytest

from src.domains.agents.tools.weather_formatting import (
    _format_current_weather_response,
    _format_forecast_response,
)
from src.domains.agents.tools.weather_tools import (
    _get_current_weather_tool_impl,
    _get_weather_forecast_tool_impl,
)

pytestmark = [pytest.mark.unit]

_LANG_KEY = _get_current_weather_tool_impl._LANGUAGE_RESULT_KEY

# A French word that must NOT appear in a non-French summary. Chosen because it
# is the exact stem the hardcoded strings used.
_FRENCH_MARKERS = ("Prévisions", "Météo actuelle", "créneaux", "Humidité")


def _current_result(language: str) -> dict:
    weather = {
        "main": {
            "temp": 21.0,
            "feels_like": 20.0,
            "temp_min": 18.0,
            "temp_max": 24.0,
            "humidity": 55,
            "pressure": 1013,
        },
        "wind": {"speed": 3.2, "deg": 180},
        "weather": [{"description": "clear sky", "icon": "01d"}],
        "clouds": {"all": 5},
        "visibility": 10000,
        "sys": {"country": "FR", "sunrise": 1784930400, "sunset": 1784980000},
        "name": "Paris",
    }
    result = _format_current_weather_response(weather, "Paris", "FR", 48.85, 2.35, "metric")
    result[_LANG_KEY] = language
    return result


def _forecast_result(language: str, days: int) -> dict:
    daily = [
        {
            "date": f"2026-07-2{5 + i}",
            "temp_min": 14.0,
            "temp_max": 24.0,
            "temp_avg": 19.0,
            "condition": "clear sky",
            "humidity_avg": 55,
            "wind_speed_avg": 3.0,
        }
        for i in range(days)
    ]
    result = _format_forecast_response(daily, "Paris", "FR", days, "metric", "2026-07-25")
    result[_LANG_KEY] = language
    return result


class TestCurrentWeatherSummary:
    def test_is_localized(self):
        fr = _get_current_weather_tool_impl.format_registry_response(_current_result("fr")).message
        en = _get_current_weather_tool_impl.format_registry_response(_current_result("en")).message
        assert fr != en
        assert not any(marker in en for marker in _FRENCH_MARKERS)

    def test_carries_the_measured_values(self):
        message = _get_current_weather_tool_impl.format_registry_response(
            _current_result("en")
        ).message
        # The figures the model may quote must survive the localization rewrite.
        assert "21.0°C" in message
        assert "55%" in message
        assert "clear sky" in message

    @pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
    def test_every_supported_language_renders(self, language: str):
        message = _get_current_weather_tool_impl.format_registry_response(
            _current_result(language)
        ).message
        assert message and "{" not in message, "unsubstituted placeholder left in the summary"


class TestForecastSummary:
    def test_is_localized(self):
        fr = _get_weather_forecast_tool_impl.format_registry_response(
            _forecast_result("fr", 3)
        ).message
        en = _get_weather_forecast_tool_impl.format_registry_response(
            _forecast_result("en", 3)
        ).message
        assert fr != en
        assert not any(marker in en for marker in _FRENCH_MARKERS)

    def test_singular_and_plural_differ_in_french(self):
        """Prod showed "(1 jours)" — the count must agree with the noun."""
        one = _get_weather_forecast_tool_impl.format_registry_response(
            _forecast_result("fr", 1)
        ).message
        many = _get_weather_forecast_tool_impl.format_registry_response(
            _forecast_result("fr", 3)
        ).message
        assert "1 jour)" in one
        assert "3 jours)" in many

    def test_daily_lines_are_preserved(self):
        message = _get_weather_forecast_tool_impl.format_registry_response(
            _forecast_result("en", 2)
        ).message
        assert message.count("\n- ") == 2
        assert "2026-07-25" in message


class TestLanguageIsNeverStoredOnTheInstance:
    """Singletons must not leak one user's language into another's summary."""

    def test_two_languages_interleaved_stay_independent(self):
        fr_result = _current_result("fr")
        en_result = _current_result("en")
        first_fr = _get_current_weather_tool_impl.format_registry_response(fr_result).message
        en_msg = _get_current_weather_tool_impl.format_registry_response(en_result).message
        second_fr = _get_current_weather_tool_impl.format_registry_response(fr_result).message
        assert first_fr == second_fr
        assert en_msg != first_fr

    def test_no_language_attribute_is_set_on_the_tool(self):
        _get_current_weather_tool_impl.format_registry_response(_current_result("de"))
        assert not hasattr(_get_current_weather_tool_impl, "language")
        assert _LANG_KEY not in vars(_get_current_weather_tool_impl)
