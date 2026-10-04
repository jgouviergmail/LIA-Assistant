"""Known provider fields retained for journey presentation, without raw-tree dumps."""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from math import isfinite

from src.domains.agents.display.values import list_values, nonnegative_integer, scalar_text


def mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def ordered_waypoints(route: Mapping[str, object], waypoints: list[str] | None) -> list[str]:
    points = list(waypoints or [])
    indices = list_values(route.get("optimizedIntermediateWaypointIndex"))
    ordered = [index for index in indices if isinstance(index, int) and not isinstance(index, bool)]
    if len(ordered) != len(points) or sorted(ordered) != list(range(len(points))):
        return points
    return [points[index] for index in ordered]


def toll_prices(route: Mapping[str, object]) -> list[dict[str, object]]:
    tolls = mapping(mapping(route.get("travelAdvisory")).get("tollInfo"))
    totals: dict[str, Decimal] = {}
    for record in list_values(tolls.get("estimatedPrice")):
        price = _money(record)
        if price:
            currency, amount = price
            totals[currency] = totals.get(currency, Decimal(0)) + amount
    return [
        {"currency": currency, "amount": float(amount), "formatted": f"{amount:.2f} {currency}"}
        for currency, amount in totals.items()
    ]


def _money(value: object) -> tuple[str, Decimal] | None:
    source = mapping(value)
    currency = scalar_text(source.get("currencyCode"))
    units = scalar_text(source.get("units", "0"))
    nanos = nonnegative_integer(source.get("nanos", 0))
    if len(currency) != 3 or not currency.isascii() or not currency.isupper():
        return None
    if (
        not units.isascii()
        or not units.isdigit()
        or len(units) > 19
        or nanos is None
        or nanos >= 1_000_000_000
    ):
        return None
    try:
        return currency, Decimal(units) + Decimal(nanos) / Decimal(1_000_000_000)
    except InvalidOperation:
        return None


def duration_seconds(value: object) -> int | None:
    if not isinstance(value, str) or not value.endswith("s"):
        return None
    try:
        number = float(value[:-1])
    except ValueError, OverflowError:
        return None
    return int(number) if isfinite(number) and number >= 0 else None


def condensed_walk(steps: list[dict[str, object]]) -> dict[str, object]:
    distances = [nonnegative_integer(step.get("distance_meters")) for step in steps]
    known = [value for value in distances if value is not None]
    total = sum(known) if len(known) == len(steps) else None
    text = f"Walk ({total} m)" if total is not None else "Walk"
    return {
        "instruction": text,
        "distance_meters": total,
        "travel_mode": "WALK",
        "maneuver": "WALK",
        "is_condensed": True,
        "condensed_count": len(steps),
    }


def _transit(value: object) -> dict[str, object]:
    source = mapping(value)
    line, stops = mapping(source.get("transitLine")), mapping(source.get("stopDetails"))
    vehicle = mapping(line.get("vehicle"))
    return {
        "line_name": scalar_text(line.get("nameShort")) or scalar_text(line.get("name")),
        "line_color": scalar_text(line.get("color")),
        "line_text_color": scalar_text(line.get("textColor")),
        "vehicle_type": scalar_text(vehicle.get("type")),
        "vehicle_name": scalar_text(mapping(vehicle.get("name")).get("text")),
        "headsign": scalar_text(source.get("headsign")),
        "departure_stop": scalar_text(mapping(stops.get("departureStop")).get("name")),
        "arrival_stop": scalar_text(mapping(stops.get("arrivalStop")).get("name")),
        "stop_count": nonnegative_integer(source.get("stopCount")),
    }


def normalized_step(value: Mapping[str, object], mode: str = "") -> dict[str, object]:
    navigation = mapping(value.get("navigationInstruction"))
    result: dict[str, object] = {
        "instruction": scalar_text(navigation.get("instructions")),
        "maneuver": scalar_text(navigation.get("maneuver")),
        "distance_meters": nonnegative_integer(value.get("distanceMeters")),
        "duration_seconds": duration_seconds(value.get("staticDuration")),
        "travel_mode": scalar_text(value.get("travelMode")) or mode,
    }
    if isinstance(value.get("transitDetails"), dict):
        transit = _transit(value["transitDetails"])
        result["transit"] = transit
        if not result["instruction"]:
            result["instruction"] = " · ".join(
                text
                for key in ("vehicle_name", "line_name", "headsign")
                if (text := scalar_text(transit.get(key)))
            )
    return result


def normalized_legs(route: Mapping[str, object], mode: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for leg in list_values(route.get("legs")):
        if not isinstance(leg, dict):
            continue
        result.append(
            {
                "distance_meters": nonnegative_integer(leg.get("distanceMeters")),
                "duration_seconds": duration_seconds(leg.get("duration")),
                "start_location": _point(leg.get("startLocation")),
                "end_location": _point(leg.get("endLocation")),
                "travel_mode": mode,
                "steps": [
                    normalized_step(step, mode)
                    for step in list_values(leg.get("steps"))
                    if isinstance(step, dict)
                ],
            }
        )
    return result


def _point(value: object) -> dict[str, float] | None:
    point = mapping(mapping(value).get("latLng"))
    latitude, longitude = point.get("latitude"), point.get("longitude")
    if not isinstance(latitude, int | float) or isinstance(latitude, bool):
        return None
    if not isinstance(longitude, int | float) or isinstance(longitude, bool):
        return None
    if not (
        isfinite(latitude)
        and isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return None
    return {"latitude": float(latitude), "longitude": float(longitude)}


def flatten_steps(legs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        step for leg in legs for step in list_values(leg.get("steps")) if isinstance(step, dict)
    ]


def alternative_details(
    routes: list[object], selected: Mapping[str, object], mode: str
) -> list[dict[str, object]]:
    return [
        {
            "distance_meters": nonnegative_integer(route.get("distanceMeters")),
            "duration_seconds": duration_seconds(route.get("duration")),
            "legs": normalized_legs(route, mode),
        }
        for route in routes
        if isinstance(route, dict) and route is not selected
    ]
