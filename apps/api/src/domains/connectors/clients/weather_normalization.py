"""Shared weather normalization helpers (lot E, 2026-08).

The internal weather shape of LIA is the OpenWeatherMap JSON (19 call sites
consume it). Every weather provider client normalizes to that shape at its
boundary; the daily aggregation over a 3-hourly forecast list lives here so
OpenWeatherMap and Google Weather share one implementation.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, tzinfo
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

import structlog

logger = structlog.get_logger(__name__)


# Google condition enums must become OWM `weather[0].main` values at the
# provider boundary. Older cached briefing payloads may still hold the enum;
# the companion projection uses this same conversion when reading them.
# https://developers.google.com/maps/documentation/weather/reference/rest/v1/WeatherCondition
_GOOGLE_TO_OWM_MAIN: dict[str, str] = {
    "CLEAR": "Clear",
    "MOSTLY_CLEAR": "Clear",
    "PARTLY_CLOUDY": "Clouds",
    "MOSTLY_CLOUDY": "Clouds",
    "CLOUDY": "Clouds",
    "FOG": "Fog",
    "HAZE": "Haze",
    "WINDY": "Squall",
    "WIND_AND_RAIN": "Rain",
    "DRIZZLE": "Drizzle",
    "LIGHT_RAIN_SHOWERS": "Rain",
    "CHANCE_OF_SHOWERS": "Rain",
    "SCATTERED_SHOWERS": "Rain",
    "LIGHT_RAIN": "Rain",
    "RAIN": "Rain",
    "HEAVY_RAIN": "Rain",
    "RAIN_SHOWERS": "Rain",
    "HEAVY_RAIN_SHOWERS": "Rain",
    "LIGHT_TO_MODERATE_RAIN": "Rain",
    "MODERATE_TO_HEAVY_RAIN": "Rain",
    "RAIN_PERIODICALLY_HEAVY": "Rain",
    "SNOW": "Snow",
    "LIGHT_SNOW": "Snow",
    "HEAVY_SNOW": "Snow",
    "SNOW_SHOWERS": "Snow",
    "LIGHT_SNOW_SHOWERS": "Snow",
    "CHANCE_OF_SNOW_SHOWERS": "Snow",
    "SCATTERED_SNOW_SHOWERS": "Snow",
    "HEAVY_SNOW_SHOWERS": "Snow",
    "LIGHT_TO_MODERATE_SNOW": "Snow",
    "MODERATE_TO_HEAVY_SNOW": "Snow",
    "SNOWSTORM": "Snow",
    "SNOW_PERIODICALLY_HEAVY": "Snow",
    "HEAVY_SNOW_STORM": "Snow",
    "BLOWING_SNOW": "Snow",
    "RAIN_AND_SNOW": "Snow",
    "SLEET": "Snow",
    "HAIL": "Snow",
    "HAIL_SHOWERS": "Snow",
    "THUNDERSTORM": "Thunderstorm",
    "THUNDERSHOWER": "Thunderstorm",
    "LIGHT_THUNDERSTORM_RAIN": "Thunderstorm",
    "SCATTERED_THUNDERSTORMS": "Thunderstorm",
    "HEAVY_THUNDERSTORM": "Thunderstorm",
}
_OWM_MAINS = frozenset(_GOOGLE_TO_OWM_MAIN.values()) | {
    "Mist",
    "Smoke",
    "Dust",
    "Sand",
    "Ash",
    "Tornado",
    "Unknown",
}


def canonical_weather_main(value: str) -> str:
    """Return the OWM main code for Google or already normalized conditions.

    Future provider values become Unknown instead of silently pretending to be
    clear, rain or another condition that would drive the avatar incorrectly.
    """
    if value in _OWM_MAINS:
        return value
    return _GOOGLE_TO_OWM_MAIN.get(value, "Unknown")


def _samples(entries: list[dict[str, object]], block: str, field: str) -> list[float]:
    values = [entry.get(block) for entry in entries]
    candidates = [value.get(field) for value in values if isinstance(value, dict)]
    return [
        float(value)
        for value in candidates
        if isinstance(value, int | float) and not isinstance(value, bool) and isfinite(value)
    ]


def _average(values: list[float], digits: int) -> float | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    return round(mean, digits) if isfinite(mean) else None


def _day_summary(date: str, entries: list[dict[str, object]]) -> dict[str, object]:
    temps = _samples(entries, "main", "temp")
    weather_blocks = [entry.get("weather") for entry in entries]
    descriptions = [
        text
        for block in weather_blocks
        if isinstance(block, list)
        for value in block
        if isinstance(value, dict) and isinstance(text := value.get("description"), str) and text
    ]
    return {
        "date": date,
        "temp_min": round(min(temps), 1) if temps else None,
        "temp_max": round(max(temps), 1) if temps else None,
        "temp_avg": _average(temps, 1),
        "condition": Counter(descriptions).most_common(1)[0][0] if descriptions else "",
        "humidity_avg": _average(_samples(entries, "main", "humidity"), 0),
        "wind_speed_avg": _average(_samples(entries, "wind", "speed"), 1),
    }


def _slot_date(entry: dict[str, object], tz: tzinfo) -> str:
    value = entry.get("dt")
    if not isinstance(value, int | float) or isinstance(value, bool) or not isfinite(value):
        return ""
    try:
        return datetime.fromtimestamp(value, UTC).astimezone(tz).date().isoformat()
    except ValueError, OverflowError, OSError:
        return ""


def aggregate_daily_forecast(
    forecast: dict[str, Any], days: int, user_timezone: str
) -> dict[str, Any]:
    """Group received slots on the user's calendar; missing samples never become zero."""
    try:
        tz: tzinfo = ZoneInfo(user_timezone)
    except KeyError, ValueError:
        logger.warning("invalid_user_timezone", timezone=user_timezone, fallback="UTC")
        tz = UTC
    groups: dict[str, list[dict[str, object]]] = {}
    slots = forecast.get("list")
    for entry in slots if isinstance(slots, list) else []:
        if isinstance(entry, dict) and (date := _slot_date(entry, tz)):
            groups.setdefault(date, []).append(entry)
    city = forecast.get("city")
    return {
        "daily": [_day_summary(date, entries) for date, entries in sorted(groups.items())[:days]],
        "city": city if isinstance(city, dict) else {},
        "source": forecast.get("source", "openweathermap"),
    }
