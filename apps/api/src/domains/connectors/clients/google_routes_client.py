"""
Google Routes API client with API Key authentication.

Provides access to Google Routes API for directions and route calculations.
Uses global API key (GOOGLE_API_KEY) - no per-user OAuth required.

API Reference:
- https://developers.google.com/maps/documentation/routes/overview
- https://developers.google.com/maps/documentation/routes/compute_route_directions

Authentication:
- API Key via X-Goog-Api-Key header
- Global key shared across all users (not per-user OAuth)

Features:
- Route computation with traffic awareness
- Route matrix for multi-point optimization
- Multiple travel modes (DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER)
- Route modifiers (avoid tolls, highways, ferries)
- Polyline encoding for map display
"""

import json
from enum import Enum
from typing import Any
from uuid import UUID

import httpx
import structlog
from fastapi import HTTPException
from fastapi import status as http_status

from src.core.config import settings
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class TravelMode(str, Enum):
    """Travel modes supported by Google Routes API."""

    DRIVE = "DRIVE"
    WALK = "WALK"
    BICYCLE = "BICYCLE"
    TRANSIT = "TRANSIT"
    TWO_WHEELER = "TWO_WHEELER"


class RoutingPreference(str, Enum):
    """Routing preferences for traffic-aware routing."""

    TRAFFIC_UNAWARE = "TRAFFIC_UNAWARE"
    TRAFFIC_AWARE = "TRAFFIC_AWARE"
    TRAFFIC_AWARE_OPTIMAL = "TRAFFIC_AWARE_OPTIMAL"


class TrafficCondition(str, Enum):
    """Traffic condition levels."""

    TRAFFIC_MODEL_UNSPECIFIED = "TRAFFIC_MODEL_UNSPECIFIED"
    BEST_GUESS = "BEST_GUESS"
    PESSIMISTIC = "PESSIMISTIC"
    OPTIMISTIC = "OPTIMISTIC"


# =============================================================================
# FIELD MASKS
# =============================================================================

# Default field mask for compute_route - includes commonly needed fields
DEFAULT_ROUTE_FIELD_MASK = ",".join(
    [
        "routes.duration",
        "routes.distanceMeters",
        "routes.polyline.encodedPolyline",
        "routes.legs.duration",
        "routes.legs.distanceMeters",
        "routes.legs.startLocation",
        "routes.legs.endLocation",
        "routes.legs.steps.navigationInstruction",
        "routes.legs.steps.distanceMeters",
        "routes.legs.steps.staticDuration",
        "routes.travelAdvisory",
        "routes.routeLabels",
    ]
)

# Transit-specific fields for TRANSIT mode
# Includes line info (name, color, vehicle type), stops, headsign
TRANSIT_ROUTE_FIELD_MASK = ",".join(
    [
        DEFAULT_ROUTE_FIELD_MASK,
        # Transit line details
        "routes.legs.steps.transitDetails.stopDetails.departureStop.name",
        "routes.legs.steps.transitDetails.stopDetails.arrivalStop.name",
        "routes.legs.steps.transitDetails.transitLine.name",
        "routes.legs.steps.transitDetails.transitLine.nameShort",
        "routes.legs.steps.transitDetails.transitLine.color",
        "routes.legs.steps.transitDetails.transitLine.textColor",
        "routes.legs.steps.transitDetails.transitLine.vehicle.name.text",
        "routes.legs.steps.transitDetails.transitLine.vehicle.type",
        "routes.legs.steps.transitDetails.headsign",
        "routes.legs.steps.transitDetails.stopCount",
        # Travel mode for each step (WALK, TRANSIT, etc.)
        "routes.legs.steps.travelMode",
    ]
)

# Extended field mask including traffic and toll info
EXTENDED_ROUTE_FIELD_MASK = ",".join(
    [
        DEFAULT_ROUTE_FIELD_MASK,
        "routes.staticDuration",
        "routes.legs.travelAdvisory",
        "routes.legs.steps.travelAdvisory",
        # Toll info (requires extraComputations: TOLLS)
        "routes.travelAdvisory.tollInfo.estimatedPrice",
    ]
)

