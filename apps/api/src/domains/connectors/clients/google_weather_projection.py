"""Supplied Google weather fields and OWM-compatible unit conversion."""

from collections.abc import Mapping
from math import isfinite


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool) and isfinite(value)
        else None
    )


def google_weather_fields(payload: Mapping[str, object]) -> dict[str, object]:
    precip = _mapping(payload.get("precipitation"))
    probability = _number(_mapping(precip.get("probability")).get("percent"))
    fields: dict[str, object] = {
        "uvi": _number(payload.get("uvIndex")),
        "clouds": {"all": _number(payload.get("cloudCover"))},
    }
    if probability is not None and 0 <= probability <= 100:
        fields["pop"] = probability / 100
    for key, target in (("qpf", "rain"), ("snowQpf", "snow")):
        quantity = _mapping(precip.get(key))
        amount = _number(quantity.get("quantity"))
        if amount is not None and amount >= 0 and quantity.get("unit") == "MILLIMETERS":
            fields[target] = {"1h": amount}
    visibility = _number(_mapping(payload.get("visibility")).get("distance"))
    if visibility is not None and visibility >= 0:
        fields["visibility"] = int(visibility * 1000)
    return {key: value for key, value in fields.items() if value is not None}


def convert_owm_units(payload: Mapping[str, object], units: str) -> dict[str, object]:
    """Convert only temperatures and wind; OWM pressure/visibility/rain keep SI units."""
    if units != "imperial":
        return dict(payload)
    main, wind = dict(_mapping(payload.get("main"))), dict(_mapping(payload.get("wind")))
    for key in (
        "temp",
        "temp_min",
        "temp_max",
        "feels_like",
        "dew_point",
        "heat_index",
        "wind_chill",
    ):
        if (value := _number(main.get(key))) is not None:
            main[key] = value * 1.8 + 32
    for key in ("speed", "gust"):
        if (value := _number(wind.get(key))) is not None:
            wind[key] = value * 2.23693629
    return {**payload, "main": main, "wind": wind}
