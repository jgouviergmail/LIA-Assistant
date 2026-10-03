"""Pure Routes response formatting and bounded model previews."""

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.field_names import FIELD_DISPLAY_ONLY
from src.core.i18n import _
from src.core.time_utils import format_time_with_date_context, parse_datetime
from src.domains.agents.display.urls import build_route_url
from src.domains.agents.display.values import list_values, nonnegative_integer, scalar_text
from src.domains.agents.tools.route_map_projection import route_map_data
from src.domains.agents.tools.routes_projection import (
    alternative_details,
    condensed_walk,
    flatten_steps,
    mapping,
    normalized_legs,
    ordered_waypoints,
    toll_prices,
)
from src.domains.agents.tools.routes_projection import (
    duration_seconds as parse_route_duration,
)
from src.domains.agents.utils.polyline import simplify_polyline_for_static_map
from src.domains.connectors.clients.google_routes_client import GoogleRoutesClient, TravelMode
from src.domains.connectors.media_attribution import with_attribution

logger = structlog.get_logger(__name__)


TRANSIT_PRIORITY_SCORES: dict[str, int] = {
    "HIGH_SPEED_TRAIN": 100,  # TGV
    "RAIL": 95,  # RER, TER, regional trains
    "TRAIN": 95,  # Same as RAIL
    "SUBWAY": 90,  # Metro
    "METRO_RAIL": 90,  # Metro variant
    "MONORAIL": 85,  # Monorail
    "HEAVY_RAIL": 85,  # Heavy rail
    "COMMUTER_TRAIN": 85,  # Commuter trains
    "LIGHT_RAIL": 80,  # Light rail
    "TRAM": 75,  # Tramway
    "CABLE_CAR": 70,  # Cable car
    "FUNICULAR": 70,  # Funicular
    "FERRY": 60,  # Ferry
    "BUS": 40,  # Bus (lowest priority for rail preference)
    "SHARE_TAXI": 30,  # Shared taxi
    "INTERCITY_BUS": 35,  # Intercity bus
    "TROLLEYBUS": 45,  # Electric bus (slightly better than bus)
    "OTHER": 50,  # Unknown/other
}


def _score_route_transit_priority(route: dict[str, Any]) -> tuple[int, int, int]:
    """
    Score a route based on transit type priority.

    Returns a tuple for sorting: (avg_priority, total_rail_steps, -total_bus_steps)
    Higher scores = better route (more rail/metro, less bus).

    This enables selecting routes that prioritize RER/Metro over Bus
    when multiple alternatives are available.

    Args:
        route: Route dict from Google Routes API response

    Returns:
        Tuple (avg_priority_score, rail_step_count, -bus_step_count) for sorting
    """
    transit_scores = []
    rail_steps = 0
    bus_steps = 0

    for leg in list_values(route.get("legs")):
        for step in list_values(mapping(leg).get("steps")):
            transit_details = mapping(mapping(step).get("transitDetails"))
            if transit_details:
                vehicle = mapping(mapping(transit_details.get("transitLine")).get("vehicle"))
                vehicle_type = scalar_text(vehicle.get("type")) or "OTHER"

                score = TRANSIT_PRIORITY_SCORES.get(vehicle_type, 50)
                transit_scores.append(score)

                # Count rail vs bus steps
                if vehicle_type in (
                    "RAIL",
                    "TRAIN",
                    "SUBWAY",
                    "METRO_RAIL",
                    "HIGH_SPEED_TRAIN",
                    "COMMUTER_TRAIN",
                    "HEAVY_RAIL",
                    "LIGHT_RAIL",
                    "TRAM",
                ):
                    rail_steps += 1
                elif vehicle_type in ("BUS", "INTERCITY_BUS", "TROLLEYBUS"):
                    bus_steps += 1

    # Calculate average priority score (default 50 if no transit steps)
    avg_score = sum(transit_scores) // len(transit_scores) if transit_scores else 50

    # Return tuple: (avg_priority, rail_count, -bus_count)
    # Negative bus_count so fewer buses = higher sort value
    return (avg_score, rail_steps, -bus_steps)


