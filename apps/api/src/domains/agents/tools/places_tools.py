"""
LangChain v1 tools for Google Places operations.

LOT 10: Google Places API integration for location search.

Note: Google Places uses global API Key authentication (GOOGLE_API_KEY from settings).
This follows the ConnectorTool pattern with uses_global_api_key=True flag.
Users enable the connector via simple toggle (no OAuth flow required).

API Reference:
- https://developers.google.com/maps/documentation/places/web-service/overview

Features:
- Text search for places
- Nearby search with radius
- Place details retrieval

Data Registry Integration:
    Places results are registered in ContextTypeRegistry to enable:
    - Contextual references ("the restaurant", "that place near me")
    - Data persistence for response_node
    - Cross-domain queries with LocalQueryEngine
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel

from src.core.config import get_settings, settings
from src.core.constants import (
    PLACE_CAROUSEL_ENABLED,
    PLACES_MAX_GALLERY_PHOTOS,
    PLACES_MIN_RATING_MAX,
    PLACES_MIN_RATING_MIN,
    PLACES_VALID_PRICE_LEVELS,
)
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import (
    AGENT_PLACE,
    CONTEXT_DOMAIN_LOCATION,
    CONTEXT_DOMAIN_PLACES,
)
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.validation_helpers import validate_positive_int_or_default
from src.domains.agents.utils.distance import calculate_distance_sync, circle_to_viewport
from src.domains.agents.utils.i18n_location import DistanceSource, get_price_level
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.connectors.clients.google_geocoding_helpers import forward_geocode
from src.domains.connectors.clients.google_places_client import GooglePlacesClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA REGISTRY INTEGRATION
# ============================================================================


class PlaceItem(BaseModel):
    """Schema for Google Places data in context registry."""

    id: str  # Google Place ID
    name: str  # Place name
    address: str = ""  # Formatted address
    rating: float | None = None  # Rating (1-5)
    types: list[str] = []  # Place types (restaurant, cafe, etc.)
    google_maps_url: str = ""  # Google Maps URL


# Register Places context type for Data Registry support
# This enables contextual references like "the restaurant", "that place"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_PLACES,
        agent_name=AGENT_PLACE,
        item_schema=PlaceItem,
        primary_id_field="id",
        display_name_field="name",
        reference_fields=["name", "address", "types"],
        icon="📍",
    )
)


# =============================================================================
# PLACE FORMATTING
# =============================================================================
# Distance calculation is delegated to src.domains.agents.utils.distance
# which provides an extensible architecture for future Google Routes API
# =============================================================================


def _format_place(
    place: dict[str, Any],
    center_lat: float | None = None,
    center_lon: float | None = None,
    distance_source: str | None = None,
    language: str = settings.default_language,
) -> dict[str, Any]:
    """
    Format a place for consistent output.

    Args:
        place: Raw place data from Google Places API
        center_lat: Optional center latitude for distance calculation
        center_lon: Optional center longitude for distance calculation
        distance_source: Source of center coordinates ("browser", "home", or None)
        language: Language for distance reference text

    Returns:
        Formatted place dict with optional distance fields
    """
    display_name = place.get("displayName", {})
    location = place.get("location", {})
    hours = place.get("currentOpeningHours", {})

    place_id = place.get("id")
    place_lat = location.get("latitude")
    place_lon = location.get("longitude")

    formatted = {
        "id": place_id,
        "place_id": place_id,  # Alias for planner compatibility
        "name": display_name.get("text", "Unknown"),
        "address": place.get("formattedAddress", ""),
        "location": {
            "lat": place_lat,
            "lon": place_lon,
        },
        "types": place.get("types", []),
        "google_maps_url": place.get("googleMapsUri"),
    }

    # Calculate distance from center point if provided AND source is known
    if center_lat is not None and center_lon is not None and distance_source is not None:
        if place_lat is not None and place_lon is not None:
            # Use extensible distance calculation from distance module
            distance_result = calculate_distance_sync(
                origin_lat=center_lat,
                origin_lon=center_lon,
                dest_lat=place_lat,
                dest_lon=place_lon,
                source=distance_source,
                language=language,
            )
            # Merge distance fields into formatted place
            formatted.update(distance_result.to_dict())
        else:
            # Place has no coordinates - log warning and skip distance
            logger.warning(
                "place_missing_coordinates_for_distance",
                place_id=place_id,
                place_name=formatted.get("name"),
                has_location=bool(location),
            )

    # Optional fields
    if place.get("rating"):
        formatted["rating"] = place.get("rating")
        formatted["rating_count"] = place.get("userRatingCount", 0)

    if place.get("priceLevel"):
        # Use i18n for price level translation
        formatted["price_level"] = get_price_level(place.get("priceLevel"), language)

    if place.get("nationalPhoneNumber"):
        formatted["phone"] = place.get("nationalPhoneNumber")

    if place.get("websiteUri"):
        formatted["website"] = place.get("websiteUri")

    if hours.get("openNow") is not None:
        formatted["open_now"] = hours.get("openNow")

    # Opening hours (weekday descriptions)
    if hours.get("weekdayDescriptions"):
        formatted["opening_hours"] = hours.get("weekdayDescriptions")

    # Editorial summary / description
    summary = place.get("editorialSummary", {})
    if summary.get("text"):
        formatted["description"] = summary.get("text")

    # Photos (resource names + proxy URL for first photo + gallery URLs)
    photos = place.get("photos", [])
    if photos:
        photo_names = [p.get("name") for p in photos if p.get("name")]
        if photo_names:
            # First photo for card thumbnail
            formatted["photo_url"] = f"/api/v1/connectors/google-places/photo/{photo_names[0]}"
            # Track the thumbnail photo API call
            track_google_api_call("places", "/{photo}/media", cached=False)

            # Carousel photos (only if enabled via PLACE_CAROUSEL_ENABLED env var)
            # When disabled: 1 photo per place = accurate billing
            # When enabled: N photos per place but carousel photos are NOT tracked for billing
            if PLACE_CAROUSEL_ENABLED:
                formatted["photo_urls"] = [
                    f"/api/v1/connectors/google-places/photo/{name}"
                    for name in photo_names[:PLACES_MAX_GALLERY_PHOTOS]
                ]
            else:
                # Single photo mode: photo_urls contains only the thumbnail
                formatted["photo_urls"] = [formatted["photo_url"]]

    # Reviews (up to 5 most recent, sorted by publishTime)
    reviews = place.get("reviews", [])
    if reviews:
        sorted_reviews = sorted(
            reviews,
            key=lambda r: r.get("publishTime", ""),
            reverse=True,
        )
        formatted["reviews"] = [
            {
                "rating": r.get("rating"),
                "text": (
                    r.get("text", {}).get("text", "")[:200]
                    if isinstance(r.get("text"), dict)
                    else str(r.get("text", ""))[:200]
                ),
                "relative_time": r.get("relativePublishTimeDescription"),
                "author_name": (
                    r.get("authorAttribution", {}).get("displayName", "")
                    if isinstance(r.get("authorAttribution"), dict)
                    else ""
                ),
            }
            for r in sorted_reviews[:5]
        ]

    return formatted


# ============================================================================
# TOOL 1: UNIFIED SEARCH PLACES (Text Search + Nearby Search combined)
# ============================================================================


class SearchPlacesTool(ToolOutputMixin, ConnectorTool[GooglePlacesClient]):
    """
    Unified search places tool using ConnectorTool architecture with global API Key.

    Combines Text Search and Nearby Search into a single intelligent tool:
    - Text Search: Used when `query` is provided (semantic search)
    - Nearby Search: Used when only `place_type` is provided (proximity search)

    Location resolution is automatic based on:
    - Browser geolocation (if available)
    - Home address from settings (if configured)
    - Explicit coordinates (if provided)

    Benefits:
    - Single tool for all place searches (simpler for planner)
    - Global API Key authentication (no OAuth flow needed)
    - Distributed rate limiting
    - Intelligent location resolution
    """

    connector_type = ConnectorType.GOOGLE_PLACES
    client_class = GooglePlacesClient
    registry_enabled = True  # Enable Data Registry mode
    uses_global_api_key = True  # Uses global GOOGLE_API_KEY instead of OAuth

    def __init__(self) -> None:
        """Initialize search places tool."""
        super().__init__(tool_name="get_places_tool", operation="search")

    async def execute_api_call(
        self,
        client: GooglePlacesClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute search places API call - unified business logic.

        Chooses between Text Search and Nearby Search based on parameters:
        - If `query` provided: Use Text Search API with location bias
        - If only `place_type` provided: Use Nearby Search API with center point
        """
        from src.domains.agents.tools.runtime_helpers import (
            get_browser_geolocation,
            get_original_user_message,
            get_user_home_location,
            get_user_language_safe,
            resolve_location,
        )

        settings = get_settings()

        # Extract parameters
        query: str = kwargs.get("query", "") or ""
        location: str | None = kwargs.get("location") or None
        place_type: str | None = kwargs.get("place_type") or None

        # Clean location: replace newlines with ", " for Google Places API compatibility
        # Addresses from contacts often have \n for frontend display
        if location:
            location = location.replace("\n", ", ").replace("  ", " ").strip()
        open_now: bool = kwargs.get("open_now", False)
        min_rating: float | None = kwargs.get("min_rating")
        price_levels: list[str] | None = kwargs.get("price_levels")
        force_refresh: bool = kwargs.get("force_refresh", False)

        # Normalize min_rating: 0 means "no filter" (LLM often sends 0 as default)
        if min_rating is not None and min_rating == 0:
            min_rating = None

        # Validate min_rating range (Google Places API constraint)
        if min_rating is not None:
            if not (PLACES_MIN_RATING_MIN <= min_rating <= PLACES_MIN_RATING_MAX):
                raise ToolValidationError(
                    APIMessages.invalid_rating_range(PLACES_MIN_RATING_MIN, PLACES_MIN_RATING_MAX),
                    field="min_rating",
                )

        # Validate price_levels values (Google Places API constraint)
        if price_levels:
            invalid_levels = [p for p in price_levels if p not in PLACES_VALID_PRICE_LEVELS]
            if invalid_levels:
                raise ToolValidationError(
                    APIMessages.invalid_price_level(
                        invalid_levels, sorted(PLACES_VALID_PRICE_LEVELS)
                    ),
                    field="price_levels",
                )

        # Extract radius_meters early for condition check (will be validated later)
        raw_radius_param = kwargs.get("radius_meters")
        has_explicit_radius = isinstance(raw_radius_param, int) and raw_radius_param > 0

        # Flag: use geocoded location for API viewport restriction
        # Enabled when location + radius_meters: precise geographic search with viewport
        # Without this, location is appended to query text (semantic search = imprecise)
        needs_geocoded_viewport = location is not None and has_explicit_radius
        geocode_failed = False  # Track if geocode failed

        # Geocoded center for viewport restriction (when location + radius_meters)
        geocoded_lat: float | None = None
        geocoded_lon: float | None = None

        if needs_geocoded_viewport and location:
            # Geocode the location to get center for viewport restriction
            geocode_result = await forward_geocode(location, language="fr")
            if geocode_result:
                geocoded_lat, geocoded_lon, _, _ = geocode_result
                logger.info(
                    "places_viewport_geocoded",
                    location=location,
                    geocoded_lat=geocoded_lat,
                    geocoded_lon=geocoded_lon,
                    radius_meters_param=raw_radius_param,
                )
            else:
                logger.warning(
                    "places_viewport_geocode_failed",
                    location=location,
                )
                # Fallback: disable geocoded viewport, use semantic search instead
                needs_geocoded_viewport = False
                geocode_failed = True

        # If explicit location provided, handle based on mode:
        # - Geocoded viewport mode: DON'T append to query (use viewport from geocoded center)
        # - Normal mode: append to query for semantic search
        if location and not needs_geocoded_viewport:
            if query:
                query = f"{query} {location}"
            else:
                query = f"{location}"
            logger.info(
                "places_search_explicit_location",
                original_query=kwargs.get("query", ""),
                location=location,
                combined_query=query[:100],
            )

        # Handle max_results with caps
        raw_max_results = kwargs.get("max_results")
        default_max_results = settings.places_tool_default_max_results
        # Cap at domain-specific limit (PLACES_TOOL_DEFAULT_MAX_RESULTS = 20 for Google API)
        api_cap = settings.places_tool_default_max_results
        max_results = validate_positive_int_or_default(raw_max_results, default=default_max_results)
        if max_results > api_cap:
            logger.warning(
                "places_search_limit_capped",
                requested_max_results=raw_max_results,
                capped_max_results=api_cap,
            )
            max_results = api_cap

        # Handle radius (search radius in meters)
        raw_radius = kwargs.get("radius_meters")
        radius_meters = validate_positive_int_or_default(
            raw_radius, default=settings.places_tool_default_radius_meters
        )

        # Get user language for i18n
        language = await get_user_language_safe(self.runtime)

        # Get user message for location phrase detection
        user_message: str = get_original_user_message(self.runtime)

        # Location for API restriction
        # When `location` parameter is provided by LLM/planner, trust it - no browser restriction
        # Browser restriction only used when no explicit location (implicit "nearby" queries)
        restriction_lat: float | None = None
        restriction_lon: float | None = None
        fallback_msg: str | None = None

        if not location:
            # No explicit location from LLM → use resolve_location for implicit queries
            resolved_location, fallback_msg = await resolve_location(
                self.runtime, user_message, language
            )
            if resolved_location:
                restriction_lat = resolved_location.lat
                restriction_lon = resolved_location.lon

        # Location for distance calculation
        # - Geocoded viewport mode with location: use geocoded center
        # - Geocoded viewport mode without location: use browser/home
        # - Normal mode: use browser/home (shows "X km from your location")
        distance_lat: float | None = None
        distance_lon: float | None = None
        distance_source: str | None = None

        if needs_geocoded_viewport and geocoded_lat is not None:
            # Geocoded viewport mode: use geocoded location for both distance and restriction
            distance_lat = geocoded_lat
            distance_lon = geocoded_lon
            distance_source = DistanceSource.SEARCH_LOCATION
            # Also use geocoded coords for restriction viewport
            restriction_lat = geocoded_lat
            restriction_lon = geocoded_lon
        else:
            # Try browser geolocation first, then home location
            browser_loc = await get_browser_geolocation(self.runtime)
            if browser_loc:
                distance_lat = browser_loc.lat
                distance_lon = browser_loc.lon
                distance_source = browser_loc.source
            else:
                home_loc = await get_user_home_location(self.runtime)
                if home_loc:
                    distance_lat = home_loc.lat
                    distance_lon = home_loc.lon
                    distance_source = home_loc.source

            # For geocoded viewport without explicit location, use browser/home as center
            if needs_geocoded_viewport and distance_lat is not None:
                restriction_lat = distance_lat
                restriction_lon = distance_lon

        logger.info(
            "places_search_location_resolved",
            has_restriction_location=restriction_lat is not None,
            has_distance_location=distance_lat is not None,
            has_explicit_location=location is not None,
            needs_geocoded_viewport=needs_geocoded_viewport,
            restriction_source=(
                "geocoded" if geocoded_lat else ("browser" if restriction_lat else None)
            ),
            distance_source=distance_source,
            query=query[:50] if query else "(none)",
            place_type=place_type,
            radius_meters=radius_meters,
        )

        # Decide which API to use based on parameters
        # Text Search: if query provided (semantic search)
        # Nearby Search: if no query but place_type provided (pure proximity)
        use_nearby_search = not query and place_type

        if use_nearby_search:
            # NEARBY SEARCH: Pure proximity search - requires user location
            # For nearby search, we MUST have a center point (user's location)
            if restriction_lat is None or restriction_lon is None:
                if fallback_msg:
                    return {
                        "success": False,
                        "error": "location_required",
                        "message": fallback_msg,
                    }
                return {
                    "success": False,
                    "error": "location_required",
                    "message": "Coordonnées GPS requises pour la recherche à proximité.",
                }

            # Parse place types
            types_list = [t.strip() for t in place_type.split(",") if t.strip()]

            result = await client.search_nearby(
                latitude=restriction_lat,
                longitude=restriction_lon,
                radius_meters=radius_meters,
                include_types=types_list if types_list else None,
                max_results=max_results,
                use_cache=not force_refresh,
            )

            # Format places with distance (use distance_lat/lon for display)
            formatted_places = [
                _format_place(
                    p,
                    center_lat=distance_lat,
                    center_lon=distance_lon,
                    distance_source=distance_source,
                    language=language,
                )
                for p in result.get("places", [])
            ]

            # Sort by distance (closest first) for nearby search
            formatted_places.sort(key=lambda x: x.get("distance_km", float("inf")))

            logger.info(
                "search_places_nearby_success",
                user_id=str(user_id),
                center_lat=restriction_lat,
                center_lon=restriction_lon,
                radius=radius_meters,
                results=len(formatted_places),
                place_types=types_list,
            )

            result_data: dict[str, Any] = {
                "places": formatted_places,
                "total": len(formatted_places),
                "search_mode": "nearby",
                "center": {"lat": restriction_lat, "lon": restriction_lon},
                "radius_meters": radius_meters,
                "filter_types": types_list if types_list else None,
            }

            # Add warning if geocoding failed for viewport restriction
            if geocode_failed:
                result_data["warning"] = (
                    f"Viewport restriction could not be applied: "
                    f"location '{location}' could not be geocoded."
                )

            return {"success": True, "data": result_data}

        else:
            # TEXT SEARCH: Semantic search with optional location restriction
            if not query:
                return {
                    "success": False,
                    "error": "query_required",
                    "message": "Requête de recherche requise.",
                }

            # Build location restriction (viewport) ONLY if we have a resolved location
            # When user specifies explicit location ("restaurants à Paris"), restriction_lat is None
            # and Google will interpret the city from the query directly
            location_restriction: dict[str, Any] | None = None
            if restriction_lat is not None and restriction_lon is not None:
                # Convert circle (center + radius) to viewport (bounding box)
                viewport = circle_to_viewport(restriction_lat, restriction_lon, radius_meters)
                location_restriction = viewport.to_dict()

            result = await client.search_text(
                query=query,
                max_results=max_results,
                include_type=place_type,
                location_restriction=location_restriction,  # None for explicit location queries
                open_now=open_now if open_now else None,
                min_rating=min_rating,
                price_levels=price_levels,
                use_cache=not force_refresh,
            )

            # Format places for output with distance calculation
            # - Geocoded viewport mode: distance from geocoded location
            # - Normal mode: distance from user's position (browser or home)
            formatted_places = [
                _format_place(
                    p,
                    center_lat=distance_lat,
                    center_lon=distance_lon,
                    distance_source=distance_source,
                    language=language,
                )
                for p in result.get("places", [])
            ]

            logger.info(
                "search_places_text_success",
                user_id=str(user_id),
                query=query,
                results=len(formatted_places),
                place_type=place_type if place_type else "none",
                has_location_restriction=location_restriction is not None,
                has_distance_location=distance_lat is not None,
                distance_source=distance_source,
                radius_meters=radius_meters,
            )

            response_data: dict[str, Any] = {
                "places": formatted_places,
                "total": len(formatted_places),
                "search_mode": "text",
                "query": query,
                "filter_type": place_type if place_type else None,
                "filter_open_now": open_now if open_now else None,
                "filter_min_rating": min_rating,
                "filter_price_levels": price_levels,
                "radius_meters": radius_meters if location_restriction else None,
            }

            # Add warning if geocoding failed for viewport restriction
            if geocode_failed:
                response_data["warning"] = (
                    f"Viewport restriction could not be applied: "
                    f"location '{location}' could not be geocoded."
                )

            return {"success": True, "data": response_data}

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format search places as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Search places request failed"),
                error_code=result.get("error"),
                metadata={"status": "error"},
            )

        data = result.get("data", {})
        places = data.get("places", [])
        query = data.get("query", "")
        search_mode = data.get("search_mode", "search")

        # Use mixin to build standardized output
        return self.build_places_output(
            places=places,
            query=query,
            operation=search_mode,
            center=data.get("center"),
            radius=data.get("radius_meters"),
        )