# Matrix field mask
MATRIX_FIELD_MASK = ",".join(
    [
        "originIndex",
        "destinationIndex",
        "status",
        "distanceMeters",
        "duration",
        "condition",
    ]
)


# =============================================================================
# TIMESTAMP NORMALIZATION
# =============================================================================


def _normalize_departure_time(departure_time: str | None) -> str | None:
    """
    Normalize departure_time to RFC3339/ISO8601 format required by Google Routes API.

    Google Routes API requires timestamps in RFC3339 format with timezone:
    - "2024-01-15T08:00:00Z" (UTC)
    - "2024-01-15T08:00:00+01:00" (with offset)

    Common LLM-generated formats that need normalization:
    - "2024-01-15T08:00:00" (missing timezone) → add 'Z'
    - "2024-01-15 08:00:00" (space instead of T) → fix format
    - "tomorrow at 8am" (natural language) → skip (let API fail gracefully)

    Args:
        departure_time: Timestamp string or None

    Returns:
        Normalized timestamp string or None
    """
    if not departure_time:
        return None

    # Already has timezone indicator
    if departure_time.endswith("Z") or "+" in departure_time or departure_time.count("-") >= 3:
        # Check for offset format like +01:00 or -05:00
        if "+" in departure_time or (departure_time.count("-") >= 3 and "T" in departure_time):
            return departure_time

    # Replace space with T if needed (common LLM format)
    if " " in departure_time and "T" not in departure_time:
        departure_time = departure_time.replace(" ", "T", 1)

    # Add Z suffix if missing timezone
    if "T" in departure_time and not departure_time.endswith("Z"):
        # Check it looks like ISO format (has time component)
        parts = departure_time.split("T")
        if len(parts) == 2 and ":" in parts[1]:
            departure_time = departure_time + "Z"

    return departure_time


# =============================================================================
# CLIENT
# =============================================================================