def _select_best_transit_route(routes: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Select the best transit route from alternatives based on transit type priority.

    Prioritizes routes using more rail (RER, Metro, Tram) over bus.
    When scores are equal, prefers routes with more rail steps and fewer bus steps.

    Args:
        routes: List of route alternatives from Google Routes API

    Returns:
        Best route based on transit priority scoring
    """
    if len(routes) == 1:
        return routes[0]

    # Score each route and sort by priority
    scored_routes = [(route, _score_route_transit_priority(route)) for route in routes]

    # Sort by (avg_priority DESC, rail_steps DESC, bus_steps ASC)
    scored_routes.sort(key=lambda x: x[1], reverse=True)

    best_route = scored_routes[0][0]
    best_score = scored_routes[0][1]

    logger.info(
        "transit_route_selected",
        routes_count=len(routes),
        best_priority_score=best_score[0],
        best_rail_steps=best_score[1],
        best_bus_steps=-best_score[2],  # Negate back to positive
    )

    return best_route


def _condense_route_steps(steps: list[dict[str, Any]], max_steps: int) -> list[dict[str, Any]]:
    """
    Condense route steps intelligently to fit within max_steps limit.

    Condensation strategy (applied progressively only if needed):
    1. If steps fit within limit, return as-is
    2. First, merge only consecutive WALK steps (between transit legs)
    3. If still over limit, select evenly spaced steps preserving first/last

    Transit steps (bus, metro, etc.) are always preserved as-is.

    Args:
        steps: Full list of route steps
        max_steps: Maximum number of steps to return

    Returns:
        Condensed list of steps fitting within max_steps limit
    """
    if not steps or len(steps) <= max_steps:
        return steps

    # Phase 1: Only merge consecutive WALK steps (common in transit routes)
    # This preserves navigation steps individually
    merged_steps: list[dict[str, Any]] = []
    i = 0

    while i < len(steps):
        current_step = steps[i]
        current_mode = current_step.get("travel_mode", "")

        # Merge consecutive WALK steps only
        if current_mode == "WALK" and not current_step.get("transit"):
            j = i + 1
            while j < len(steps):
                next_step = steps[j]
                if next_step.get("travel_mode") == "WALK" and not next_step.get("transit"):
                    j += 1
                else:
                    break

            # Create merged WALK step only if multiple were merged
            if j > i + 1:
                merged_step = condensed_walk(steps[i:j])
                merged_steps.append(merged_step)
            else:
                merged_steps.append(current_step)

            i = j
        else:
            # Keep all other steps as-is (transit, drive, etc.)
            merged_steps.append(current_step)
            i += 1

    # Check if we're within limit after WALK merging
    if len(merged_steps) <= max_steps:
        return merged_steps

    # Phase 2: Select steps evenly while preserving transit and boundaries
    # Separate transit and non-transit steps
    transit_indices = [idx for idx, step in enumerate(merged_steps) if step.get("transit")]
    non_transit_indices = [idx for idx, step in enumerate(merged_steps) if not step.get("transit")]

    # Calculate how many non-transit steps we can keep
    remaining_slots = max_steps - len(transit_indices)

    if remaining_slots <= 0:
        # Only keep transit steps (truncate if needed)
        return [merged_steps[idx] for idx in transit_indices[:max_steps]]

    if remaining_slots >= len(non_transit_indices):
        # All steps fit after transit reservation
        return merged_steps

    # Select non-transit steps: always keep first and last, distribute middle evenly
    selected_non_transit: list[int] = []

    if len(non_transit_indices) >= 2 and remaining_slots >= 2:
        # Always keep first and last
        selected_non_transit.append(non_transit_indices[0])
        selected_non_transit.append(non_transit_indices[-1])

        # Distribute remaining slots evenly among middle steps
        middle_indices = non_transit_indices[1:-1]
        middle_slots = remaining_slots - 2

        if middle_slots > 0 and middle_indices:
            if len(middle_indices) <= middle_slots:
                selected_non_transit.extend(middle_indices)
            else:
                # Select evenly spaced indices
                for k in range(middle_slots):
                    idx = (
                        int(k * (len(middle_indices) - 1) / (middle_slots - 1))
                        if middle_slots > 1
                        else 0
                    )
                    selected_non_transit.append(middle_indices[idx])
    elif non_transit_indices:
        selected_non_transit = non_transit_indices[:remaining_slots]

    # Combine transit and selected non-transit, sort by original order
    all_selected = set(transit_indices) | set(selected_non_transit)
    result = [merged_steps[idx] for idx in sorted(all_selected)]

    return result


def _format_route_response(
    route_data: dict[str, Any],
    origin_display: str,
    destination_display: str,
    travel_mode: TravelMode,
    language: str,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    departure_time: str | None = None,
    arrival_time_target: str | None = None,
    is_arrival_based: bool = False,
    origin_coords: tuple[float, float] | None = None,
    dest_coords: tuple[float, float] | None = None,
    *,
    waypoints: list[str] | None = None,
    avoid_tolls: bool = False,
    avoid_highways: bool = False,
    avoid_ferries: bool = False,
) -> dict[str, Any]:
    """
    Format Google Routes API response for user consumption.

    Args:
        route_data: Raw response from Google Routes API
        origin_display: Human-readable origin
        destination_display: Human-readable destination
        travel_mode: Travel mode used
        language: Language code for formatting
        user_timezone: User's timezone for ETA calculation (default: DEFAULT_USER_DISPLAY_TIMEZONE)
        departure_time: Optional departure time in ISO 8601 format for ETA calculation
        arrival_time_target: Target arrival time (for calendar event routing)
        is_arrival_based: Whether this is an arrival-based route calculation
        origin_coords: Optional (lat, lng) tuple for origin marker on static map
        dest_coords: Optional (lat, lng) tuple for destination marker on static map

    Returns:
        Formatted route data dict with suggested_departure_time if arrival-based
    """
    routes = [entry for entry in list_values(route_data.get("routes")) if isinstance(entry, dict)]
    if not routes:
        return {
            "success": False,
            "error": "no_route_found",
            "message": _("No route found between these locations."),
        }

    # For TRANSIT mode with alternatives, select route prioritizing rail over bus
    if travel_mode == TravelMode.TRANSIT and len(routes) > 1:
        primary_route = _select_best_transit_route(routes)
    else:
        primary_route = routes[0]

    # Parse duration and distance
    duration_seconds = parse_route_duration(primary_route.get("duration"))
    distance_meters = nonnegative_integer(primary_route.get("distanceMeters"))
    if duration_seconds is None or distance_meters is None:
        return {
            "success": False,
            "error": "invalid_route_data",
            "message": _("Route measurements are unavailable."),
        }
    duration_minutes = duration_seconds // 60

    distance_km = GoogleRoutesClient.meters_to_km(distance_meters)

    # Format duration for display
    duration_formatted = GoogleRoutesClient.format_duration(duration_seconds, language)

    # Get traffic duration if available
    static_seconds = parse_route_duration(primary_route.get("staticDuration"))
    duration_in_traffic_minutes = None
    traffic_conditions = None

    if static_seconds is not None:
        if static_seconds != duration_seconds:
            duration_in_traffic_minutes = duration_minutes
            # Determine traffic conditions based on ratio
            ratio = duration_seconds / static_seconds if static_seconds > 0 else 1.0
            if ratio <= 1.1:
                traffic_conditions = "NORMAL"
            elif ratio <= 1.3:
                traffic_conditions = "LIGHT"
            elif ratio <= 1.5:
                traffic_conditions = "MODERATE"
            else:
                traffic_conditions = "HEAVY"

    # Get polyline for map display
    polyline = scalar_text(mapping(primary_route.get("polyline")).get("encodedPolyline"))

    # Extract start/end coordinates directly from polyline (first and last decoded points)
    # This ensures markers are EXACTLY at polyline endpoints for visual consistency
    # Douglas-Peucker preserves first/last points, so simplified polyline will match markers
    from src.domains.agents.utils.polyline import decode_polyline

    polyline_origin_coords: tuple[float, float] | None = None
    polyline_dest_coords: tuple[float, float] | None = None

    if polyline:
        try:
            decoded_points = decode_polyline(polyline)
            if decoded_points:
                polyline_origin_coords = decoded_points[0]  # First point = origin
                polyline_dest_coords = decoded_points[-1]  # Last point = destination
                logger.debug(
                    "polyline_endpoints_extracted",
                    origin=polyline_origin_coords,
                    destination=polyline_dest_coords,
                    total_points=len(decoded_points),
                )
        except (ValueError, IndexError) as e:
            logger.warning("polyline_decode_failed_for_markers", error=str(e))

    # Use polyline coords (ensures visual alignment with route trace), fallback to passed-in coords
    final_origin_coords = polyline_origin_coords or origin_coords
    final_dest_coords = polyline_dest_coords or dest_coords

    legs = normalized_legs(primary_route, travel_mode.value)
    steps = flatten_steps(legs)
    waypoints = ordered_waypoints(primary_route, waypoints)
    maps_url = build_route_url(
        origin_display,
        destination_display,
        travel_mode.value,
        waypoints,
        avoid_tolls=avoid_tolls,
        avoid_highways=avoid_highways,
        avoid_ferries=avoid_ferries,
    )

    # Build Static Map URL using proxy (API key hidden server-side)
    # Simplify polyline if needed to fit within URL length limits (Google allows 16384 chars)
    static_map_url = None
    if polyline:
        # Simplify polyline using defaults (max_url_length=14000, base_url_length=400)
        simplified_polyline = simplify_polyline_for_static_map(polyline)

        if simplified_polyline:
            # URL-encode the polyline for safe transmission via proxy
            encoded_polyline = quote(simplified_polyline, safe="")
            # Use proxy endpoint to avoid exposing API key to client
            # Add origin/destination coords for accurate markers (even with simplified polyline)
            static_map_url = (
                f"/api/v1/connectors/google-routes/static-map?polyline={encoded_polyline}"
            )
            # Add origin coords for green marker (accurate starting point)
            if final_origin_coords:
                static_map_url += f"&origin={final_origin_coords[0]},{final_origin_coords[1]}"
            # Add destination coords for red marker (accurate ending point)
            if final_dest_coords:
                static_map_url += f"&dest={final_dest_coords[0]},{final_dest_coords[1]}"

            # The map is BILLED when the browser fetches it, and the proxy counts
            # it then, on this turn: the URL carries the signed run id.
            static_map_url = with_attribution(static_map_url)

            logger.debug(
                "static_map_url_generated",
                original_polyline_length=len(polyline),
                simplified_polyline_length=len(simplified_polyline),
                url_length=len(static_map_url),
                has_origin_marker=bool(final_origin_coords),
                has_dest_marker=bool(final_dest_coords),
            )
        else:
            logger.warning(
                "static_map_url_skipped",
                reason="polyline_too_complex_to_simplify",
                polyline_length=len(polyline),
            )
    else:
        logger.warning("static_map_url_not_generated", reason="polyline_empty")

    estimates = toll_prices(primary_route)
    toll_info = next(
        (price for price in estimates if price["currency"] == "EUR"),
        estimates[0] if estimates else None,
    )

    # Calculate ETA (estimated time of arrival) in user's timezone
    eta = None
    eta_formatted = None
    # New fields for arrival-based routing
    target_arrival_time_iso = None
    target_arrival_formatted = None
    suggested_departure_time_iso = None
    suggested_departure_formatted = None

    if duration_seconds:
        try:
            tz = ZoneInfo(user_timezone)
        except KeyError, ValueError:
            tz = ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)

        now = datetime.now(tz)

        if is_arrival_based and arrival_time_target:
            # Arrival-based calculation: user wants to ARRIVE at a specific time
            # Calculate suggested departure time = arrival_time - duration
            # Note: UTC-to-local conversion is done in get_route_tool BEFORE API call
            parsed_arrival = parse_datetime(arrival_time_target)
            if parsed_arrival is not None:
                target_arrival_dt = parsed_arrival.astimezone(tz)
            else:
                target_arrival_dt = None

            if target_arrival_dt is not None:

                # Calculate suggested departure
                suggested_departure_dt = target_arrival_dt - timedelta(seconds=duration_seconds)

                # Store ISO formats
                target_arrival_time_iso = target_arrival_dt.isoformat()
                suggested_departure_time_iso = suggested_departure_dt.isoformat()

                # Format times using centralized helper (handles today/tomorrow/date context)
                target_arrival_formatted = format_time_with_date_context(
                    target_arrival_dt, now, language
                )
                suggested_departure_formatted = format_time_with_date_context(
                    suggested_departure_dt, now, language
                )

                # For arrival-based, ETA is the target arrival time
                eta = target_arrival_time_iso
                eta_formatted = target_arrival_formatted

                logger.info(
                    "route_arrival_based_calculation",
                    target_arrival=target_arrival_time_iso,
                    suggested_departure=suggested_departure_time_iso,
                    duration_minutes=duration_minutes,
                )
            else:
                logger.warning(
                    "arrival_time_parse_failed",
                    arrival_time_target=arrival_time_target,
                )
                # Fall back to standard ETA calculation
                is_arrival_based = False

        if not is_arrival_based:
            # Standard ETA calculation (departure-based)
            if departure_time:
                parsed_departure = parse_datetime(departure_time)
                if parsed_departure is not None:
                    # Convert to user's timezone for display
                    base_time = parsed_departure.astimezone(tz)
                    logger.debug(
                        "eta_using_departure_time",
                        departure_time=departure_time,
                        base_time=base_time.isoformat(),
                        user_timezone=user_timezone,
                    )
                else:
                    logger.warning(
                        "departure_time_parse_failed",
                        departure_time=departure_time,
                    )
                    base_time = now
            else:
                base_time = now

            calculated_eta = base_time + timedelta(seconds=duration_seconds)
            eta = calculated_eta.isoformat()

            # Format ETA using centralized helper (handles today/tomorrow/date context)
            eta_formatted = format_time_with_date_context(calculated_eta, now, language)

    model_steps = _condense_route_steps(steps, settings.routes_max_steps) if steps else []

    return {
        "success": True,
        "data": {
            "route": {
                "origin": origin_display,
                "destination": destination_display,
                "travel_mode": travel_mode.value,
                "distance_km": distance_km,
                "distance_meters": distance_meters,
                "duration_seconds": duration_seconds,
                "waypoints": list(waypoints or []),
                "avoid_tolls": avoid_tolls,
                "avoid_highways": avoid_highways,
                "avoid_ferries": avoid_ferries,
                FIELD_DISPLAY_ONLY: {
                    "route_map": route_map_data(routes, primary_route),
                    "steps": steps,
                    "toll_estimates": estimates,
                    "legs": legs,
                    "alternatives": alternative_details(routes, primary_route, travel_mode.value),
                },
                "duration_minutes": duration_minutes,
                "duration_formatted": duration_formatted,
                "duration_in_traffic_minutes": duration_in_traffic_minutes,
                "traffic_conditions": traffic_conditions,
                "polyline": polyline,
                "steps": model_steps,
                "steps_total": len(steps),
                "steps_preview_truncated": model_steps != steps,
                "maps_url": maps_url,
                "static_map_url": static_map_url,
                "toll_info": toll_info,
                "eta": eta,
                "eta_formatted": eta_formatted,
                # Arrival-based route fields
                "is_arrival_based": is_arrival_based,
                "target_arrival_time": target_arrival_time_iso,
                "target_arrival_formatted": target_arrival_formatted,
                "suggested_departure_time": suggested_departure_time_iso,
                "suggested_departure_formatted": suggested_departure_formatted,
            },
            "alternatives_count": len(routes) - 1,
        },
    }