# Create tool instance (singleton pattern for class-based tool)
_search_places_tool_instance = SearchPlacesTool()


@connector_tool(
    name="search_places",
    agent_name=AGENT_PLACE,
    context_domain=CONTEXT_DOMAIN_PLACES,
    category="read",
)
async def search_places_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    query: Annotated[
        str,
        "Search query (e.g., 'restaurants in Paris'). Optional for proximity search.",
    ] = "",
    max_results: Annotated[
        int | None, "Maximum number of results (1-20, defaults to settings)"
    ] = None,
    place_type: Annotated[
        str,
        "Filter by type: restaurant, cafe, bar, hotel, pharmacy, hospital, bank, etc. "
        "For proximity search without query, this becomes the search criteria.",
    ] = "",
    radius_meters: Annotated[
        int | None, "Location bias/search radius in meters (defaults to 1000m)"
    ] = None,
    open_now: Annotated[bool, "Filter to only show places currently open"] = False,
    min_rating: Annotated[
        float | None,
        "Minimum rating filter (1.0-5.0). Only returns places with rating >= this value.",
    ] = None,
    price_levels: Annotated[
        list[str] | None,
        "Price level filter. Valid values: PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE, "
        "PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE. Can specify multiple.",
    ] = None,
    force_refresh: Annotated[bool, "Force refresh from API (bypass cache)"] = False,
) -> str:
    """
    Unified search for places combining text search and proximity search.

    This tool intelligently handles both scenarios:
    1. Text search (query provided): Finds places matching a description
       - "Italian restaurants in Paris"
       - "hotels near Gare de Lyon"
       - "pharmacie ouverte"
    2. Proximity search (only place_type): Finds places near user's location
       - "restaurants nearby" → place_type="restaurant"
       - "cafes around here" → place_type="cafe"

    Location resolution is automatic:
    - Browser geolocation (if shared)
    - Home address (if "chez moi", "domicile" mentioned)
    - Current location (if "nearby", "près d'ici" mentioned)

    IMPORTANT: This tool requires Google Places connector to be activated.
    Go to Settings > Connectors to authorize Google Places.

    Args:
        runtime: Tool runtime (injected)
        query: Search text. If empty, uses place_type for proximity search.
        max_results: How many results to return (default: 10, max: 20)
        place_type: Type filter (restaurant, cafe, hotel, etc.)
                   For proximity search, this is the main search criteria.
        radius_meters: Location bias radius for text search,
                      or search radius for proximity search (default: 1000m)
        open_now: Only show places that are currently open
        min_rating: Minimum rating (1.0-5.0) to filter results
        price_levels: Price level filter (list of PRICE_LEVEL_* values)
        force_refresh: Bypass cache and force fresh API call

    Returns:
        List of matching places with details

    Examples:
        - search_places(query="sushi restaurants Lyon")
        - search_places(query="pharmacie", open_now=True)
        - search_places(place_type="restaurant") # Proximity search
        - search_places(query="bar terrasse") # Text search with criteria
        - search_places(query="restaurant", min_rating=4.0) # High-rated only
        - search_places(query="café", price_levels=["PRICE_LEVEL_INEXPENSIVE"])
    """
    return await _search_places_tool_instance.execute(
        runtime=runtime,
        query=query,
        max_results=max_results,
        place_type=place_type if place_type else None,
        radius_meters=radius_meters,
        open_now=open_now,
        min_rating=min_rating,
        price_levels=price_levels,
        force_refresh=force_refresh,
    )


