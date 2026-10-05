"""Pure formatters for OpenWeatherMap API payloads.

Extracted from ``weather_tools`` (file-size ratchet): these functions shape
raw OpenWeatherMap responses (current weather, daily and 3-hour forecasts,
geocoding) into the tool-facing dict contract. They are pure — no I/O, no
runtime/session state — and therefore unit-testable in isolation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.time_utils import format_time_only, parse_rfc3339
from src.domains.agents.display.values import list_values, scalar_text
from src.domains.agents.tools.weather_fields import (
    extra_fields,
    finite_number,
    mapping,
    measurement,
    observation,
    probability,
    weather_timezone,
)


def _extract_location_from_geocode(
    geocode_results: list[dict[str, Any]],
) -> tuple[float, float, str, str] | None:
    """
    Extract coordinates and location info from geocode results.

    Args:
        geocode_results: List of location dicts from OpenWeatherMap geocoding API

    Returns:
        Tuple of (lat, lon, name, country) or None if no results
    """
    if not geocode_results:
        return None

    location = geocode_results[0]
    return (
        location.get("lat", 0.0),
        location.get("lon", 0.0),
        location.get("name", "Unknown"),
        location.get("country", ""),
    )


def _format_current_weather_response(
    weather: dict[str, Any],
    resolved_name: str,
    country: str,
    lat: float,
    lon: float,
    units: str,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> dict[str, Any]:
    """Format current weather API response.

    Args:
        weather: Raw weather data from OpenWeatherMap
        resolved_name: Resolved location name
        country: Country code
        lat: Latitude
        lon: Longitude
        units: Temperature units (metric/imperial)
        user_timezone: User's IANA timezone for sunrise/sunset formatting
    """
    temp_unit = "°C" if units == "metric" else "°F"
    speed_unit = "m/s" if units == "metric" else "mph"

    main = mapping(weather.get("main"))
    wind = mapping(weather.get("wind"))
    weather_info = next(
        (
            mapping(value)
            for value in list_values(weather.get("weather"))
            if isinstance(value, dict)
        ),
        {},
    )
    visibility = finite_number(weather.get("visibility"))

    # Format sunrise/sunset in user's timezone
    sys_info = mapping(weather.get("sys"))
    sunrise_ts = finite_number(sys_info.get("sunrise"))
    sunset_ts = finite_number(sys_info.get("sunset"))
    sunrise_str = (
        format_time_only(observation(sunrise_ts), weather_timezone(user_timezone))
        if observation(sunrise_ts)
        else ""
    )
    sunset_str = (
        format_time_only(observation(sunset_ts), weather_timezone(user_timezone))
        if observation(sunset_ts)
        else ""
    )

    # Use city name from API if resolved_name is empty (auto-resolved without address)
    location_name = resolved_name
    if not resolved_name:
        # OpenWeatherMap returns city name in "name" field
        api_city = weather.get("name", "")
        if api_city:
            location_name = api_city

    return {
        "success": True,
        "data": {
            "source": (
                "google_weather" if weather.get("source") == "google_weather" else "openweathermap"
            ),
            "location": {
                "name": location_name,
                "country": country or sys_info.get("country", ""),
                "lat": lat,
                "lon": lon,
            },
            "weather": {
                "temperature": measurement(main.get("temp"), temp_unit),
                "feels_like": measurement(main.get("feels_like"), temp_unit),
                "temp_min": measurement(main.get("temp_min"), temp_unit),
                "temp_max": measurement(main.get("temp_max"), temp_unit),
                "description": scalar_text(weather_info.get("description")),
                "icon": scalar_text(weather_info.get("icon")),
                "weather_main": scalar_text(weather_info.get("main")),
                "humidity": measurement(main.get("humidity"), "%"),
                "pressure": measurement(main.get("pressure"), " hPa"),
                "visibility": (
                    f"{visibility / 1000:.1f} km"
                    if visibility is not None and visibility >= 0
                    else ""
                ),
                "wind": {
                    "speed": measurement(wind.get("speed"), f" {speed_unit}"),
                    "direction": measurement(wind.get("deg"), "°"),
                    "gust": measurement(wind.get("gust"), f" {speed_unit}"),
                },
                "sunrise": sunrise_str,
                "sunset": sunset_str,
                **extra_fields(weather, temp_unit, speed_unit),
            },
        },
    }


def _format_forecast_response(
    daily_data: list[dict[str, Any]],
    resolved_name: str,
    country: str,
    days: int,
    units: str,
    target_date: str,
) -> dict[str, Any]:
    """
    Format daily forecast API response.

    Args:
        daily_data: Raw forecast data from OpenWeatherMap API (grouped by date in user's timezone)
        resolved_name: Location name
        country: Country code
        days: Number of days requested
        units: Temperature units (metric/imperial)
        target_date: Start date in YYYY-MM-DD format (user's timezone). Filter keeps days >= this date.
    """
    temp_unit = "°C" if units == "metric" else "°F"
    speed_unit = "m/s" if units == "metric" else "mph"

    # Filter by actual date instead of using blind index offset
    # This correctly handles cases where API data starts later than today
    # (e.g., when called late in the day, API may not have data for "today")
    filtered_data = [day for day in daily_data if day.get("date", "") >= target_date]

    # Take only the requested number of days
    daily_forecasts = []
    for day in filtered_data[:days]:
        daily_forecasts.append(
            {
                "date": day.get("date"),
                "temp": {
                    "min": measurement(day.get("temp_min"), temp_unit),
                    "max": measurement(day.get("temp_max"), temp_unit),
                    "avg": measurement(day.get("temp_avg"), temp_unit),
                },
                "description": day.get("condition", "N/A"),
                "icon": scalar_text(day.get("icon")),
                "weather_main": scalar_text(day.get("weather_main")),
                "humidity": measurement(day.get("humidity_avg"), "%"),
                "wind_speed": measurement(day.get("wind_speed_avg"), f" {speed_unit}"),
            }
        )

    return {
        "success": True,
        "data": {
            "location": {
                "name": resolved_name,
                "country": country,
            },
            "forecast_days": len(daily_forecasts),
            "daily": daily_forecasts,
        },
    }


def _entry_local_datetime(entry: dict[str, Any], user_timezone: str) -> datetime | None:
    """Project a 3-hour forecast entry onto the user's local wall clock.

    The OpenWeatherMap ``dt`` field is a UTC unix timestamp and ``dt_txt`` is its
    UTC rendering; presenting either verbatim misstates the time by the user's
    offset (a slot at 12:00 in Paris reads "10:00"). Everything user-facing must
    go through this projection.

    Args:
        entry: A raw forecast entry (expects ``dt``).
        user_timezone: The user's IANA timezone (e.g. "Europe/Paris").

    Returns:
        The timezone-aware local datetime, or None when ``dt`` is absent.
    """
    ts = finite_number(entry.get("dt"))
    tz = ZoneInfo(weather_timezone(user_timezone))
    if ts is None:
        raw = scalar_text(entry.get("dt_txt"))
        parsed = parse_rfc3339(raw.replace(" ", "T") + "Z")
        return parsed.astimezone(tz) if parsed else None
    try:
        return datetime.fromtimestamp(ts, tz=tz)
    except ValueError, OverflowError, OSError:
        return None


def _entry_local_date(entry: dict[str, Any], user_timezone: str) -> str:
    """Return the user-local calendar date (YYYY-MM-DD) of a 3-hour forecast entry.

    A single local day spans two UTC days, so the slot must be projected into the
    user's timezone to be grouped under the correct calendar date.

    Args:
        entry: A raw forecast entry (expects ``dt``; falls back to ``dt_txt``).
        user_timezone: The user's IANA timezone (e.g. "Europe/Paris").

    Returns:
        The local date in ISO ``YYYY-MM-DD`` format, or "" if undeterminable.
    """
    local = _entry_local_datetime(entry, user_timezone)
    if local is None:
        return ""
    return local.date().isoformat()


def _hourly_reading(
    entry: dict[str, object], temp_unit: str, speed_unit: str, user_timezone: str
) -> dict[str, object]:
    main = mapping(entry.get("main"))
    wind = mapping(entry.get("wind"))
    weather_info = next(
        (mapping(value) for value in list_values(entry.get("weather")) if isinstance(value, dict)),
        {},
    )
    local_dt = _entry_local_datetime(entry, user_timezone)
    return {
        "datetime": entry.get("dt"),
        "datetime_text": local_dt.strftime("%Y-%m-%d %H:%M:%S") if local_dt is not None else "",
        "temp": measurement(main.get("temp"), temp_unit),
        "feels_like": measurement(main.get("feels_like"), temp_unit),
        "description": scalar_text(weather_info.get("description")),
        "icon": scalar_text(weather_info.get("icon")),
        "weather_main": scalar_text(weather_info.get("main")),
        "humidity": measurement(main.get("humidity"), "%"),
        "precipitation_probability": probability(entry.get("pop")),
        "wind_speed": measurement(wind.get("speed"), f" {speed_unit}"),
        **extra_fields(entry, temp_unit, speed_unit),
    }


def _format_hourly_response(
    forecast_data: dict[str, Any],
    resolved_name: str,
    country: str,
    entries_needed: int,
    units: str,
    target_date: str | None = None,
    user_timezone: str = "UTC",
) -> dict[str, Any]:
    """Format hourly forecast API response.

    Args:
        forecast_data: Raw 3-hour forecast payload from OpenWeatherMap.
        resolved_name: Location name (empty triggers API city-name substitution).
        country: Country code.
        entries_needed: Sliding-window size used when no specific day is requested.
        units: Temperature units (metric/imperial).
        target_date: When set (YYYY-MM-DD, user timezone), keep only that day's
            3-hour slots instead of the rolling ``entries_needed`` window.
        user_timezone: User's IANA timezone. Used both to map each slot to a local
            calendar date AND to render ``datetime_text`` on the user's wall clock —
            the raw ``dt_txt`` is UTC and would misstate every hour by the offset.
    """
    temp_unit = "°C" if units == "metric" else "°F"
    speed_unit = "m/s" if units == "metric" else "mph"

    # Use city name from API if resolved_name is empty (auto-resolved without address)
    location_name = resolved_name
    if not resolved_name:
        # OpenWeatherMap forecast returns city in "city.name"
        city_data = forecast_data.get("city", {})
        api_city = city_data.get("name", "")
        if api_city:
            location_name = api_city
        if not country:
            country = city_data.get("country", "")

    forecast_list = [
        entry for entry in list_values(forecast_data.get("list")) if isinstance(entry, dict)
    ]

    # Specific-day request: keep that day's slots (projected to the user's local
    # date). Otherwise: rolling near-term window of the first ``entries_needed``.
    if target_date is not None:
        selected_entries = [
            e for e in forecast_list if _entry_local_date(e, user_timezone) == target_date
        ]
    else:
        selected_entries = forecast_list[:entries_needed]

    hourly_forecasts = [
        _hourly_reading(entry, temp_unit, speed_unit, user_timezone) for entry in selected_entries
    ]

    return {
        "success": True,
        "data": {
            "location": {
                "name": location_name,
                "country": country,
            },
            "interval": "3 hours",  # Free tier gives 3-hour intervals
            "forecast_entries": len(hourly_forecasts),
            "timezone": weather_timezone(user_timezone),
            "hourly": hourly_forecasts,
            "source": (
                "google_weather"
                if forecast_data.get("source") == "google_weather"
                else "openweathermap"
            ),
        },
    }
