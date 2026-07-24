"""Pure formatters for OpenWeatherMap API payloads.

Extracted from ``weather_tools`` (file-size ratchet): these functions shape
raw OpenWeatherMap responses (current weather, daily and 3-hour forecasts,
geocoding) into the tool-facing dict contract. They are pure — no I/O, no
runtime/session state — and therefore unit-testable in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.time_utils import format_time_only


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

    main = weather.get("main", {})
    wind = weather.get("wind", {})
    weather_info = weather.get("weather", [{}])[0]
    clouds = weather.get("clouds", {})
    visibility = weather.get("visibility", 0)

    # Format sunrise/sunset in user's timezone
    sys_info = weather.get("sys", {})
    sunrise_ts = sys_info.get("sunrise")
    sunset_ts = sys_info.get("sunset")
    sunrise_str = format_time_only(sunrise_ts, user_timezone) if sunrise_ts else "N/A"
    sunset_str = format_time_only(sunset_ts, user_timezone) if sunset_ts else "N/A"

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
            "location": {
                "name": location_name,
                "country": country or sys_info.get("country", ""),
                "lat": lat,
                "lon": lon,
            },
            "weather": {
                "temperature": f"{main.get('temp', 'N/A')}{temp_unit}",
                "feels_like": f"{main.get('feels_like', 'N/A')}{temp_unit}",
                "temp_min": f"{main.get('temp_min', 'N/A')}{temp_unit}",
                "temp_max": f"{main.get('temp_max', 'N/A')}{temp_unit}",
                "description": weather_info.get("description", "N/A"),
                "icon": weather_info.get("icon", ""),
                "humidity": f"{main.get('humidity', 'N/A')}%",
                "pressure": f"{main.get('pressure', 'N/A')} hPa",
                "visibility": f"{visibility / 1000:.1f} km" if visibility else "N/A",
                "wind": {
                    "speed": f"{wind.get('speed', 'N/A')} {speed_unit}",
                    "direction": f"{wind.get('deg', 'N/A')}°",
                    "gust": f"{wind.get('gust', 'N/A')} {speed_unit}" if wind.get("gust") else None,
                },
                "clouds": clouds.get("all", "N/A"),
                "sunrise": sunrise_str,
                "sunset": sunset_str,
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
                    "min": f"{day.get('temp_min', 'N/A')}{temp_unit}",
                    "max": f"{day.get('temp_max', 'N/A')}{temp_unit}",
                    "avg": f"{day.get('temp_avg', 'N/A')}{temp_unit}",
                },
                "description": day.get("condition", "N/A"),
                "humidity": f"{day.get('humidity_avg', 'N/A')}%",
                "wind_speed": f"{day.get('wind_speed_avg', 'N/A')} {speed_unit}",
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
    ts = entry.get("dt")
    if ts is None:
        return None
    try:
        tz: Any = ZoneInfo(user_timezone)
    except (KeyError, ValueError):
        tz = UTC
    return datetime.fromtimestamp(ts, tz=tz)


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
        # Fallback: the UTC "dt_txt" date part (best effort when dt is absent).
        return str(entry.get("dt_txt", ""))[:10]
    return local.date().isoformat()


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

    hourly_forecasts = []
    forecast_list = forecast_data.get("list", [])

    # Specific-day request: keep that day's slots (projected to the user's local
    # date). Otherwise: rolling near-term window of the first ``entries_needed``.
    if target_date is not None:
        selected_entries = [
            e for e in forecast_list if _entry_local_date(e, user_timezone) == target_date
        ]
    else:
        selected_entries = forecast_list[:entries_needed]

    for entry in selected_entries:
        main = entry.get("main", {})
        wind = entry.get("wind", {})
        weather_info = entry.get("weather", [{}])[0]
        pop = entry.get("pop", 0)  # Probability of precipitation (0-1)

        # Format datetime ON THE USER'S WALL CLOCK. `dt` stays the raw UTC epoch
        # (unambiguous, consumed programmatically); `datetime_text` is what the
        # response LLM quotes and the weather card renders, so it must be local —
        # OpenWeatherMap's own `dt_txt` is UTC and shifted the whole strip.
        dt = entry.get("dt")
        local_dt = _entry_local_datetime(entry, user_timezone)
        dt_txt = (
            local_dt.strftime("%Y-%m-%d %H:%M:%S")
            if local_dt is not None
            else str(entry.get("dt_txt", ""))
        )

        hourly_forecasts.append(
            {
                "datetime": dt,
                "datetime_text": dt_txt,
                "temp": f"{main.get('temp', 'N/A')}{temp_unit}",
                "feels_like": f"{main.get('feels_like', 'N/A')}{temp_unit}",
                "description": weather_info.get("description", "N/A"),
                "icon": weather_info.get("icon", ""),
                "humidity": f"{main.get('humidity', 'N/A')}%",
                "precipitation_probability": f"{pop * 100:.0f}",
                "wind_speed": f"{wind.get('speed', 'N/A')} {speed_unit}",
            }
        )

    return {
        "success": True,
        "data": {
            "location": {
                "name": location_name,
                "country": country,
            },
            "interval": "3 hours",  # Free tier gives 3-hour intervals
            "forecast_entries": len(hourly_forecasts),
            "hourly": hourly_forecasts,
        },
    }