# ============================================================================
# TOOL 3: PLACE DETAILS (Class-based with OAuth)
# ============================================================================


class GetPlaceDetailsTool(ToolOutputMixin, ConnectorTool[GooglePlacesClient]):
    """
    Get place details tool using ConnectorTool architecture with global API Key.

    Retrieves comprehensive details for a specific place.

    MULTI-ORDINAL FIX (2026-01-01): Supports batch mode for multi-reference queries.
    - Single mode: place_id="abc123" → fetch one place
    - Batch mode: place_ids=["abc123", "def456"] → fetch multiple places in parallel
    """

    connector_type = ConnectorType.GOOGLE_PLACES
    client_class = GooglePlacesClient
    registry_enabled = True  # Enable Data Registry mode
    uses_global_api_key = True  # Uses global GOOGLE_API_KEY instead of OAuth

    def __init__(self) -> None:
        """Initialize place details tool."""
        super().__init__(tool_name="get_places_tool", operation="details")

    async def execute_api_call(
        self,
        client: GooglePlacesClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute get place details API call.

        MULTI-ORDINAL FIX (2026-01-01): Routes to single or batch mode based on parameters.
        - If place_ids is provided (non-empty list) → batch mode
        - If place_id is provided → single mode
        - Both provided → batch mode takes precedence
        """
        place_id: str | None = kwargs.get("place_id")
        place_ids: list[str] | None = kwargs.get("place_ids")
        force_refresh: bool = kwargs.get("force_refresh", False)

        # Determine mode: batch takes precedence
        if place_ids and len(place_ids) > 0:
            return await self._execute_batch(client, user_id, place_ids, force_refresh)
        elif place_id:
            return await self._execute_single(client, user_id, place_id, force_refresh)
        else:
            raise ValueError("Either place_id or place_ids must be provided")

    async def _execute_single(
        self,
        client: GooglePlacesClient,
        user_id: UUID,
        place_id: str,
        force_refresh: bool,
    ) -> dict[str, Any]:
        """Execute single place details fetch."""
        from src.domains.agents.tools.runtime_helpers import (
            get_browser_geolocation,
            get_user_home_location,
            get_user_language_safe,
        )

        # Get user language for i18n
        language = await get_user_language_safe(self.runtime)

        # Try to get user location for distance calculation (browser first, then home)
        center_lat: float | None = None
        center_lon: float | None = None
        distance_source: str | None = None

        browser_loc = await get_browser_geolocation(self.runtime)
        if browser_loc:
            center_lat = browser_loc.lat
            center_lon = browser_loc.lon
            distance_source = browser_loc.source  # "browser"
        else:
            home_loc = await get_user_home_location(self.runtime)
            if home_loc:
                center_lat = home_loc.lat
                center_lon = home_loc.lon
                distance_source = home_loc.source  # "home"

        place = await client.get_place_details(
            place_id=place_id,
            use_cache=not force_refresh,
        )

        # Format the detailed place info
        display_name = place.get("displayName", {})
        location = place.get("location", {})
        hours = place.get("regularOpeningHours", {})

        place_lat = location.get("latitude")
        place_lon = location.get("longitude")

        # BugFix 2025-11-30: Add place_id alias for consistency with _format_place
        place_id_value = place.get("id")
        details = {
            "id": place_id_value,
            "place_id": place_id_value,  # Alias for planner compatibility
            "name": display_name.get("text", "Unknown"),
            "address": place.get("formattedAddress", ""),
            "location": {
                "lat": place_lat,
                "lon": place_lon,
            },
            "types": place.get("types", []),
            "google_maps_url": place.get("googleMapsUri"),
        }

        # Calculate distance from user location if available
        if (
            center_lat is not None
            and center_lon is not None
            and distance_source is not None
            and place_lat is not None
            and place_lon is not None
        ):
            distance_result = calculate_distance_sync(
                origin_lat=center_lat,
                origin_lon=center_lon,
                dest_lat=place_lat,
                dest_lon=place_lon,
                source=distance_source,
                language=language,
            )
            details.update(distance_result.to_dict())

        # Contact info
        if place.get("nationalPhoneNumber"):
            details["phone"] = place.get("nationalPhoneNumber")
        if place.get("internationalPhoneNumber"):
            details["phone_international"] = place.get("internationalPhoneNumber")
        if place.get("websiteUri"):
            details["website"] = place.get("websiteUri")

        # Ratings
        if place.get("rating"):
            details["rating"] = place.get("rating")
            details["rating_count"] = place.get("userRatingCount", 0)

        # Price level (i18n)
        if place.get("priceLevel"):
            details["price_level"] = get_price_level(place.get("priceLevel"), language)

        # Opening hours
        if hours.get("weekdayDescriptions"):
            details["opening_hours"] = hours.get("weekdayDescriptions")

        current_hours = place.get("currentOpeningHours", {})
        if current_hours.get("openNow") is not None:
            details["open_now"] = current_hours.get("openNow")

        # Editorial summary
        summary = place.get("editorialSummary", {})
        if summary.get("text"):
            details["description"] = summary.get("text")

        # Photos (resource names + proxy URL for first photo + gallery URLs)
        photos = place.get("photos", [])
        if photos:
            photo_names = [p.get("name") for p in photos if p.get("name")]
            details["photos"] = photo_names
            # Add photo_url for first photo using proxy endpoint
            if photo_names:
                # First photo for card thumbnail
                details["photo_url"] = f"/api/v1/connectors/google-places/photo/{photo_names[0]}"
                # Track the thumbnail photo API call
                track_google_api_call("places", "/{photo}/media", cached=False)

                # Carousel photos (only if enabled via PLACE_CAROUSEL_ENABLED env var)
                # When disabled: 1 photo per place = accurate billing
                # When enabled: N photos per place but carousel photos are NOT tracked for billing
                if PLACE_CAROUSEL_ENABLED:
                    details["photo_urls"] = [
                        f"/api/v1/connectors/google-places/photo/{name}"
                        for name in photo_names[:PLACES_MAX_GALLERY_PHOTOS]
                    ]
                else:
                    # Single photo mode: photo_urls contains only the thumbnail
                    details["photo_urls"] = [details["photo_url"]]

        # Reviews (3 most recent, sorted by publishTime)
        reviews = place.get("reviews", [])
        if reviews:
            # Sort by publishTime descending (most recent first)
            # publishTime is ISO 8601 format, lexicographic sort works
            sorted_reviews = sorted(
                reviews,
                key=lambda r: r.get("publishTime", ""),
                reverse=True,
            )
            details["reviews"] = [
                {
                    "rating": r.get("rating"),
                    "text": r.get("text", {}).get("text", "")[:200],
                    "relative_time": r.get("relativePublishTimeDescription"),
                }
                for r in sorted_reviews[:3]
            ]

        logger.info(
            "get_place_details_success",
            user_id=str(user_id),
            place_id=place_id,
            name=details.get("name"),
            has_distance=distance_source is not None,
        )

        return {
            "success": True,
            "data": details,
            "mode": "single",
        }

    async def _execute_batch(
        self,
        client: GooglePlacesClient,
        user_id: UUID,
        place_ids: list[str],
        force_refresh: bool,
    ) -> dict[str, Any]:
        """Execute batch place details fetch using asyncio.gather for parallelism.

        MULTI-ORDINAL FIX (2026-01-01): Added for multi-reference queries.
        """
        import asyncio

        from src.domains.agents.tools.runtime_helpers import (
            get_browser_geolocation,
            get_user_home_location,
            get_user_language_safe,
        )

        # Get user language for i18n
        language = await get_user_language_safe(self.runtime)

        # Get user location for distance calculation
        center_lat: float | None = None
        center_lon: float | None = None
        distance_source: str | None = None

        browser_loc = await get_browser_geolocation(self.runtime)
        if browser_loc:
            center_lat = browser_loc.lat
            center_lon = browser_loc.lon
            distance_source = browser_loc.source
        else:
            home_loc = await get_user_home_location(self.runtime)
            if home_loc:
                center_lat = home_loc.lat
                center_lon = home_loc.lon
                distance_source = home_loc.source

        # Fetch all places in parallel
        async def fetch_single(pid: str) -> tuple[str, dict[str, Any] | None, str | None]:
            """Fetch single place, return (place_id, place_data, error)."""
            try:
                place = await client.get_place_details(
                    place_id=pid,
                    use_cache=not force_refresh,
                )

                # Format the detailed place info (simplified for batch)
                display_name = place.get("displayName", {})
                location = place.get("location", {})

                place_lat = location.get("latitude")
                place_lon = location.get("longitude")

                place_id_value = place.get("id")
                details = {
                    "id": place_id_value,
                    "place_id": place_id_value,
                    "name": display_name.get("text", "Unknown"),
                    "address": place.get("formattedAddress", ""),
                    "location": {"lat": place_lat, "lon": place_lon},
                    "types": place.get("types", []),
                    "google_maps_url": place.get("googleMapsUri"),
                }

                # Calculate distance
                if (
                    center_lat is not None
                    and center_lon is not None
                    and distance_source is not None
                    and place_lat is not None
                    and place_lon is not None
                ):
                    distance_result = calculate_distance_sync(
                        origin_lat=center_lat,
                        origin_lon=center_lon,
                        dest_lat=place_lat,
                        dest_lon=place_lon,
                        source=distance_source,
                        language=language,
                    )
                    details.update(distance_result.to_dict())

                # Contact info
                if place.get("nationalPhoneNumber"):
                    details["phone"] = place.get("nationalPhoneNumber")
                if place.get("websiteUri"):
                    details["website"] = place.get("websiteUri")

                # Ratings
                if place.get("rating"):
                    details["rating"] = place.get("rating")
                    details["rating_count"] = place.get("userRatingCount", 0)

                return (pid, details, None)
            except Exception as e:
                logger.warning("get_place_details_batch_item_failed", place_id=pid, error=str(e))
                return (pid, None, str(e))

        results = await asyncio.gather(*[fetch_single(pid) for pid in place_ids])

        # Collect successful places and errors
        places: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for pid, place_data, error in results:
            if place_data:
                places.append(place_data)
            if error:
                errors.append({"place_id": pid, "error": error})

        logger.info(
            "get_place_details_batch_success",
            user_id=str(user_id),
            requested_count=len(place_ids),
            success_count=len(places),
            error_count=len(errors),
        )

        return {
            "success": True,
            "data": places,
            "place_ids": place_ids,
            "mode": "batch",
            "errors": errors if errors else None,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format place details as Data Registry UnifiedToolOutput.

        MULTI-ORDINAL FIX (2026-01-01): Handles both single and batch modes.
        - Single mode: One place in registry with full details
        - Batch mode: Multiple places in registry, errors in metadata
        """
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Get place details request failed"),
                error_code=result.get("error"),
                metadata={"status": "error"},
            )

        mode = result.get("mode", "single")
        data = result.get("data", {})

        if mode == "batch":
            # Batch mode: data is a list of places
            places = data if isinstance(data, list) else []
            place_ids = result.get("place_ids", [])
            errors = result.get("errors")

            output = self.build_places_output(
                places=places,
                operation="details",
            )

            # Build batch summary
            summary_lines = [f"Place details retrieved: {len(places)} place(s)"]
            for i, p in enumerate(places[:5], 1):
                name = p.get("name", "Unknown")
                address = p.get("address", "")[:30]
                summary_lines.append(f'{i}. "{name}" - {address}')
            if len(places) > 5:
                summary_lines.append(f"... and {len(places) - 5} more")

            output.message = "\n".join(summary_lines)
            output.metadata["place_ids"] = place_ids
            output.metadata["mode"] = "batch"
            if errors:
                output.metadata["errors"] = errors

            return output

        # Single mode: data is a single place dict
        details = data if isinstance(data, dict) else {}
        output = self.build_places_output(
            places=[details],
            operation="details",
        )
        output.metadata["mode"] = "single"
        return output