class GoogleRoutesClient:
    """
    Client for Google Routes API with API Key authentication.

    Uses global GOOGLE_API_KEY (shared across all users, not per-user OAuth).

    Provides access to:
    - Route computation (A to B directions)
    - Route matrix (N origins to M destinations)
    - Traffic-aware routing
    - Multiple travel modes

    Example:
        >>> client = GoogleRoutesClient(language="fr")
        >>> route = await client.compute_route(
        ...     origin="Paris, France",
        ...     destination="Lyon, France",
        ...     travel_mode=TravelMode.DRIVE
        ... )
        >>> print(f"Distance: {route['routes'][0]['distanceMeters']} meters")
    """

    connector_type = ConnectorType.GOOGLE_ROUTES
    api_base_url = "https://routes.googleapis.com"

    def __init__(
        self,
        language: str = "fr",
        user_id: UUID | None = None,
    ) -> None:
        """
        Initialize Google Routes client.

        Args:
            language: Default language for results (default: fr)
            user_id: Optional user ID for logging (not used for auth)
        """
        self.language = language
        self.user_id = user_id
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client."""
        if self._client is None or self._client.is_closed:
            # Use configurable timeout from settings (default: 30s total, 10s connect)
            timeout_total = settings.http_timeout_routes_api
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_total, connect=10.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_headers(self, field_mask: str = DEFAULT_ROUTE_FIELD_MASK) -> dict[str, str]:
        """
        Get headers for Routes API request.

        Args:
            field_mask: Fields to return in response

        Returns:
            Headers dict with API key and field mask
        """
        if not settings.google_api_key:
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google API key not configured (GOOGLE_API_KEY)",
            )

        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_api_key,
            "X-Goog-FieldMask": field_mask,
        }

    def _build_waypoint(self, location: str | dict[str, Any]) -> dict[str, Any]:
        """
        Build a waypoint object from a location string or dict.

        Args:
            location: Address string or dict with lat/lon

        Returns:
            Waypoint dict for Routes API
        """
        if isinstance(location, str):
            return {"address": location}
        elif isinstance(location, dict):
            if "lat" in location and "lon" in location:
                return {
                    "location": {
                        "latLng": {
                            "latitude": location["lat"],
                            "longitude": location["lon"],
                        }
                    }
                }
            elif "latitude" in location and "longitude" in location:
                return {
                    "location": {
                        "latLng": {
                            "latitude": location["latitude"],
                            "longitude": location["longitude"],
                        }
                    }
                }
            elif "address" in location:
                return {"address": location["address"]}
        raise ValueError(f"Invalid location format: {location}")

    # =========================================================================
    # COMPUTE ROUTE
    # =========================================================================

    async def compute_route(
        self,
        origin: str | dict[str, Any],
        destination: str | dict[str, Any],
        travel_mode: TravelMode = TravelMode.DRIVE,
        routing_preference: RoutingPreference = RoutingPreference.TRAFFIC_AWARE,
        waypoints: list[str | dict[str, Any]] | None = None,
        optimize_waypoint_order: bool = False,
        avoid_tolls: bool = False,
        avoid_highways: bool = False,
        avoid_ferries: bool = False,
        departure_time: str | None = None,
        arrival_time: str | None = None,
        compute_alternative_routes: bool = False,
        language_code: str | None = None,
        units: str = "METRIC",
    ) -> dict[str, Any]:
        """
        Compute a route between origin and destination.

        Args:
            origin: Starting point (address string or lat/lon dict)
            destination: End point (address string or lat/lon dict)
            travel_mode: Mode of transport (DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER)
            routing_preference: Traffic awareness level
            waypoints: Optional intermediate points (max 25)
            optimize_waypoint_order: Reorder waypoints for optimal route
            avoid_tolls: Avoid toll roads
            avoid_highways: Avoid highways
            avoid_ferries: Avoid ferries
            departure_time: ISO 8601 timestamp for traffic prediction (mutually exclusive with arrival_time)
            arrival_time: ISO 8601 timestamp for target arrival (TRANSIT only, mutually exclusive with departure_time)
            compute_alternative_routes: Return alternative routes
            language_code: Language for instructions (default: self.language)
            units: METRIC or IMPERIAL

        Returns:
            Dict with routes array containing:
            - distanceMeters: Total distance
            - duration: Total time (e.g., "3600s")
            - polyline.encodedPolyline: Encoded path for map display
            - legs: Route segments with steps
            - travelAdvisory: Traffic/toll information

        Raises:
            HTTPException: On API errors
            ValueError: If both departure_time and arrival_time are provided

        Example:
            >>> route = await client.compute_route(
            ...     origin="48.8584,2.2945",  # Eiffel Tower
            ...     destination="Lyon, France",
            ...     travel_mode=TravelMode.DRIVE,
            ...     avoid_tolls=True
            ... )
        """
        # Validate mutually exclusive time parameters
        if departure_time and arrival_time:
            raise ValueError("departure_time and arrival_time are mutually exclusive")

        client = await self._get_client()

        # Build request body
        # Note: origin/destination use direct waypoint content (no "waypoint" wrapper)
        # but intermediates DO use the "waypoint" wrapper per Google Routes API spec
        body: dict[str, Any] = {
            "origin": self._build_waypoint(origin),
            "destination": self._build_waypoint(destination),
            "travelMode": travel_mode.value,
            "languageCode": language_code or self.language,
            "units": units,
        }

        # routingPreference is ONLY supported for DRIVE and TWO_WHEELER modes
        # NOT supported for: WALK, BICYCLE, TRANSIT
        # https://developers.google.com/maps/documentation/routes/reference/rest/v2/TopLevel/computeRoutes
        if travel_mode in (TravelMode.DRIVE, TravelMode.TWO_WHEELER):
            body["routingPreference"] = routing_preference.value

        # Add waypoints if provided (intermediates use waypoint wrapper)
        if waypoints:
            body["intermediates"] = [self._build_waypoint(wp) for wp in waypoints]
            if optimize_waypoint_order:
                body["optimizeWaypointOrder"] = True

        # Add route modifiers
        route_modifiers: dict[str, Any] = {}
        if avoid_tolls:
            route_modifiers["avoidTolls"] = True
        if avoid_highways:
            route_modifiers["avoidHighways"] = True
        if avoid_ferries:
            route_modifiers["avoidFerries"] = True
        if route_modifiers:
            body["routeModifiers"] = route_modifiers

        # Handle time parameters (departure_time vs arrival_time)
        # Note: arrivalTime is ONLY supported for TRANSIT mode by Google Routes API
        if arrival_time and travel_mode == TravelMode.TRANSIT:
            # TRANSIT mode: use native arrivalTime support
            normalized_arrival = _normalize_departure_time(arrival_time)
            if normalized_arrival:
                body["arrivalTime"] = normalized_arrival
                logger.debug(
                    "routes_using_arrival_time",
                    arrival_time=normalized_arrival,
                    travel_mode=travel_mode.value,
                )
        elif departure_time:
            # Standard departure time for traffic prediction
            normalized_time = _normalize_departure_time(departure_time)
            if normalized_time:
                body["departureTime"] = normalized_time

        # Request alternative routes
        if compute_alternative_routes:
            body["computeAlternativeRoutes"] = True

        # Request toll info for DRIVE/TWO_WHEELER modes (requires extraComputations)
        if travel_mode in (TravelMode.DRIVE, TravelMode.TWO_WHEELER) and not avoid_tolls:
            body["extraComputations"] = ["TOLLS"]

        # Use appropriate field mask based on travel mode
        # TRANSIT mode needs additional fields for line/stop info
        if travel_mode == TravelMode.TRANSIT:
            field_mask = TRANSIT_ROUTE_FIELD_MASK
        else:
            field_mask = EXTENDED_ROUTE_FIELD_MASK
        headers = self._get_headers(field_mask)

        url = f"{self.api_base_url}/directions/v2:computeRoutes"

        try:
            logger.debug(
                "routes_api_request",
                user_id=str(self.user_id) if self.user_id else "global",
                origin=str(origin)[:50],
                destination=str(destination)[:50],
                travel_mode=travel_mode.value,
            )

            response = await client.post(url, headers=headers, json=body)

            if response.status_code >= 400:
                error_detail = response.text
                logger.error(
                    "routes_api_error",
                    user_id=str(self.user_id) if self.user_id else "global",
                    status_code=response.status_code,
                    error=error_detail[:500],
                    origin=str(origin)[:50],
                    destination=str(destination)[:50],
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Google Routes API error: {error_detail}",
                )

            data = response.json()

            # Track API call (always non-cached for Routes API)
            track_google_api_call("routes", "/directions/v2:computeRoutes", cached=False)

            # Check for empty routes (no route found)
            if not data.get("routes"):
                logger.warning(
                    "routes_api_no_route",
                    user_id=str(self.user_id) if self.user_id else "global",
                    origin=str(origin)[:50],
                    destination=str(destination)[:50],
                    travel_mode=travel_mode.value,
                )
                return {"routes": [], "error": "No route found"}

            logger.info(
                "routes_api_success",
                user_id=str(self.user_id) if self.user_id else "global",
                routes_count=len(data.get("routes", [])),
                distance_meters=(
                    data["routes"][0].get("distanceMeters") if data.get("routes") else None
                ),
            )

            return data

        except httpx.RequestError as e:
            logger.error(
                "routes_api_request_error",
                user_id=str(self.user_id) if self.user_id else "global",
                error=str(e),
                origin=str(origin)[:50],
                destination=str(destination)[:50],
            )
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Google Routes API unavailable: {e!s}",
            ) from e

    # =========================================================================
    # COMPUTE ROUTE MATRIX
    # =========================================================================

    async def compute_route_matrix(
        self,
        origins: list[str | dict[str, Any]],
        destinations: list[str | dict[str, Any]],
        travel_mode: TravelMode = TravelMode.DRIVE,
        routing_preference: RoutingPreference = RoutingPreference.TRAFFIC_AWARE,
        departure_time: str | None = None,
    ) -> dict[str, Any]:
        """
        Compute distance/duration matrix between multiple origins and destinations.

        Useful for:
        - Optimizing delivery routes
        - Finding nearest location among many
        - Multi-stop trip planning

        Args:
            origins: List of starting points (max 25)
            destinations: List of end points (max 25)
            travel_mode: Mode of transport
            routing_preference: Traffic awareness level
            departure_time: ISO 8601 timestamp for traffic prediction

        Returns:
            Dict with matrix of durations and distances:
            - Each element contains distanceMeters, duration, condition

        Note:
            Maximum 625 elements (25x25 matrix)

        Example:
            >>> matrix = await client.compute_route_matrix(
            ...     origins=["Paris", "Lyon"],
            ...     destinations=["Marseille", "Nice", "Bordeaux"]
            ... )
            >>> # Returns 2x3 matrix
        """
        if len(origins) * len(destinations) > 625:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Route matrix limited to 625 elements (25x25 max)",
            )

        client = await self._get_client()

        # Note: Route Matrix API uses direct waypoint content (no "waypoint" wrapper)
        body: dict[str, Any] = {
            "origins": [{"waypoint": self._build_waypoint(origin)} for origin in origins],
            "destinations": [{"waypoint": self._build_waypoint(dest)} for dest in destinations],
            "travelMode": travel_mode.value,
        }

        # routingPreference is ONLY supported for DRIVE and TWO_WHEELER modes
        if travel_mode in (TravelMode.DRIVE, TravelMode.TWO_WHEELER):
            body["routingPreference"] = routing_preference.value

        # Normalize departure time format for Google API
        normalized_time = _normalize_departure_time(departure_time)
        if normalized_time:
            body["departureTime"] = normalized_time

        headers = self._get_headers(MATRIX_FIELD_MASK)
        url = f"{self.api_base_url}/distanceMatrix/v2:computeRouteMatrix"

        try:
            logger.debug(
                "routes_matrix_api_request",
                user_id=str(self.user_id) if self.user_id else "global",
                origins_count=len(origins),
                destinations_count=len(destinations),
                travel_mode=travel_mode.value,
            )

            response = await client.post(url, headers=headers, json=body)

            if response.status_code >= 400:
                error_detail = response.text
                logger.error(
                    "routes_matrix_api_error",
                    user_id=str(self.user_id) if self.user_id else "global",
                    status_code=response.status_code,
                    error=error_detail[:500],
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Google Routes Matrix API error: {error_detail}",
                )

            # Track API call (always non-cached for Routes Matrix API)
            track_google_api_call("routes", "/distanceMatrix/v2:computeRouteMatrix", cached=False)

            # Matrix API returns streaming NDJSON - parse all results
            results = []
            for line in response.text.strip().split("\n"):
                if line.strip():
                    results.append(json.loads(line))

            logger.info(
                "routes_matrix_api_success",
                user_id=str(self.user_id) if self.user_id else "global",
                results_count=len(results),
            )

            return {"elements": results}

        except httpx.RequestError as e:
            logger.error(
                "routes_matrix_api_request_error",
                user_id=str(self.user_id) if self.user_id else "global",
                error=str(e),
            )
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Google Routes Matrix API unavailable: {e!s}",
            ) from e

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    @staticmethod
    def parse_duration(duration_str: str) -> int:
        """
        Parse duration string (e.g., "3600s") to seconds.

        Args:
            duration_str: Duration string from Routes API

        Returns:
            Duration in seconds
        """
        if duration_str.endswith("s"):
            return int(float(duration_str[:-1]))
        return int(float(duration_str))

    @staticmethod
    def format_duration(seconds: int, language: str = "fr") -> str:
        """
        Format duration in human-readable form.

        Args:
            seconds: Duration in seconds
            language: Language code

        Returns:
            Human-readable duration
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if language == "fr":
            if hours > 0:
                return f"{hours}h {minutes}min"
            return f"{minutes} min"
        else:
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes} min"

    @staticmethod
    def meters_to_km(meters: int) -> float:
        """Convert meters to kilometers."""
        return round(meters / 1000, 1)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "GoogleRoutesClient",
    "TravelMode",
    "RoutingPreference",
    "TrafficCondition",
    "DEFAULT_ROUTE_FIELD_MASK",
    "EXTENDED_ROUTE_FIELD_MASK",
    "MATRIX_FIELD_MASK",
]
