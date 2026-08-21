"""WeatherCard AQ/pollen enrichment rendering (2026-08).

The card already had a dormant AQI slot (assuming the EPA scale). Google's
universal index is INVERTED (100 = excellent), so when the enrichment ships
its own localized category, the card must show THAT wording and never
re-derive a label from the number.
"""

from __future__ import annotations

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.weather_card import WeatherCard

pytestmark = pytest.mark.unit


def _ctx() -> RenderContext:
    return RenderContext(viewport="desktop", language="fr", timezone="Europe/Paris")


class TestAirQualityRendering:
    def test_api_category_wins_over_the_epa_label(self) -> None:
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "aqi": 71,
                "aqi_category": "Bonne qualité de l'air",
            },
            _ctx(),
            with_wrapper=False,
        )
        # The apostrophe is HTML-escaped by the card (XSS boundary).
        assert "Bonne qualité de l&#x27;air" in html
        # 71 on the EPA scale would read "Modéré" — the inverted UAQI must
        # never be labeled through the EPA table.
        assert "Modéré" not in html

    def test_category_without_a_number_still_renders(self) -> None:
        # MEASURED in prod: the French national index has a category and NO
        # number. Gating the row on the number hid the whole air-quality
        # signal for every French user.
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "aqi": None,
                "aqi_category": "Moyen",
                "aqi_label": "IQA (FR)",
                "has_air_quality": True,
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Moyen" in html
        assert "IQA (FR)" in html
        # No fabricated number, and no empty parentheses either.
        assert "()" not in html
        assert "None" not in html

    def test_value_and_label_render_together_when_both_exist(self) -> None:
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "aqi": 66,
                "aqi_category": "Bonne qualité de l&#x27;air",
                "aqi_label": "Universal AQI",
                "has_air_quality": True,
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "66" in html
        assert "Universal AQI" in html

    def test_legacy_numeric_aqi_keeps_the_epa_label(self) -> None:
        html = WeatherCard().render(
            {"temperature": "21°C", "description": "ciel dégagé", "aqi": 42},
            _ctx(),
            with_wrapper=False,
        )
        assert "Bon" in html


class TestForecastCardRendering:
    def test_forecast_card_shows_the_environment_line(self) -> None:
        # "Il fait quoi cette semaine ?" — the air-quality/pollen signal of
        # TODAY is what decides an outdoor plan, so the multi-day strip
        # carries it too (the enrichment is cached, so it costs nothing extra).
        html = WeatherCard().render(
            {
                "type": "forecast",
                "forecasts": [
                    {"date": "2026-08-22", "temp_max": "24°C", "temp_min": "14°C"},
                    {"date": "2026-08-23", "temp_max": "26°C", "temp_min": "15°C"},
                ],
                "aqi_category": "Moyen",
                "aqi_label": "IQA (FR)",
                "has_air_quality": True,
                "pollen": [{"name": "Graminées", "category": "Élevé", "index": 4}],
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Moyen" in html
        assert "Graminées" in html

    def test_forecast_card_without_enrichment_is_unchanged(self) -> None:
        html = WeatherCard().render(
            {
                "type": "forecast",
                "forecasts": [{"date": "2026-08-22", "temp_max": "24°C", "temp_min": "14°C"}],
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Pollen" not in html
        assert "Qualité de l" not in html


class TestPollenRendering:
    def test_in_season_pollen_lines_are_rendered(self) -> None:
        html = WeatherCard().render(
            {
                "temperature": "21°C",
                "description": "ciel dégagé",
                "pollen": [
                    {"name": "Graminées", "category": "Élevé", "index": 4},
                    {"name": "Ambroisie", "category": "Modéré", "index": 2},
                ],
            },
            _ctx(),
            with_wrapper=False,
        )
        assert "Pollen" in html
        assert "Graminées" in html
        assert "Élevé" in html
        assert "Ambroisie" in html

    def test_no_pollen_data_renders_nothing(self) -> None:
        html = WeatherCard().render(
            {"temperature": "21°C", "description": "ciel dégagé"},
            _ctx(),
            with_wrapper=False,
        )
        assert "Pollen" not in html