# Create tool instance
_get_place_details_tool_instance = GetPlaceDetailsTool()


@connector_tool(
    name="get_place_details",
    agent_name=AGENT_PLACE,
    context_domain=CONTEXT_DOMAIN_PLACES,
    category="read",
)
async def get_place_details_tool(
    place_id: Annotated[str | None, "Google Place ID (single mode)"] = None,
    place_ids: Annotated[
        list[str] | None,
        "List of Google Place IDs (batch mode for multi-ordinal queries)",
    ] = None,
    force_refresh: Annotated[bool, "Force refresh from API (bypass cache)"] = False,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Get detailed information about one or more places.

    Supports both single and batch modes:
    - Single: place_id="abc123" → fetch one place
    - Batch: place_ids=["abc123", "def456"] → fetch multiple places in parallel

    MULTI-ORDINAL FIX (2026-01-01): Added batch mode for multi-reference queries.
    Example: "detail du 1 et du 2" → place_ids=["id1", "id2"]

    Retrieves comprehensive details including:
    - Name, address, coordinates
    - Phone number, website
    - Opening hours
    - Reviews and ratings
    - Photos

    IMPORTANT: This tool requires Google Places connector to be activated.
    Go to Settings > Connectors to authorize Google Places.

    Args:
        place_id: Google Place ID for single mode (obtained from search results)
        place_ids: List of Google Place IDs for batch mode
        force_refresh: Force refresh from API (bypass cache)
        runtime: Tool runtime (injected)

    Returns:
        Complete place details

    Examples:
        - get_place_details(place_id="ChIJLU7jZClu5kcR4PcOy...")
        - get_place_details(place_ids=["ChIJ1...", "ChIJ2..."])
    """
    return await _get_place_details_tool_instance.execute(
        runtime=runtime,
        place_id=place_id,
        place_ids=place_ids,
        force_refresh=force_refresh,
    )


# ============================================================================
# TOOL 4: LIST PLACES (Class-based with OAuth)
# ============================================================================


class ListPlacesTool(ToolOutputMixin, ConnectorTool[GooglePlacesClient]):
    """
    List places tool using ConnectorTool architecture with global API Key.

    Allows listing places from cache or recent searches without new API calls.
    """

    connector_type = ConnectorType.GOOGLE_PLACES
    client_class = GooglePlacesClient
    registry_enabled = True  # Enable Data Registry mode
    uses_global_api_key = True  # Uses global GOOGLE_API_KEY instead of OAuth

    def __init__(self) -> None:
        """Initialize list places tool."""
        super().__init__(tool_name="get_places_tool", operation="list")

    async def execute_api_call(
        self,
        client: GooglePlacesClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list places API call - business logic only."""
        # For Places, "list" is essentially a search with empty query or cache retrieval
        # But since Places API requires a query or location, we'll check cache first
        # If no cache, we might return empty or default nearby if location known

        # This tool is primarily for retrieving cached results or listing specific IDs
        # For now, we'll implement it as a cache retrieval mechanism

        # TODO: Implement proper cache retrieval logic in client if needed
        # For now, we return empty list if no specific logic
        return {
            "success": True,
            "data": {
                "places": [],
                "total": 0,
                "message": "List functionality requires specific implementation or cache access",
            },
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format list places as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "List places request failed"),
                error_code=result.get("error"),
                metadata={"status": "error"},
            )

        data = result.get("data", {})
        places = data.get("places", [])

        return self.build_places_output(
            places=places,
            operation="list",
        )


