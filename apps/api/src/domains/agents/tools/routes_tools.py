"""
LangChain tools for Google Routes API operations.

Provides directions, travel time, and route calculations.
Uses global API Key authentication (GOOGLE_API_KEY) - no per-user OAuth required.

Features:
- Route computation (A to B directions)
- Route matrix (N origins to M destinations for optimization)
- Traffic-aware routing with real-time conditions
- Multiple travel modes (DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER)
- Route modifiers (avoid tolls, highways, ferries)
- Auto-resolution of origin (browser geolocation, home address)
- Cross-domain destination resolution (contacts, calendar events, places)
- HITL conditional triggering for significant routes (>20km)

API Reference:
- https://developers.google.com/maps/documentation/routes/overview
"""

from datetime import datetime, timedelta
from typing import Annotated, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, ROUTES_INVALID_DESTINATION_VALUES
from src.core.i18n import _
from src.core.i18n_v3 import V3Messages
from src.core.time_utils import format_time_with_date_context, parse_datetime
from src.domains.agents.constants import AGENT_ROUTE, CONTEXT_DOMAIN_ROUTES
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    ResolvedLocation,
    extract_coordinates,
    get_browser_geolocation,
    get_original_user_message,
    get_user_home_location,
    get_user_preferences,
    handle_tool_exception,
    resolve_location,
)
from src.domains.agents.utils.distance import calculate_distance_sync
from src.domains.agents.utils.polyline import simplify_polyline_for_static_map
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.connectors.clients.google_geocoding_helpers import reverse_geocode
from src.domains.connectors.clients.google_routes_client import (
    GoogleRoutesClient,
    RoutingPreference,
    TravelMode,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.cache.routes_cache import RoutesCache
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# ROUTE CONTEXT TYPE REGISTRATION
# ============================================================================


class RouteItem(BaseModel):
    """Schema for route data in context registry."""

    origin: dict[str, Any] | str | None = None
    destination: dict[str, Any] | str | None = None
    travel_mode: str | None = None
    distance_km: float | None = None
    duration_minutes: int | None = None
    duration_in_traffic_minutes: int | None = None
    polyline: str | None = None
    steps: list[dict[str, Any]] | None = None
    avoid_tolls: bool | None = None
    avoid_highways: bool | None = None
    avoid_ferries: bool | None = None
    traffic_conditions: str | None = None
    maps_url: str | None = None
    static_map_url: str | None = None
    toll_info: dict[str, Any] | None = None
    eta: str | None = None
    eta_formatted: str | None = None
    # Arrival-based route fields (for calendar event routing)
    is_arrival_based: bool = False
    target_arrival_time: str | None = None
    target_arrival_formatted: str | None = None
    suggested_departure_time: str | None = None
    suggested_departure_formatted: str | None = None


# Register routes context type for Data Registry support
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_ROUTES,
        agent_name=AGENT_ROUTE,
        item_schema=RouteItem,
        primary_id_field="destination",
        display_name_field="destination",
        reference_fields=[
            "origin",
            "destination",
            "travel_mode",
            "distance_km",
            "duration_minutes",
        ],
        icon="🗺️",
    )
)


# ============================================================================
# TRAVEL MODE PARSING
# ============================================================================


def _parse_travel_mode(mode_str: str | None, distance_km: float | None = None) -> TravelMode:
    """
    Parse travel mode string to TravelMode enum.

    Supports French and English mode names for natural language compatibility.

    DEFAULT RULE (when mode not specified):
    - If distance < 1 km → WALK
    - If distance >= 1 km → DRIVE
    - If distance unknown → DRIVE

    Args:
        mode_str: Travel mode string (e.g., "voiture", "car", "DRIVE", "à pied")
        distance_km: Estimated distance for default mode selection (optional)

    Returns:
        TravelMode enum value
    """
    if not mode_str:
        # Apply distance-based default rule
        threshold = settings.routes_walk_threshold_km
        if distance_km is not None and distance_km < threshold:
            logger.debug(
                "travel_mode_default_walk",
                distance_km=distance_km,
                threshold_km=threshold,
                reason=f"distance < {threshold}km",
            )
            return TravelMode.WALK
        return TravelMode.DRIVE

    mode_lower = mode_str.lower().strip()

    # Driving modes
    if mode_lower in ("drive", "driving", "car", "voiture", "auto", "automobile"):
        return TravelMode.DRIVE

    # Walking modes
    if mode_lower in ("walk", "walking", "foot", "on foot", "pied", "à pied", "a pied", "marche"):
        return TravelMode.WALK

    # Cycling modes
    if mode_lower in ("bicycle", "bike", "cycling", "vélo", "velo", "bicyclette"):
        return TravelMode.BICYCLE

    # Transit modes
    if mode_lower in (
        "transit",
        "public transit",
        "public transport",
        "transports",
        "transports en commun",
        "metro",
        "métro",
        "bus",
        "train",
        "tram",
    ):
        return TravelMode.TRANSIT

    # Two-wheeler modes
    if mode_lower in ("two_wheeler", "motorcycle", "moto", "scooter", "deux-roues", "deux roues"):
        return TravelMode.TWO_WHEELER

    # Try direct enum value
    try:
        return TravelMode(mode_str.upper())
    except ValueError:
        return TravelMode.DRIVE


# ============================================================================
# HITL CONDITIONAL LOGIC
# ============================================================================


