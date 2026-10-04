"""Closed, bounded HTML presentation contract; never raw provider dictionaries."""

import json
import re
from collections.abc import Mapping

from src.domains.agents.display.escaping import escape_html
from src.domains.agents.display.values import nonnegative_integer


def render_route_map(source: object, fallback: str) -> str:
    if not isinstance(source, Mapping) or source.get("version") != 1:
        return fallback
    routes = source.get("routes")
    if not isinstance(routes, list) or not 1 <= len(routes) <= 8:
        return fallback
    projected = _project_routes(routes)
    if projected is None:
        return fallback
    ids = {route["id"] for route in projected}
    primary = source.get("primary_id")
    omitted = nonnegative_integer(source.get("omitted_count"))
    if not isinstance(primary, str) or primary not in ids or omitted is None or omitted > 8:
        return fallback
    wire = json.dumps(
        {"version": 1, "primary_id": primary, "routes": projected, "omitted_count": omitted},
        separators=(",", ":"),
    )
    return f'<div class="lia-route-map" data-route-map="{escape_html(wire)}">{fallback}</div>'


def _project_routes(routes: list[object]) -> list[dict[str, object]] | None:
    projected: list[dict[str, object]] = []
    ids: set[str] = set()
    for route in routes:
        if not isinstance(route, Mapping):
            return None
        route_id, encoded = route.get("id"), route.get("polyline")
        if not isinstance(route_id, str) or re.fullmatch(r"route-[0-7]", route_id) is None:
            return None
        if route_id in ids or not isinstance(encoded, str) or not 2 <= len(encoded) <= 100_000:
            return None
        ids.add(route_id)
        projected.append(
            {
                "id": route_id,
                "polyline": encoded,
                "distance_meters": nonnegative_integer(route.get("distance_meters")),
                "duration_seconds": nonnegative_integer(route.get("duration_seconds")),
            }
        )
    return projected
