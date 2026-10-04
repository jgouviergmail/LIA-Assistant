"""Known weather measures, with explicit units and accumulation periods."""

from collections.abc import Mapping
from datetime import UTC, datetime
from math import isfinite
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.domains.agents.display.values import scalar_text


def mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def weather_source(data: Mapping[str, object]) -> Literal["google_weather", "openweathermap"]:
    return "google_weather" if data.get("source") == "google_weather" else "openweathermap"


def finite_number(value: object) -> float | None:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    return float(value) if isfinite(value) else None


def measurement(value: object, unit: str) -> str:
    number = finite_number(value)
    return f"{scalar_text(value)}{unit}" if number is not None else ""


def probability(value: object) -> str:
    number = finite_number(value)
    return f"{number * 100:.0f}" if number is not None and 0 <= number <= 1 else ""


def accumulation(value: object) -> str:
    source = mapping(value)
    return " · ".join(
        f"{amount:g} mm / {period[0]} h"
        for period in ("1h", "3h")
        if (amount := finite_number(source.get(period))) is not None and amount >= 0
    )


def observation(value: object) -> str:
    number = finite_number(value)
    if number is None:
        return ""
    try:
        return datetime.fromtimestamp(number, UTC).isoformat()
    except ValueError, OverflowError, OSError:
        return ""


def weather_timezone(value: str) -> str:
    try:
        return ZoneInfo(value).key
    except ValueError, ZoneInfoNotFoundError:
        return "UTC"


def extra_fields(
    source: Mapping[str, object], temp_unit: str, speed_unit: str
) -> dict[str, object]:
    """Pass through only known readings, never the provider's raw tree."""
    main, wind, clouds = (
        mapping(source.get("main")),
        mapping(source.get("wind")),
        mapping(source.get("clouds")),
    )
    visibility = finite_number(source.get("visibility"))
    result: dict[str, object] = {
        "pressure": measurement(main.get("pressure"), " hPa"),
        "visibility": (
            f"{visibility / 1000:.1f} km" if visibility is not None and visibility >= 0 else ""
        ),
        "clouds": (
            scalar_text(clouds.get("all")) if finite_number(clouds.get("all")) is not None else ""
        ),
        "wind_direction": measurement(wind.get("deg"), "°"),
        "wind_gust": measurement(wind.get("gust"), f" {speed_unit}"),
        "precipitation_probability": probability(source.get("pop")),
        "rain_amount": accumulation(source.get("rain")),
        "snow_amount": accumulation(source.get("snow")),
        "uv_index": finite_number(source.get("uvi")),
        "observation_time": observation(source.get("dt")),
    }
    for key in ("dew_point", "heat_index", "wind_chill"):
        result[key] = measurement(main.get(key), temp_unit)
    return {key: value for key, value in result.items() if value is not None and value != ""}
