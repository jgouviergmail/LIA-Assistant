"""Shared weather normalization helpers (lot E, 2026-08).

The internal weather shape of LIA is the OpenWeatherMap JSON (19 call sites
consume it). Every weather provider client normalizes to that shape at its
boundary; the daily aggregation over a 3-hourly forecast list lives here so
OpenWeatherMap and Google Weather share one implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime
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


def aggregate_daily_forecast(
    forecast: dict[str, Any], days: int, user_timezone: str
) -> dict[str, Any]:
    """Aggregate an OWM-shaped 3-hourly forecast into daily summaries.

    Days are grouped in the USER'S timezone so "tomorrow" matches the user's
    local midnight (extracted verbatim from OpenWeatherMapClient, 2026-08).

    Args:
        forecast: OWM-shaped forecast ({"list": [...], "city": {...}}).
        days: Number of daily summaries to return.
        user_timezone: IANA timezone for the day grouping.

    Returns:
        Dict with "daily" summaries (date, temp_min/max/avg, condition,
        humidity_avg, wind_speed_avg) and the pass-through "city" info.
    """
    try:
        tz: Any = ZoneInfo(user_timezone)
    except KeyError, ValueError:
        logger.warning("invalid_user_timezone", timezone=user_timezone, fallback="UTC")
        tz = UTC

    daily_data: dict[str, dict[str, Any]] = {}
    for entry in forecast.get("list", []):
        dt_utc = datetime.fromtimestamp(entry["dt"], tz=UTC)
        date_key = dt_utc.astimezone(tz).strftime("%Y-%m-%d")

        if date_key not in daily_data:
            daily_data[date_key] = {
                "date": date_key,
                "temps": [],
                "conditions": [],
                "humidity": [],
                "wind_speed": [],
            }

        main = entry.get("main", {})
        weather = entry.get("weather", [{}])[0]
        wind = entry.get("wind", {})

        daily_data[date_key]["temps"].append(main.get("temp", 0))
        daily_data[date_key]["conditions"].append(weather.get("description", ""))
        daily_data[date_key]["humidity"].append(main.get("humidity", 0))
        daily_data[date_key]["wind_speed"].append(wind.get("speed", 0))

    daily_list = []
    for _date_key, data in sorted(daily_data.items())[:days]:
        temps = data["temps"]
        daily_list.append(
            {
                "date": data["date"],
                "temp_min": round(min(temps), 1),
                "temp_max": round(max(temps), 1),
                "temp_avg": round(sum(temps) / len(temps), 1),
                "condition": max(set(data["conditions"]), key=data["conditions"].count),
                "humidity_avg": round(sum(data["humidity"]) / len(data["humidity"])),
                "wind_speed_avg": round(sum(data["wind_speed"]) / len(data["wind_speed"]), 1),
            }
        )

    return {
        "daily": daily_list,
        "city": forecast.get("city", {}),
    }
