"""Bounded exact Routes geometries for presentation, never planner bindings."""

import re
from collections.abc import Mapping

from src.domains.agents.display.values import nonnegative_integer
from src.domains.agents.tools.routes_projection import duration_seconds, mapping
from src.domains.agents.utils.polyline import decode_polyline

MAX_MAP_ROUTES = 8
MAX_MAP_POLYLINE_CHARS = 100_000
MAX_MAP_POINTS = 25_000
_GROUPS = re.compile(r"(?:[\x5f-\x7e]{0,6}[\x3f-\x5e]){2,}")


def checked_polyline(value: object) -> tuple[str, int] | None:
    """Refuse malformed, excessive or off-earth data before any map allocation."""
    if not isinstance(value, str) or len(value) > MAX_MAP_POLYLINE_CHARS:
        return None
    if _GROUPS.fullmatch(value) is None:
        return None
    try:
        points = decode_polyline(value)
    except IndexError, ValueError, OverflowError:
        return None
    if not 2 <= len(points) <= MAX_MAP_POINTS:
        return None
    if any(not (-90 <= lat <= 90 and -180 <= lng <= 180) for lat, lng in points):
        return None
    return value, len(points)


def route_map_data(
    routes: list[object], selected: Mapping[str, object]
) -> dict[str, object] | None:
    """Keep original indices and explicitly state omitted invalid siblings.

    Refuse the whole interactive map when the source family/point budget is
    excessive. The ordinary source facts and static-map fallback remain intact.
    """
    if len(routes) > MAX_MAP_ROUTES:
        return None
    projected: list[dict[str, object]] = []
    primary_id: str | None = None
    point_count = 0
    for index, source in enumerate(routes):
        route = mapping(source)
        path = checked_polyline(mapping(route.get("polyline")).get("encodedPolyline"))
        if path is None:
            continue
        encoded, count = path
        point_count += count
        if point_count > MAX_MAP_POINTS:
            return None
        route_id = f"route-{index}"
        if source is selected:
            primary_id = route_id
        projected.append(
            {
                "id": route_id,
                "polyline": encoded,
                "distance_meters": nonnegative_integer(route.get("distanceMeters")),
                "duration_seconds": duration_seconds(route.get("duration")),
            }
        )
    if primary_id is None:
        return None
    return {
        "version": 1,
        "primary_id": primary_id,
        "routes": projected,
        "omitted_count": len(routes) - len(projected),
    }