# Create tool instance
_list_places_tool_instance = ListPlacesTool()


@connector_tool(
    name="list_places",
    agent_name=AGENT_PLACE,
    context_domain=CONTEXT_DOMAIN_PLACES,
    category="read",
)
async def list_places_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    limit: Annotated[int, "Maximum number of results (default: 10)"] = 10,
) -> str:
    """
    List recently viewed or cached places.

    Useful for retrieving context without performing a new search.

    Args:
        runtime: Tool runtime (injected)
        limit: Maximum results to return

    Returns:
        List of places
    """
    return await _list_places_tool_instance.execute(
        runtime=runtime,
        limit=limit,
    )


# ============================================================================
# TOOL 5: GET CURRENT LOCATION (Reverse Geocoding)
# ============================================================================


class LocationItem(BaseModel):
    """Schema for current location data in context registry."""

    formatted_address: str  # Full address string
    locality: str | None = None  # City/town
    country: str | None = None  # Country name
    postal_code: str | None = None  # ZIP/postal code
    latitude: float  # Latitude coordinate
    longitude: float  # Longitude coordinate


# Register Location context type for Data Registry support
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_LOCATION,
        agent_name=AGENT_PLACE,
        item_schema=LocationItem,
        primary_id_field="formatted_address",
        display_name_field="formatted_address",
        reference_fields=["locality", "country"],
        icon="📍",
    )
)