def should_trigger_hitl(
    estimated_distance_km: float | None,
    travel_mode: TravelMode,
    waypoints: list[Any] | None = None,
    has_departure_time: bool = False,
) -> bool:
    """
    Determine if HITL (Human-In-The-Loop) should be triggered for route request.

    HITL is triggered for significant routes where user confirmation adds value.
    Short trips (like "boulangerie du coin") should NOT trigger HITL.

    Triggering conditions:
    1. Distance > routes_hitl_distance_threshold_km (significant trip)
    2. OR travel_mode is TRANSIT or TWO_WHEELER (non-standard modes)
    3. OR waypoints > 1 (multi-stop trip planning)
    4. OR departure_time specified (traffic timing important)

    Args:
        estimated_distance_km: Estimated distance (can be None if unknown)
        travel_mode: Selected travel mode
        waypoints: List of intermediate stops
        has_departure_time: Whether departure time was specified

    Returns:
        True if HITL should be triggered, False otherwise
    """
    # Distance threshold (significant trip)
    threshold = settings.routes_hitl_distance_threshold_km
    if estimated_distance_km is not None and estimated_distance_km > threshold:
        logger.debug(
            "hitl_triggered_by_distance",
            distance_km=estimated_distance_km,
            threshold_km=threshold,
        )
        return True

    # Non-standard travel modes that benefit from confirmation
    if travel_mode in (TravelMode.TRANSIT, TravelMode.TWO_WHEELER):
        logger.debug(
            "hitl_triggered_by_travel_mode",
            travel_mode=travel_mode.value,
        )
        return True

    # Multi-stop trips
    if waypoints and len(waypoints) > 1:
        logger.debug(
            "hitl_triggered_by_waypoints",
            waypoints_count=len(waypoints),
        )
        return True

    # Departure time specified (traffic timing matters)
    if has_departure_time:
        logger.debug("hitl_triggered_by_departure_time")
        return True

    return False


# ============================================================================
# DISTANCE ESTIMATION FOR TRAVEL MODE DEFAULT
# ============================================================================


def _estimate_distance_km(
    origin: dict[str, Any] | str | None,
    destination: dict[str, Any] | str | None,
) -> float | None:
    """
    Estimate straight-line distance between origin and destination.

    Used to determine default travel mode (WALK < 1km, DRIVE >= 1km).

    Args:
        origin: Origin as dict with lat/lon or string (address)
        destination: Destination as dict with lat/lon or string (address)

    Returns:
        Estimated distance in km, or None if coordinates unavailable
    """
    # Extract coordinates using centralized helper
    origin_lat, origin_lon = extract_coordinates(origin)
    dest_lat, dest_lon = extract_coordinates(destination)

    # Both coordinates needed
    if not (origin_lat and origin_lon and dest_lat and dest_lon):
        return None

    # Use Haversine for quick estimation
    result = calculate_distance_sync(
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        dest_lat=dest_lat,
        dest_lon=dest_lon,
    )

    logger.debug(
        "route_distance_estimated",
        distance_km=result.km,
        origin_coords=f"{origin_lat},{origin_lon}",
        dest_coords=f"{dest_lat},{dest_lon}",
    )

    return result.km


# ============================================================================
# LOCATION RESOLUTION HELPERS
# ============================================================================


async def _resolve_origin(
    runtime: ToolRuntime,
    origin: str | None,
    user_message: str,
    language: str,
) -> tuple[dict[str, Any] | str | None, str | None]:
    """
    Resolve origin location from various sources.

    Resolution priority:
    1. Explicit origin parameter (if provided)
    2. Browser geolocation (current position)
    3. User's home address (configured in profile)
    4. Fallback error message

    Args:
        runtime: Tool runtime for context access
        origin: Explicit origin (can be None for auto-resolution)
        user_message: Original user message for phrase detection
        language: Language code

    Returns:
        Tuple of (resolved_origin, error_message)
        - If resolved: (origin_dict_or_string, None)
        - If failed: (None, error_message)
    """
    # If explicit origin provided, use it
    if origin and origin.lower() not in (
        "auto",
        "automatic",
        "current",
        "current location",
        "ma position",
        "ici",
        "here",
    ):
        return origin, None

    # Try to resolve location automatically
    resolved, fallback_msg = await resolve_location(runtime, user_message, language)

    if resolved:
        logger.info(
            "route_origin_auto_resolved",
            source=resolved.source,
            lat=resolved.lat,
            lon=resolved.lon,
        )
        return {"lat": resolved.lat, "lon": resolved.lon, "address": resolved.address}, None

    # No location resolved yet
    # For routes, even if user message has EXPLICIT location (destination), we still need origin
    # Directly try browser geolocation then home location as fallback
    if not fallback_msg:
        # resolve_location returned (None, None) - likely EXPLICIT destination detected
        # Try browser geolocation directly for origin
        browser_loc = await get_browser_geolocation(runtime)
        if browser_loc:
            logger.info(
                "route_origin_fallback_to_browser",
                reason="EXPLICIT destination detected, using browser for origin",
                lat=browser_loc.lat,
                lon=browser_loc.lon,
            )
            return {
                "lat": browser_loc.lat,
                "lon": browser_loc.lon,
                "address": browser_loc.address,
            }, None

        # Try home location as last resort
        home_loc = await get_user_home_location(runtime)
        if home_loc:
            logger.info(
                "route_origin_fallback_to_home",
                reason="No browser geolocation, using home for origin",
                lat=home_loc.lat,
                lon=home_loc.lon,
            )
            return {"lat": home_loc.lat, "lon": home_loc.lon, "address": home_loc.address}, None

    # No location available at all
    if fallback_msg:
        return None, fallback_msg

    return None, _("Please specify a starting point or enable geolocation.")


