"""Authored provider attributions; no branding or links taken from raw payloads."""

from collections.abc import Mapping

GOOGLE_MAPS_ATTRIBUTION = '<span class="lia-google-attribution" translate="no">Google Maps</span>'


def weather_attribution(data: Mapping[str, object]) -> str:
    if data.get("source") == "google_weather":
        return (
            '<div class="lia-card__source">'
            + GOOGLE_MAPS_ATTRIBUTION
            + '<span translate="no">Source: Includes weather data from Google</span></div>'
        )
    if data.get("source") == "openweathermap":
        return '<div class="lia-card__source"><span translate="no">OpenWeatherMap</span></div>'
    return ""