class GetCurrentLocationTool(ToolOutputMixin, ConnectorTool[GooglePlacesClient]):
    """
    Get current location tool using reverse geocoding.

    Uses browser geolocation (WiFi-based) and Google Geocoding API
    to provide the user's current address when they ask "où suis-je?".
    """

    connector_type = ConnectorType.GOOGLE_PLACES
    client_class = GooglePlacesClient
    registry_enabled = True  # Enable Data Registry mode
    uses_global_api_key = True  # Uses global GOOGLE_API_KEY instead of OAuth

    def __init__(self) -> None:
        """Initialize get current location tool."""
        super().__init__(tool_name="get_current_location_tool", operation="location")

    async def execute_api_call(
        self,
        client: GooglePlacesClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute reverse geocoding to get current address."""
        from src.domains.agents.tools.runtime_helpers import (
            get_browser_geolocation,
            get_user_language_safe,
        )
        from src.domains.agents.utils.i18n_location import get_fallback_message

        # Get user language for i18n
        language = await get_user_language_safe(self.runtime)

        # Get browser geolocation (required for this tool)
        browser_loc = await get_browser_geolocation(self.runtime)

        if not browser_loc:
            # No geolocation available - return localized fallback message
            fallback_msg = get_fallback_message(language)
            logger.warning(
                "get_current_location_no_geolocation",
                user_id=str(user_id),
                language=language,
            )
            return {
                "success": False,
                "error": "geolocation_unavailable",
                "message": fallback_msg,
            }

        latitude = browser_loc.lat
        longitude = browser_loc.lon

        logger.info(
            "get_current_location_starting",
            user_id=str(user_id),
            latitude=latitude,
            longitude=longitude,
        )

        # Perform reverse geocoding
        geocode_result = await client.reverse_geocode(
            latitude=latitude,
            longitude=longitude,
        )

        if not geocode_result.get("success"):
            logger.warning(
                "get_current_location_geocode_failed",
                user_id=str(user_id),
                status=geocode_result.get("status"),
                error=geocode_result.get("error_message"),
            )
            return {
                "success": False,
                "error": "geocoding_failed",
                "message": geocode_result.get("error_message", "Reverse geocoding failed"),
                "location": {"lat": latitude, "lon": longitude},
            }

        # Build location response
        location_data = {
            "formatted_address": geocode_result.get("formatted_address", ""),
            "street_number": geocode_result.get("street_number"),
            "route": geocode_result.get("route"),
            "locality": geocode_result.get("locality"),
            "administrative_area_level_1": geocode_result.get("administrative_area_level_1"),
            "administrative_area_level_2": geocode_result.get("administrative_area_level_2"),
            "country": geocode_result.get("country"),
            "country_code": geocode_result.get("country_code"),
            "postal_code": geocode_result.get("postal_code"),
            "place_id": geocode_result.get("place_id"),
            "location": {
                "lat": latitude,
                "lon": longitude,
            },
            "location_type": geocode_result.get("location_type"),
            "source": "browser_geolocation",
        }

        logger.info(
            "get_current_location_success",
            user_id=str(user_id),
            formatted_address=location_data["formatted_address"][:50],
            locality=location_data.get("locality"),
            country=location_data.get("country"),
        )

        return {
            "success": True,
            "data": location_data,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format location as Data Registry UnifiedToolOutput."""
        from src.domains.agents.data_registry.models import (
            RegistryItem,
            RegistryItemMeta,
            RegistryItemType,
            generate_registry_id,
        )

        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Could not determine current location"),
                error_code=result.get("error"),
                metadata={"status": "error"},
            )

        data = result.get("data", {})

        # Build concise summary for LLM
        parts = []
        if data.get("formatted_address"):
            parts.append(f"Adresse: {data['formatted_address']}")
        if data.get("locality"):
            parts.append(f"Ville: {data['locality']}")
        if data.get("country"):
            parts.append(f"Pays: {data['country']}")
        if data.get("location"):
            loc = data["location"]
            parts.append(f"Coordonnées: {loc.get('lat'):.6f}, {loc.get('lon'):.6f}")

        summary = "\n".join(parts) if parts else "Position actuelle obtenue"

        # Prepare registry update for frontend rendering
        location_item = LocationItem(
            formatted_address=data.get("formatted_address", ""),
            locality=data.get("locality"),
            country=data.get("country"),
            postal_code=data.get("postal_code"),
            latitude=data.get("location", {}).get("lat", 0),
            longitude=data.get("location", {}).get("lon", 0),
        )

        # Generate unique registry ID for this location
        registry_id = generate_registry_id(
            RegistryItemType.LOCATION,
            f"{location_item.latitude}_{location_item.longitude}",
        )

        # Create proper RegistryItem
        registry_item = RegistryItem(
            id=registry_id,
            type=RegistryItemType.LOCATION,
            payload=location_item.model_dump(),
            meta=RegistryItemMeta(
                source="google_geocoding",
                domain=CONTEXT_DOMAIN_LOCATION,
                tool_name="get_current_location_tool",
            ),
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={
                registry_id: registry_item,
            },
            metadata={
                "status": "success",
                "location_type": data.get("location_type"),
                "source": data.get("source"),
            },
        )