async def _resolve_destination(
    destination: str,
    runtime: ToolRuntime | None = None,
    origin_location: ResolvedLocation | dict[str, Any] | str | None = None,
    language: str = "fr",
) -> str | dict[str, Any] | None:
    """
    Resolve destination from various sources.

    Uses Places API for place names when user location is available,
    improving resolution of local/ambiguous destinations like parks, cafes, etc.

    Resolution strategies:
    1. If destination is invalid (null, empty, None-like) -> return None
    2. If destination looks like an address (numbers, street words) -> pass-through
    3. If destination is a place name + user location available -> search via Places API

    Future enhancement: Cross-domain resolution from:
    - Contacts ("chez mon frère" -> contact's address)
    - Calendar events ("mon RDV de 14h" -> event location)

    Args:
        destination: Destination string
        runtime: Tool runtime for location access
        origin_location: Resolved origin for proximity-based search

    Returns:
        Resolved destination (address string or lat/lon dict), or None if invalid
    """
    # VALIDATION: Reject invalid destinations (null strings, empty, None-like)
    # This prevents Places API from hallucinating random locations
    if not destination or destination.strip().lower() in ROUTES_INVALID_DESTINATION_VALUES:
        logger.warning(
            "destination_invalid_rejected",
            destination=destination,
            reason="null_or_empty_destination",
        )
        return None

    # Check if destination looks like an address (has numbers or common address words)
    address_indicators = [
        any(char.isdigit() for char in destination),  # Contains numbers
        any(
            word in destination.lower()
            for word in [
                "rue",
                "route",
                "avenue",
                "boulevard",
                "place",
                "av.",
                "bd",
                "chemin",
                "allée",
                "impasse",
                ",",
                "cedex",
                "n°",
            ]
        ),
    ]

    if any(address_indicators):
        logger.debug("destination_is_address", destination=destination)
        return destination

    # For place names, try to resolve via Places API if we have user location
    if not runtime or not settings.google_api_key:
        return destination

    # Get user location for proximity search
    user_lat, user_lon = None, None

    if isinstance(origin_location, ResolvedLocation):
        user_lat, user_lon = origin_location.lat, origin_location.lon
    elif isinstance(origin_location, dict):
        user_lat, user_lon = extract_coordinates(origin_location)

    # Fallback: try browser/home location
    if not (user_lat and user_lon):
        browser_loc = await get_browser_geolocation(runtime)
        if browser_loc:
            user_lat, user_lon = browser_loc.lat, browser_loc.lon
        else:
            home_loc = await get_user_home_location(runtime)
            if home_loc:
                user_lat, user_lon = home_loc.lat, home_loc.lon

    if not (user_lat and user_lon):
        logger.debug("destination_no_user_location", destination=destination)
        return destination

    try:
        import httpx

        # Use Google Places API (New) with API key for text search
        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "X-Goog-Api-Key": settings.google_api_key,
            "X-Goog-FieldMask": "places.displayName,places.location",
            "Content-Type": "application/json",
        }
        body = {
            "textQuery": destination,
            "maxResultCount": 1,
            "languageCode": language,  # Get place name in user's language
            "locationBias": {
                "circle": {
                    "center": {"latitude": user_lat, "longitude": user_lon},
                    "radius": 10000.0,  # 10km
                }
            },
        }

        async with httpx.AsyncClient(timeout=settings.http_timeout_places_api) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            results = response.json()

        places = results.get("places", [])
        if places:
            place = places[0]
            place_name = place.get("displayName", {}).get("text", "") or destination
            place_location = place.get("location", {})
            place_lat = place_location.get("latitude")
            place_lon = place_location.get("longitude")

            if place_lat and place_lon:
                logger.info(
                    "destination_resolved_via_places",
                    original=destination,
                    resolved_name=place_name,
                    lat=place_lat,
                    lon=place_lon,
                )
                # Return both coordinates AND display name for RouteCard
                return {
                    "latitude": place_lat,
                    "longitude": place_lon,
                    "display_name": place_name,
                }

        logger.debug("destination_places_no_results", destination=destination)

    except (ConnectionError, TimeoutError, ValueError, KeyError, OSError) as e:
        logger.warning(
            "destination_places_error",
            destination=destination,
            error=str(e),
            error_type=type(e).__name__,
        )

    return destination


# ============================================================================
# RESPONSE FORMATTING
# ============================================================================


# =============================================================================
# TRANSIT PRIORITY SCORING
# =============================================================================

