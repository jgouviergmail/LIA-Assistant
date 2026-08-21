"""Briefing weather card carries the AQ/pollen enrichment (2026-08).

The home-page weather card does NOT go through the weather tool: the
briefing fetches the provider client directly. Enriching only the chat tool
left the surface the user sees FIRST unchanged (reported in prod, 2026-08-21).

Contract mirrors the chat card: the enrichment is optional and fail-quiet —
a briefing must never break because air quality could not be fetched.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.briefing.formatters import format_weather_data
from src.domains.briefing.schemas import AirQuality, PollenItem, WeatherData

pytestmark = pytest.mark.unit

_CURRENT: dict[str, Any] = {
    "main": {"temp": 21.4, "feels_like": 20.0, "humidity": 55},
    "weather": [{"main": "Clear", "description": "ciel dégagé", "icon": "01d"}],
    "wind": {"speed": 3.0, "deg": 180},
}
_FORECAST: dict[str, Any] = {"list": [], "city": {"name": "Paris"}}


def _build(environment: dict[str, Any] | None) -> WeatherData:
    from zoneinfo import ZoneInfo

    return format_weather_data(
        current=dict(_CURRENT),
        forecast=dict(_FORECAST),
        city="Paris",
        user_tz=ZoneInfo("Europe/Paris"),
        daily_forecast_days=5,
        environment=environment,
    )


class TestBriefingWeatherEnrichment:
    def test_air_quality_and_pollen_reach_the_payload(self) -> None:
        data = _build(
            {
                "aqi": None,
                "aqi_category": "Moyen",
                "aqi_label": "IQA (FR)",
                "has_air_quality": True,
                "pollen": [{"name": "Graminées", "category": "Élevé", "index": 4}],
            }
        )
        assert isinstance(data.air_quality, AirQuality)
        assert data.air_quality.category == "Moyen"
        assert data.air_quality.index_label == "IQA (FR)"
        # The national index has no number — the payload must not invent one.
        assert data.air_quality.value is None
        assert data.pollen == [PollenItem(name="Graminées", category="Élevé", index=4)]

    def test_numeric_index_is_carried_as_is(self) -> None:
        data = _build(
            {
                "aqi": 66,
                "aqi_category": "Bonne qualité de l'air",
                "aqi_label": "Universal AQI",
                "has_air_quality": True,
                "pollen": [],
            }
        )
        assert data.air_quality is not None
        assert data.air_quality.value == 66
        assert data.pollen == []

    def test_no_enrichment_leaves_the_card_unchanged(self) -> None:
        data = _build(None)
        assert data.air_quality is None
        assert data.pollen == []
        # And the rest of the card is untouched.
        assert data.temperature_c == 21.4

    def test_enrichment_without_usable_air_quality_is_dropped(self) -> None:
        data = _build(
            {
                "aqi": None,
                "aqi_category": "",
                "aqi_label": "",
                "has_air_quality": False,
                "pollen": [],
            }
        )
        assert data.air_quality is None