# Create tool instance
_get_current_location_tool_instance = GetCurrentLocationTool()


@connector_tool(
    name="get_current_location",
    agent_name=AGENT_PLACE,
    context_domain=CONTEXT_DOMAIN_LOCATION,
    category="read",
)
async def get_current_location_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
) -> str:
    """
    Get user's current location using browser geolocation and reverse geocoding.

    This tool answers questions like:
    - "Où suis-je ?" (Where am I?)
    - "À quelle adresse je suis ?" (What address am I at?)
    - "Quelle est ma position actuelle ?" (What is my current position?)

    Uses WiFi-based browser geolocation to get coordinates, then performs
    reverse geocoding via Google Geocoding API to get the full address.

    IMPORTANT: This tool requires:
    1. Browser geolocation to be enabled (user permission required)
    2. Google Places connector to be activated

    Args:
        runtime: Tool runtime (injected)

    Returns:
        Current location with full address details including:
        - Formatted address
        - City/locality
        - Country
        - Postal code
        - GPS coordinates

    Examples:
        User: "Où suis-je ?"
        User: "C'est quoi mon adresse actuelle ?"
        User: "Je suis à quelle adresse ?"
    """
    return await _get_current_location_tool_instance.execute(runtime=runtime)


# ============================================================================
# ============================================================================
# UNIFIED TOOL: GET PLACES (v2.0 - replaces search + details)
# ============================================================================