# Transit vehicle type priority scores (higher = better)
# Priority: RER/Train > Metro > Tram > Bus
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

    for leg in route.get("legs", []):
        for step in leg.get("steps", []):
            transit_details = step.get("transitDetails")
            if transit_details:
                vehicle = transit_details.get("transitLine", {}).get("vehicle", {})
                vehicle_type = vehicle.get("type", "OTHER")

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
            merged_distance = current_step.get("distance_meters", 0)

            j = i + 1
            while j < len(steps):
                next_step = steps[j]
                if next_step.get("travel_mode") == "WALK" and not next_step.get("transit"):
                    merged_distance += next_step.get("distance_meters", 0)
                    j += 1
                else:
                    break

            # Create merged WALK step only if multiple were merged
            if j > i + 1:
                distance_str = (
                    f"{merged_distance / 1000:.1f} km"
                    if merged_distance >= 1000
                    else f"{merged_distance} m"
                )
                merged_step = {
                    "instruction": f"Marcher ({distance_str})",
                    "maneuver": "WALK",
                    "distance_meters": merged_distance,
                    "travel_mode": "WALK",
                    "is_condensed": True,
                    "condensed_count": j - i,
                }
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
    routes = route_data.get("routes", [])
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
    duration_str = primary_route.get("duration", "0s")
    duration_seconds = GoogleRoutesClient.parse_duration(duration_str)
    duration_minutes = duration_seconds // 60

    distance_meters = primary_route.get("distanceMeters", 0)
    distance_km = GoogleRoutesClient.meters_to_km(distance_meters)

    # Format duration for display
    duration_formatted = GoogleRoutesClient.format_duration(duration_seconds, language)

    # Get traffic duration if available
    static_duration_str = primary_route.get("staticDuration")
    duration_in_traffic_minutes = None
    traffic_conditions = None

    if static_duration_str:
        static_seconds = GoogleRoutesClient.parse_duration(static_duration_str)
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
    polyline = primary_route.get("polyline", {}).get("encodedPolyline", "")

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

    # Format steps if available (with transit details for TRANSIT mode)
    steps = []
    for leg in primary_route.get("legs", []):
        for step in leg.get("steps", []):
            nav_instruction = step.get("navigationInstruction", {})
            step_travel_mode = step.get("travelMode", "")

            step_info: dict[str, Any] = {
                "instruction": nav_instruction.get("instructions", ""),
                "maneuver": nav_instruction.get("maneuver", ""),
                "distance_meters": step.get("distanceMeters", 0),
                "travel_mode": step_travel_mode,
            }

            # Extract transit details if present (TRANSIT mode steps)
            transit_details = step.get("transitDetails")
            if transit_details:
                transit_line = transit_details.get("transitLine", {})
                stop_details = transit_details.get("stopDetails", {})
                vehicle = transit_line.get("vehicle", {})

                # Line info (prefer short name like "M1", "RER A")
                line_name = transit_line.get("nameShort") or transit_line.get("name", "")
                line_color = transit_line.get("color", "")
                line_text_color = transit_line.get("textColor", "")

                # Vehicle type (BUS, SUBWAY, RAIL, TRAM, etc.)
                vehicle_type = vehicle.get("type", "")
                vehicle_name = vehicle.get("name", {}).get("text", "")

                # Headsign (direction/terminus) - headsign is a direct string
                headsign = transit_details.get("headsign", "")

                # Stops
                departure_stop = stop_details.get("departureStop", {}).get("name", "")
                arrival_stop = stop_details.get("arrivalStop", {}).get("name", "")
                stop_count = transit_details.get("stopCount", 0)

                step_info["transit"] = {
                    "line_name": line_name,
                    "line_color": line_color,
                    "line_text_color": line_text_color,
                    "vehicle_type": vehicle_type,
                    "vehicle_name": vehicle_name,
                    "headsign": headsign,
                    "departure_stop": departure_stop,
                    "arrival_stop": arrival_stop,
                    "stop_count": stop_count,
                }

                # Build a better instruction for transit steps
                if line_name:
                    transit_instruction = f"{vehicle_type or vehicle_name} {line_name}"
                    if headsign:
                        transit_instruction += f" → {headsign}"
                    if departure_stop and arrival_stop:
                        transit_instruction += f" ({departure_stop} → {arrival_stop})"
                    if stop_count:
                        stops_label = V3Messages.get_transit_stops(language, stop_count)
                        transit_instruction += f" [{stops_label}]"
                    step_info["instruction"] = transit_instruction

            if step_info["instruction"]:
                steps.append(step_info)

    # Build Google Maps URL
    maps_url = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_display}&destination={destination_display}"
        f"&travelmode={travel_mode.value.lower()}"
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

            # Track Static Maps API call - the browser will fetch this URL automatically
            # Static Maps proxy is public (no auth) but we track here in chat context
            track_google_api_call("static_maps", "/staticmap", cached=False)

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

    # Extract toll info from travelAdvisory
    toll_info = None
    travel_advisory = primary_route.get("travelAdvisory", {})
    toll_data = travel_advisory.get("tollInfo", {})
    estimated_prices = toll_data.get("estimatedPrice", [])
    if estimated_prices:
        # Sum all toll prices (may have multiple currencies, usually just one)
        total_tolls = {}
        for price in estimated_prices:
            currency = price.get("currencyCode", "EUR")
            # Google returns units and nanos separately
            units = int(price.get("units", 0))
            nanos = int(price.get("nanos", 0))
            amount = units + (nanos / 1_000_000_000)
            if currency in total_tolls:
                total_tolls[currency] += amount
            else:
                total_tolls[currency] = amount

        if total_tolls:
            # Format toll info (prefer EUR if available)
            primary_currency = "EUR" if "EUR" in total_tolls else list(total_tolls.keys())[0]
            toll_amount = total_tolls[primary_currency]
            toll_info = {
                "amount": round(toll_amount, 2),
                "currency": primary_currency,
                "formatted": f"{toll_amount:.2f} {primary_currency}",
            }

    # Calculate ETA (estimated time of arrival) in user's timezone
    eta = None
    eta_formatted = None
    # New fields for arrival-based routing
    target_arrival_time_iso = None
    target_arrival_formatted = None
    suggested_departure_time_iso = None
    suggested_departure_formatted = None

    if duration_minutes:
        try:
            tz = ZoneInfo(user_timezone)
        except (KeyError, ValueError):
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
                suggested_departure_dt = target_arrival_dt - timedelta(minutes=duration_minutes)

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

            calculated_eta = base_time + timedelta(minutes=duration_minutes)
            eta = calculated_eta.isoformat()

            # Format ETA using centralized helper (handles today/tomorrow/date context)
            eta_formatted = format_time_with_date_context(calculated_eta, now, language)

    return {
        "success": True,
        "data": {
            "route": {
                "origin": origin_display,
                "destination": destination_display,
                "travel_mode": travel_mode.value,
                "distance_km": distance_km,
                "distance_meters": distance_meters,
                "duration_minutes": duration_minutes,
                "duration_formatted": duration_formatted,
                "duration_in_traffic_minutes": duration_in_traffic_minutes,
                "traffic_conditions": traffic_conditions,
                "polyline": polyline,
                "steps": _condense_route_steps(steps, settings.routes_max_steps) if steps else [],
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


def _create_route_registry_item(
    route_data: dict[str, Any],
    origin: str,
    destination: str,
    travel_mode: TravelMode,
) -> tuple[str, RegistryItem]:
    """
    Create a registry item for a computed route.

    Args:
        route_data: Formatted route data
        origin: Origin string
        destination: Destination string
        travel_mode: Travel mode

    Returns:
        Tuple of (item_id, RegistryItem)
    """
    route_info = route_data.get("data", {}).get("route", {})

    item_id = generate_registry_id(
        RegistryItemType.ROUTE,
        f"{origin}_{destination}_{travel_mode.value}_{datetime.now().strftime('%Y%m%d%H%M')}",
    )

    registry_item = RegistryItem(
        id=item_id,
        type=RegistryItemType.ROUTE,
        payload={
            "origin": route_info.get("origin"),
            "destination": route_info.get("destination"),
            "travel_mode": route_info.get("travel_mode"),
            "distance_km": route_info.get("distance_km"),
            "duration_minutes": route_info.get("duration_minutes"),
            "duration_formatted": route_info.get("duration_formatted"),
            "duration_in_traffic_minutes": route_info.get("duration_in_traffic_minutes"),
            "traffic_conditions": route_info.get("traffic_conditions"),
            "polyline": route_info.get("polyline"),
            "steps": route_info.get("steps"),
            "maps_url": route_info.get("maps_url"),
            "static_map_url": route_info.get("static_map_url"),
            "toll_info": route_info.get("toll_info"),
            "eta": route_info.get("eta"),
            "eta_formatted": route_info.get("eta_formatted"),
            # Arrival-based route fields
            "is_arrival_based": route_info.get("is_arrival_based", False),
            "target_arrival_time": route_info.get("target_arrival_time"),
            "target_arrival_formatted": route_info.get("target_arrival_formatted"),
            "suggested_departure_time": route_info.get("suggested_departure_time"),
            "suggested_departure_formatted": route_info.get("suggested_departure_formatted"),
        },
        meta=RegistryItemMeta(
            source="google_routes",
            domain=CONTEXT_DOMAIN_ROUTES,
            tool_name="get_route",
        ),
    )

    return item_id, registry_item


# ============================================================================
# TOOL 1: GET ROUTE
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_route",
    agent_name=AGENT_ROUTE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_route_tool(
    destination: Annotated[
        str,
        "Destination address, place name, or coordinates. Examples: 'Lyon, France', "
        "'10 rue de Rivoli, Paris', 'Tour Eiffel'",
    ],
    origin: Annotated[
        str | None,
        "Starting point. If not specified or 'auto', uses current location or home address. "
        "Examples: 'Paris', 'ma position', 'chez moi'",
    ] = None,
    travel_mode: Annotated[
        str | None,
        "Mode of transport: 'DRIVE' (car), 'WALK' (on foot), 'BICYCLE' (bike), "
        "'TRANSIT' (public transport), 'TWO_WHEELER' (motorcycle). "
        "French: 'voiture', 'à pied', 'vélo', 'transports', 'moto'. Default: DRIVE",
    ] = None,
    avoid_tolls: Annotated[
        bool,
        "Avoid toll roads. Default: False",
    ] = False,
    avoid_highways: Annotated[
        bool,
        "Avoid highways/autoroutes. Default: False",
    ] = False,
    avoid_ferries: Annotated[
        bool,
        "Avoid ferries. Default: False",
    ] = False,
    departure_time: Annotated[
        str | None,
        "Departure time in ISO 8601 format for traffic prediction. "
        "Example: '2025-01-15T08:00:00Z'. If not specified, uses current time. "
        "Mutually exclusive with arrival_time.",
    ] = None,
    arrival_time: Annotated[
        str | None,
        "Target arrival time in ISO 8601 format (when you need to BE THERE). "
        "Use this for routes to calendar events: pass the event's start_datetime. "
        "The system will calculate the suggested departure time. "
        "Mutually exclusive with departure_time.",
    ] = None,
    waypoints: Annotated[
        list[str] | None,
        "Intermediate stops (max 25). Example: ['Dijon', 'Mâcon']",
    ] = None,
    optimize_waypoints: Annotated[
        bool,
        "Reorder waypoints for optimal route. Default: False",
    ] = False,
    user_message: Annotated[
        str,
        "Original user message for context detection",
    ] = "",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get directions and travel information between two locations.

    Provides:
    - Distance in km and duration
    - Turn-by-turn navigation steps
    - Traffic conditions (when available)
    - Polyline for map display
    - Link to Google Maps
    - Suggested departure time (when arrival_time specified)

    Automatically resolves origin from:
    - Browser geolocation (current position)
    - User's home address (if configured)

    Args:
        destination: Where to go (required)
        origin: Starting point (auto-resolved if not specified)
        travel_mode: How to travel (default: car)
        avoid_tolls: Skip toll roads
        avoid_highways: Skip highways
        avoid_ferries: Skip ferries
        departure_time: When to leave (for traffic prediction)
        arrival_time: When to arrive (for calendar events - calculates departure)
        waypoints: Intermediate stops
        optimize_waypoints: Optimize stop order
        user_message: Original user query
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with route information or error

    Examples:
        - get_route(destination="Lyon") - From current location to Lyon
        - get_route(destination="Marseille", origin="Paris", travel_mode="TRANSIT")
        - get_route(destination="Nice", avoid_tolls=True, avoid_highways=True)
        - get_route(destination="10 rue X", arrival_time="2025-01-15T14:00:00Z") - Arrive by 14h
    """
    try:
        # Get user preferences (timezone, language)
        language = "fr"
        user_timezone = DEFAULT_USER_DISPLAY_TIMEZONE
        if runtime:
            try:
                tz, lang, _locale = await get_user_preferences(runtime)
                language = lang
                if tz:
                    user_timezone = tz
            except (ValueError, KeyError, RuntimeError, AttributeError):
                pass

        # Get original user message if not provided
        if not user_message and runtime:
            user_message = get_original_user_message(runtime)

        # Resolve origin
        resolved_origin, origin_error = await _resolve_origin(
            runtime, origin, user_message, language
        )

        if origin_error:
            return UnifiedToolOutput.failure(
                message=origin_error,
                error_code="origin_resolution_failed",
            )

        # Resolve destination with Places API for place names (in user's language)
        resolved_destination = await _resolve_destination(
            destination, runtime, origin_location=resolved_origin, language=language
        )

        # Check for invalid destination (null, empty, etc.)
        if resolved_destination is None:
            return UnifiedToolOutput.failure(
                message=_("Invalid or missing destination."),
                error_code="destination_invalid",
            )

        # Validate and clean waypoints
        if waypoints:
            # Filter out empty strings
            waypoints = [wp.strip() for wp in waypoints if wp and wp.strip()]
            max_waypoints = settings.routes_max_waypoints
            if len(waypoints) > max_waypoints:
                return UnifiedToolOutput.failure(
                    message=_("Maximum {max} waypoints allowed.").format(max=max_waypoints),
                    error_code="waypoints_exceeds_limit",
                )

        # Estimate distance for default travel mode selection
        # Rule: WALK if < 1km, DRIVE if >= 1km (when mode not specified)
        estimated_distance = _estimate_distance_km(resolved_origin, resolved_destination)

        # Parse travel mode (uses estimated distance for default rule)
        mode = _parse_travel_mode(travel_mode, distance_km=estimated_distance)

        # Log the travel mode decision
        if not travel_mode and estimated_distance is not None:
            logger.info(
                "route_travel_mode_auto_selected",
                mode=mode.value,
                estimated_distance_km=estimated_distance,
                rule="WALK < 1km, DRIVE >= 1km",
            )

        # Check if Google API key is configured
        if not settings.google_api_key:
            return UnifiedToolOutput.failure(
                message=_("Google Routes API is not configured."),
                error_code="api_not_configured",
            )

        # Validate mutually exclusive time parameters
        if departure_time and arrival_time:
            return UnifiedToolOutput.failure(
                message=_("departure_time and arrival_time are mutually exclusive."),
                error_code="invalid_time_parameters",
            )

        # CRITICAL: Convert arrival_time to user's local timezone with proper UTC conversion
        # When arrival_time comes from calendar events (e.g., "2026-01-27T10:30:00Z"),
        # it represents actual UTC time that must be converted to local time.
        # Example: 10:30 UTC → 11:30 Paris (not 10:30 Paris!)
        if arrival_time:
            from src.core.time_utils import format_datetime_iso

            original_arrival = arrival_time
            converted = format_datetime_iso(arrival_time, user_timezone)
            if converted and converted != original_arrival:
                arrival_time = converted
                logger.info(
                    "arrival_time_converted_to_local",
                    original=original_arrival,
                    converted=arrival_time,
                    user_timezone=user_timezone,
                )

        # For arrival_time with non-TRANSIT modes, we use it as departure_time proxy
        # to get traffic conditions for the same time period, then calculate backwards
        effective_departure_time = departure_time
        is_arrival_based = bool(arrival_time)

        if arrival_time and mode != TravelMode.TRANSIT:
            # Use arrival_time as proxy for departure_time (same time period traffic)
            effective_departure_time = arrival_time
            logger.info(
                "route_arrival_time_proxy",
                arrival_time=arrival_time,
                mode=mode.value,
                message="Using arrival_time as departure_time proxy for non-TRANSIT mode",
            )

        # Determine routing preference based on mode
        routing_pref = RoutingPreference.TRAFFIC_AWARE
        is_traffic_aware = True
        if mode in (TravelMode.WALK, TravelMode.BICYCLE):
            routing_pref = RoutingPreference.TRAFFIC_UNAWARE
            is_traffic_aware = False

        # Try to get route from cache first (skip for waypoints - too complex to cache)
        route_data = None
        from_cache = False
        if not waypoints:
            try:
                redis_client = await get_redis_cache()
                routes_cache = RoutesCache(redis_client)
                cached_data, from_cache, cached_at, cache_age = await routes_cache.get_route(
                    origin=resolved_origin,
                    destination=resolved_destination,
                    travel_mode=mode.value,
                    avoid_tolls=avoid_tolls,
                    avoid_highways=avoid_highways,
                    avoid_ferries=avoid_ferries,
                    departure_time=effective_departure_time,
                    arrival_time=arrival_time if mode == TravelMode.TRANSIT else None,
                )
                if cached_data:
                    route_data = cached_data
                    logger.info(
                        "route_from_cache",
                        cache_age_seconds=cache_age,
                        origin=str(resolved_origin)[:30],
                        destination=str(resolved_destination)[:30],
                        is_arrival_based=is_arrival_based,
                    )
            except (ConnectionError, TimeoutError, RuntimeError, OSError) as e:
                logger.warning(
                    "routes_cache_check_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )

        # If not in cache, call the API
        if route_data is None:
            client = GoogleRoutesClient(language=language)
            try:
                route_data = await client.compute_route(
                    origin=resolved_origin,
                    destination=resolved_destination,
                    travel_mode=mode,
                    routing_preference=routing_pref,
                    waypoints=waypoints,
                    optimize_waypoint_order=optimize_waypoints,
                    avoid_tolls=avoid_tolls,
                    avoid_highways=avoid_highways,
                    avoid_ferries=avoid_ferries,
                    departure_time=effective_departure_time,
                    arrival_time=arrival_time if mode == TravelMode.TRANSIT else None,
                    compute_alternative_routes=True,
                    language_code=language,
                )

                # Store in cache (only if no waypoints and successful)
                if not waypoints and route_data:
                    try:
                        redis_client = await get_redis_cache()
                        routes_cache = RoutesCache(redis_client)
                        await routes_cache.set_route(
                            origin=resolved_origin,
                            destination=resolved_destination,
                            travel_mode=mode.value,
                            data=route_data,
                            avoid_tolls=avoid_tolls,
                            avoid_highways=avoid_highways,
                            avoid_ferries=avoid_ferries,
                            departure_time=effective_departure_time,
                            arrival_time=arrival_time if mode == TravelMode.TRANSIT else None,
                            is_traffic_aware=is_traffic_aware,
                        )
                        logger.debug(
                            "route_cached",
                            origin=str(resolved_origin)[:30],
                            destination=str(resolved_destination)[:30],
                            is_arrival_based=is_arrival_based,
                            is_traffic_aware=is_traffic_aware,
                        )
                    except (ConnectionError, TimeoutError, RuntimeError, OSError) as e:
                        logger.warning(
                            "routes_cache_set_failed",
                            error=str(e),
                            error_type=type(e).__name__,
                        )

            finally:
                await client.close()

        # Format origin display string (with reverse geocoding for coordinates)
        origin_display = None
        if isinstance(resolved_origin, dict):
            # First check if address is already provided
            origin_display = resolved_origin.get("address")
            # If no address, try reverse geocoding from coordinates
            if not origin_display:
                origin_lat, origin_lon = extract_coordinates(resolved_origin)
                if origin_lat and origin_lon:
                    origin_display = await reverse_geocode(origin_lat, origin_lon, language)
            # Fallback to "Ma position" if reverse geocoding fails
            if not origin_display:
                origin_display = V3Messages.get_my_location(language)
        else:
            origin_display = str(resolved_origin)

        # Format destination display string
        if isinstance(resolved_destination, dict):
            # Use display_name from Places API resolution, fallback to original destination
            destination_display = resolved_destination.get("display_name") or destination
        else:
            destination_display = str(resolved_destination)

        # Extract coordinates for static map markers (ensures accurate origin/dest display)
        # Uses centralized extract_coordinates helper (DRY - handles lat/lon, latitude/longitude, lng)
        origin_coords: tuple[float, float] | None = None
        dest_coords: tuple[float, float] | None = None

        origin_lat, origin_lon = extract_coordinates(resolved_origin)
        if origin_lat is not None and origin_lon is not None:
            origin_coords = (float(origin_lat), float(origin_lon))

        dest_lat, dest_lon = extract_coordinates(resolved_destination)
        if dest_lat is not None and dest_lon is not None:
            dest_coords = (float(dest_lat), float(dest_lon))

        # Format response
        formatted = _format_route_response(
            route_data,
            origin_display,
            destination_display,
            mode,
            language,
            user_timezone,
            effective_departure_time,
            arrival_time_target=arrival_time,
            is_arrival_based=is_arrival_based,
            origin_coords=origin_coords,
            dest_coords=dest_coords,
        )

        if not formatted.get("success"):
            return UnifiedToolOutput.failure(
                message=formatted.get("message", _("Route calculation failed.")),
                error_code=formatted.get("error", "route_error"),
            )

        route_info = formatted.get("data", {}).get("route", {})

        # Create registry item
        item_id, registry_item = _create_route_registry_item(
            formatted,
            origin_display,
            destination_display,
            mode,
        )

        # Build summary for LLM (English for semantic pivot)
        summary = (
            f"Route from {route_info.get('origin', 'origin')} "
            f"to {route_info.get('destination', 'destination')}: "
            f"{route_info.get('distance_km', 0)} km, "
            f"{route_info.get('duration_formatted', 'N/A')} "
            f"({mode.value.lower()})."
        )

        # Add arrival-based info to summary (English for semantic pivot)
        # IMPORTANT: Use ISO times (language-neutral) to prevent localization leaking into LLM
        if route_info.get("is_arrival_based") and route_info.get("suggested_departure_time"):
            # Use ISO format times for semantic pivot (language-neutral)
            target_arrival_iso = route_info.get("target_arrival_time", "")
            suggested_departure_iso = route_info.get("suggested_departure_time", "")
            duration_min = route_info.get("duration_minutes", 0)
            summary += (
                f" ARRIVAL-BASED ROUTE: Target arrival is {target_arrival_iso}. "
                f"User must depart at {suggested_departure_iso} "
                f"(arrival minus {duration_min} min travel time). "
                f"Use these exact times - do not recalculate."
            )

        if route_info.get("traffic_conditions"):
            traffic_labels = {
                "NORMAL": "normal",
                "LIGHT": "light",
                "MODERATE": "moderate",
                "HEAVY": "heavy",
            }
            traffic_en = traffic_labels.get(route_info["traffic_conditions"], "")
            if traffic_en:
                summary += f" Traffic: {traffic_en}."

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={item_id: registry_item},
            structured_data={
                "route": route_info,
                "maps_url": route_info.get("maps_url"),
            },
            metadata={
                "travel_mode": mode.value,
                "distance_km": route_info.get("distance_km"),
                "duration_minutes": route_info.get("duration_minutes"),
            },
        )

    except (ValueError, KeyError, ConnectionError, TimeoutError, RuntimeError, OSError) as e:
        return handle_tool_exception(e, "get_route_tool", {"destination": destination})


# ============================================================================
# TOOL 2: GET ROUTE MATRIX
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="get_route_matrix",
    agent_name=AGENT_ROUTE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def get_route_matrix_tool(
    origins: Annotated[
        list[str],
        "List of starting points (max 25). Examples: ['Paris', 'Lyon', 'Marseille']",
    ],
    destinations: Annotated[
        list[str],
        "List of destinations (max 25). Examples: ['Nice', 'Bordeaux']",
    ],
    travel_mode: Annotated[
        str | None,
        "Mode of transport: 'DRIVE', 'WALK', 'BICYCLE', 'TRANSIT'. Default: DRIVE",
    ] = None,
    departure_time: Annotated[
        str | None,
        "Departure time in ISO 8601 format for traffic prediction.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Compute distance and duration matrix between multiple origins and destinations.

    Useful for:
    - Finding the nearest location from multiple options
    - Optimizing delivery or visit routes
    - Comparing travel times from different starting points

    Note: Maximum elements = routes_max_matrix_elements (default 625 = 25x25).

    Args:
        origins: List of starting points (addresses or place names)
        destinations: List of end points (addresses or place names)
        travel_mode: How to travel (default: car)
        departure_time: When to leave (for traffic prediction)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with matrix data or error

    Examples:
        - get_route_matrix(origins=["Paris"], destinations=["Lyon", "Marseille", "Bordeaux"])
        - get_route_matrix(origins=["Entrepôt A", "Entrepôt B"], destinations=["Client 1", "Client 2", "Client 3"])
    """
    try:
        # Validate inputs
        if not origins or not destinations:
            return UnifiedToolOutput.failure(
                message=_("Origins and destinations are required."),
                error_code="validation_error",
            )

        max_elements = settings.routes_max_matrix_elements
        if len(origins) * len(destinations) > max_elements:
            return UnifiedToolOutput.failure(
                message=_("Matrix limited to {max} elements.").format(max=max_elements),
                error_code="matrix_too_large",
            )

        # Get user preferences
        language = "fr"
        if runtime:
            try:
                _tz, lang, _locale = await get_user_preferences(runtime)
                language = lang
            except (ValueError, KeyError, RuntimeError, AttributeError):
                pass

        # Parse travel mode
        mode = _parse_travel_mode(travel_mode)

        # Check API key
        if not settings.google_api_key:
            return UnifiedToolOutput.failure(
                message=_("Google Routes API is not configured."),
                error_code="api_not_configured",
            )

        routing_pref = RoutingPreference.TRAFFIC_AWARE
        if mode in (TravelMode.WALK, TravelMode.BICYCLE):
            routing_pref = RoutingPreference.TRAFFIC_UNAWARE

        # Try to get matrix from cache first
        matrix_data = None
        try:
            redis_client = await get_redis_cache()
            routes_cache = RoutesCache(redis_client)
            cached_data, from_cache, cached_at, cache_age = await routes_cache.get_matrix(
                origins=origins,
                destinations=destinations,
                travel_mode=mode.value,
            )
            if cached_data:
                matrix_data = cached_data
                logger.info(
                    "route_matrix_from_cache",
                    cache_age_seconds=cache_age,
                    origins_count=len(origins),
                    destinations_count=len(destinations),
                )
        except (ConnectionError, TimeoutError, RuntimeError, OSError) as e:
            logger.warning(
                "routes_matrix_cache_check_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

        # If not in cache, call the API
        if matrix_data is None:
            client = GoogleRoutesClient(language=language)
            try:
                matrix_data = await client.compute_route_matrix(
                    origins=origins,
                    destinations=destinations,
                    travel_mode=mode,
                    routing_preference=routing_pref,
                    departure_time=departure_time,
                )

                # Store in cache
                if matrix_data:
                    try:
                        redis_client = await get_redis_cache()
                        routes_cache = RoutesCache(redis_client)
                        await routes_cache.set_matrix(
                            origins=origins,
                            destinations=destinations,
                            travel_mode=mode.value,
                            data=matrix_data,
                        )
                        logger.debug(
                            "route_matrix_cached",
                            origins_count=len(origins),
                            destinations_count=len(destinations),
                        )
                    except (ConnectionError, TimeoutError, RuntimeError, OSError) as e:
                        logger.warning(
                            "routes_matrix_cache_set_failed",
                            error=str(e),
                            error_type=type(e).__name__,
                        )

            finally:
                await client.close()

        # Parse matrix results
        elements = matrix_data.get("elements", [])

        # Build matrix structure
        matrix_results: list[list[dict[str, Any]]] = []
        for _origin in origins:
            matrix_results.append([{} for _dest in destinations])

        for element in elements:
            origin_idx = element.get("originIndex", 0)
            dest_idx = element.get("destinationIndex", 0)

            duration_str = element.get("duration", "0s")
            duration_seconds = GoogleRoutesClient.parse_duration(duration_str)
            distance_meters = element.get("distanceMeters", 0)

            matrix_results[origin_idx][dest_idx] = {
                "distance_km": GoogleRoutesClient.meters_to_km(distance_meters),
                "duration_minutes": duration_seconds // 60,
                "duration_formatted": GoogleRoutesClient.format_duration(
                    duration_seconds, language
                ),
                "condition": element.get("condition", "OK"),
            }

        # Find optimal (shortest total distance) if multiple destinations
        optimal_order = None
        if len(origins) == 1 and len(destinations) > 1:
            # Single origin, multiple destinations - find nearest
            sorted_dests = sorted(
                enumerate(matrix_results[0]),
                key=lambda x: x[1].get("distance_km", float("inf")),
            )
            optimal_order = [idx for idx, _ in sorted_dests]

        # Build summary (English for semantic pivot)
        total_combinations = len(origins) * len(destinations)
        summary = (
            f"Distance matrix: {len(origins)} origin(s) x {len(destinations)} destination(s) "
            f"= {total_combinations} combination(s). Mode: {mode.value.lower()}."
        )

        if optimal_order and len(destinations) > 1:
            nearest = destinations[optimal_order[0]]
            nearest_dist = matrix_results[0][optimal_order[0]].get("distance_km", 0)
            summary += f" Nearest: {nearest} ({nearest_dist} km)."

        return UnifiedToolOutput.data_success(
            message=summary,
            structured_data={
                "matrix": matrix_results,
                "origins": origins,
                "destinations": destinations,
                "optimal_order": optimal_order,
                "travel_mode": mode.value,
            },
            metadata={
                "origins_count": len(origins),
                "destinations_count": len(destinations),
                "travel_mode": mode.value,
            },
        )

    except (ValueError, KeyError, ConnectionError, TimeoutError, RuntimeError, OSError) as e:
        return handle_tool_exception(
            e, "get_route_matrix_tool", {"origins": origins, "destinations": destinations}
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "RouteItem",
    "get_route_matrix_tool",
    "get_route_tool",
    "should_trigger_hitl",
]