@connector_tool(
    name="get_places",
    agent_name=AGENT_PLACE,
    context_domain=CONTEXT_DOMAIN_PLACES,
    category="read",
)
async def get_places_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    query: str | None = None,
    location: str | None = None,
    place_id: str | None = None,
    place_ids: list[str] | None = None,
    place_type: str | None = None,
    max_results: int | None = None,
    radius_meters: int | None = None,
    open_now: bool = False,
    min_rating: float | None = None,
    price_levels: list[str] | None = None,
    force_refresh: bool = False,
    language: str | None = None,
) -> UnifiedToolOutput:
    """
    Get places with full details - unified search and retrieval.

    Architecture Simplification (2026-01):
    - Replaces search_places_tool + get_place_details_tool
    - Always returns FULL place details (name, address, hours, reviews)
    - Supports query mode (search) OR ID mode (direct fetch)

    Modes:
    - Query mode: get_places_tool(query="restaurant") → search + return full details
    - ID mode: get_places_tool(place_id="abc123") → fetch specific place
    - Batch mode: get_places_tool(place_ids=["abc", "def"]) → fetch multiple
    - Type mode: get_places_tool(place_type="restaurant") → nearby by type
    - List mode: get_places_tool() → return nearby places

    Args:
        runtime: Runtime dependencies injected automatically.
        query: Search term (name, type, area) - triggers search mode.
        location: Physical address for proximity search (e.g., "Paris", "75001").
            When used with radius_meters, enables viewport restriction via geocoding.
            Semantic type: physical_address - triggers contacts resolution for person references.
        place_id: Single place ID for direct fetch.
        place_ids: Multiple place IDs for batch fetch.
        place_type: Filter by place type (restaurant, pharmacy, etc.).
        max_results: Maximum results (default 10, max 50).
        radius_meters: Maximum distance / search radius in meters.
        open_now: Filter to only show places currently open (default False).
        min_rating: Minimum rating filter (1.0-5.0). Only returns places with rating >= this value.
        price_levels: Price level filter list. Valid values:
            PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE,
            PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE
        force_refresh: Bypass cache (default False).
        language: Language code for results (e.g., "fr", "en", "es", "de", "it", "zh-CN").
            If not provided, uses user's preferred language from runtime context.

    Returns:
        UnifiedToolOutput with registry items containing place data.

    Examples:
        - get_places_tool(query="cafés ouverts", open_now=True)
        - get_places_tool(query="restaurant", min_rating=4.0)
        - get_places_tool(query="bar", price_levels=["PRICE_LEVEL_MODERATE"])
    """
    # Route to appropriate implementation based on parameters
    if place_id or place_ids:
        # ID mode: direct fetch with full details
        return await _get_place_details_tool_instance.execute(
            runtime=runtime,
            place_id=place_id,
            place_ids=place_ids,
            force_refresh=force_refresh,
        )
    elif query or place_type or location:
        # Query/Type/Location mode: search + full details
        return await _search_places_tool_instance.execute(
            runtime=runtime,
            query=query or "",
            location=location,
            max_results=max_results,
            place_type=place_type,
            radius_meters=radius_meters,
            open_now=open_now,
            min_rating=min_rating,
            price_levels=price_levels,
            force_refresh=force_refresh,
        )
    else:
        # List mode: return nearby places (location not provided)
        return await _list_places_tool_instance.execute(
            runtime=runtime,
            max_results=max_results,
            radius_meters=radius_meters,
            force_refresh=force_refresh,
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Unified tool (v2.0 - replaces search + details)
    "get_places_tool",
    # Other tools
    "get_current_location_tool",  # Reverse geocoding tool
    # Tool classes (for advanced usage)
    "SearchPlacesTool",
    "GetPlaceDetailsTool",
    "ListPlacesTool",
    "GetCurrentLocationTool",
]
