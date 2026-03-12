"""
Google Places API client with global API Key authentication.

Provides access to Google Places for location search and place details.
Uses the Google Places API (New) with API Key authentication.

API Reference:
- https://developers.google.com/maps/documentation/places/web-service/overview

Authentication:
- API Key (X-Goog-Api-Key header)
- Uses global GOOGLE_API_KEY from settings (not per-user OAuth)

Note: This client uses the newer Places API (New) endpoints which provide
richer data and better pricing structure than the legacy Places API.

Migration (2026-02): Changed from OAuth to global API Key for simplified
user experience. Users now simply enable the connector without OAuth flow.
"""

import asyncio
import time
from typing import Any
from uuid import UUID

import httpx
import structlog
from fastapi import HTTPException, status

from src.core.config import settings
from src.core.constants import (
    HTTP_MAX_CONNECTIONS,
    HTTP_MAX_KEEPALIVE_CONNECTIONS,
)
from src.core.field_names import FIELD_CACHED_AT
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.cache_mixin import CacheableMixin
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.connectors.clients.google_geocoding_helpers import GOOGLE_GEOCODING_API_URL
from src.domains.connectors.models import ConnectorType
from src.infrastructure.cache import PlacesCache

logger = structlog.get_logger(__name__)


class GooglePlacesClient(CacheableMixin[PlacesCache]):
    """
    Client for Google Places API (New) with global API Key authentication.

    Uses the global GOOGLE_API_KEY from settings instead of per-user OAuth.
    This simplifies the user experience - users just enable the connector.

    Provides:
    - Rate limiting (Redis + local fallback)
    - Connection pooling
    - Retry logic with exponential backoff
    - Redis caching

    Provides access to:
    - Text search for places
    - Nearby search
    - Place details
    - Autocomplete suggestions

    Example:
        >>> client = GooglePlacesClient(user_id)
        >>> results = await client.search_text("restaurants in Paris")
        >>> print(results["places"][0]["displayName"])
    """

    connector_type = ConnectorType.GOOGLE_PLACES
    api_base_url = "https://places.googleapis.com/v1"

    # Required by CacheableMixin
    _cache_class = PlacesCache

    def __init__(
        self,
        user_id: UUID,
        language: str = "fr",
        rate_limit_per_second: int = 10,
    ) -> None:
        """
        Initialize Google Places client with global API Key.

        Args:
            user_id: User UUID (for caching and logging)
            language: Default language for results (default: fr)
            rate_limit_per_second: Max requests per second (default: 10)
        """
        self.user_id = user_id
        self.language = language
        self._rate_limit_per_second = rate_limit_per_second
        self._rate_limit_interval = 1.0 / rate_limit_per_second
        self._last_request_time = 0.0
        self._http_client: httpx.AsyncClient | None = None

    @property
    def api_key(self) -> str:
        """Get global API key from settings."""
        if not settings.google_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google Places service unavailable: API key not configured",
            )
        return settings.google_api_key

    # =========================================================================
    # HTTP CLIENT MANAGEMENT
    # =========================================================================

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client with connection pooling."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=settings.http_timeout_external_api,
                limits=httpx.Limits(
                    max_keepalive_connections=HTTP_MAX_KEEPALIVE_CONNECTIONS,
                    max_connections=HTTP_MAX_CONNECTIONS,
                    keepalive_expiry=30.0,
                ),
            )
        return self._http_client

    async def close(self) -> None:
        """Cleanup HTTP client and close connections."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    async def _rate_limit(self) -> None:
        """Simple local rate limiting."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self._rate_limit_interval:
            await asyncio.sleep(self._rate_limit_interval - elapsed)
        self._last_request_time = time.time()

    # =========================================================================
    # API REQUEST (API Key based)
    # =========================================================================

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Make HTTP request to Google Places API with API Key.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint path (e.g., /places:searchText).
            params: Query parameters.
            json_data: JSON body for POST requests.
            max_retries: Max retry attempts for 429/5xx errors.
            extra_headers: Additional headers (e.g., X-Goog-FieldMask).

        Returns:
            JSON response from API.

        Raises:
            HTTPException: On 4xx errors or max retries exceeded.
        """
        await self._rate_limit()

        url = f"{self.api_base_url}{endpoint}"
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "POST":
                    response = await client.post(
                        url, headers=headers, params=params, json=json_data
                    )
                elif method.upper() == "PUT":
                    response = await client.put(url, headers=headers, params=params, json=json_data)
                elif method.upper() == "PATCH":
                    response = await client.patch(
                        url, headers=headers, params=params, json=json_data
                    )
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=headers, params=params)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Success
                if response.status_code < 400:
                    return response.json() if response.content else {}

                # Rate limited - retry with backoff
                if response.status_code == 429:
                    wait_time = 2**attempt
                    logger.warning(
                        "places_api_rate_limited",
                        user_id=str(self.user_id),
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Server error - retry
                if response.status_code >= 500:
                    wait_time = 2**attempt
                    logger.warning(
                        "places_api_server_error",
                        user_id=str(self.user_id),
                        status_code=response.status_code,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Client error - don't retry
                logger.error(
                    "places_api_client_error",
                    user_id=str(self.user_id),
                    status_code=response.status_code,
                    endpoint=endpoint,
                    response_text=response.text[:500] if response.text else None,
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Google Places API error: {response.text}",
                )

            except httpx.RequestError as e:
                logger.error(
                    "places_api_request_error",
                    user_id=str(self.user_id),
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"Google Places API connection error: {e}",
                    ) from e
                await asyncio.sleep(2**attempt)

        # Max retries exceeded
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Places API unavailable after retries",
        )

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    async def search_text(
        self,
        query: str,
        max_results: int = settings.places_tool_default_max_results,
        include_type: str | None = None,
        location_bias: dict[str, Any] | None = None,
        location_restriction: dict[str, Any] | None = None,
        open_now: bool | None = None,
        min_rating: float | None = None,
        price_levels: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Search for places using text query.

        Args:
            query: Search query (e.g., "restaurants near Eiffel Tower")
            max_results: Maximum results to return (1-20, default: 10)
            include_type: Filter by place type (e.g., "restaurant", "cafe", "hotel")
            location_bias: Optional location to bias results towards (soft preference)
            location_restriction: Optional viewport to restrict results within (hard filter)
            open_now: Filter to only show places currently open
            min_rating: Minimum rating filter (1.0-5.0, increments of 0.5)
            price_levels: Price level filter list. Valid values:
                PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE,
                PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE
            use_cache: Whether to use Redis cache (default True)

        Note:
            - location_restriction takes precedence over location_bias if both provided
            - location_restriction guarantees results within the viewport
            - location_bias only suggests preference, results may be outside

        Returns:
            Dict with places list and metadata

        Example:
            >>> results = await client.search_text("coffee shops in Lyon")
            >>> for place in results["places"]:
            ...     print(place["displayName"]["text"])
        """
        # Check cache first
        cache = await self._get_cache()

        # Determine location param for cache key (restriction takes precedence)
        location_param = location_restriction or location_bias

        # Use cache even with filters (now supported by PlacesCache)
        if use_cache:
            cached_data, from_cache, cached_at, cache_age = await cache.get_search(
                self.user_id,
                query,
                include_type=include_type,
                open_now=open_now,
                location_bias=location_param,  # Pass location for cache key differentiation
                min_rating=min_rating,
                price_levels=price_levels,
            )
            if from_cache and cached_data:
                cached_data["from_cache"] = True
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        # Build request body for Places API (New)
        body: dict[str, Any] = {
            "textQuery": query,
            "languageCode": self.language,
            "maxResultCount": apply_max_items_limit(max_results),
        }

        if include_type:
            body["includedType"] = include_type

        # Location filtering: restriction takes precedence (hard filter vs soft bias)
        # Only one of locationRestriction or locationBias can be used
        if location_restriction:
            body["locationRestriction"] = location_restriction
        elif location_bias:
            body["locationBias"] = location_bias

        if open_now is not None:
            body["openNow"] = open_now

        if min_rating is not None:
            # Google Places API accepts minRating as a number (0.0-5.0)
            body["minRating"] = min_rating

        if price_levels:
            # Google Places API accepts priceLevels as a list of enum strings
            body["priceLevels"] = price_levels

        # Field mask for response (which fields to return)
        # Full details mode: include opening hours, reviews, editorial summary
        field_mask = ",".join(
            [
                "places.id",
                "places.displayName",
                "places.formattedAddress",
                "places.location",
                "places.rating",
                "places.userRatingCount",
                "places.priceLevel",
                "places.types",
                "places.websiteUri",
                "places.nationalPhoneNumber",
                "places.currentOpeningHours",
                "places.googleMapsUri",
                "places.photos",
                "places.editorialSummary",
                "places.reviews",
            ]
        )

        response = await self._make_request(
            "POST",
            "/places:searchText",
            json_data=body,
            extra_headers={"X-Goog-FieldMask": field_mask},
        )

        # Track API call (only for non-cached responses)
        track_google_api_call("places", "/places:searchText", cached=False)

        places = response.get("places", [])

        logger.info(
            "places_search_text_completed",
            user_id=str(self.user_id),
            query=query,
            results_count=len(places),
        )

        result = {
            "places": places,
            "query": query,
            "total": len(places),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }

        # Cache results including location filtering
        # PlacesCache._make_search_key includes all filter params in the hash
        if use_cache and places:
            await cache.set_search(
                self.user_id,
                query,
                result,
                include_type=include_type,
                open_now=open_now,
                location_bias=location_param,  # Same as used for cache key
                min_rating=min_rating,
                price_levels=price_levels,
            )

        return result

    async def search_nearby(
        self,
        latitude: float,
        longitude: float,
        radius_meters: int = 1000,
        include_types: list[str] | None = None,
        max_results: int = settings.places_tool_default_max_results,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Search for places near a location.

        Args:
            latitude: Center point latitude
            longitude: Center point longitude
            radius_meters: Search radius in meters (max: 50000)
            include_types: List of place types to include
            max_results: Maximum results (1-20)
            use_cache: Whether to use Redis cache (default True)

        Returns:
            Dict with nearby places

        Example:
            >>> results = await client.search_nearby(48.8584, 2.2945, radius_meters=500)
            >>> print(f"Found {len(results['places'])} places near Eiffel Tower")
        """
        # Check cache first
        cache = await self._get_cache()
        can_cache = include_types is None  # Only cache basic nearby searches for now

        if use_cache and can_cache:
            cached_data, from_cache, cached_at, cache_age = await cache.get_nearby(
                self.user_id, latitude, longitude, radius_meters
            )
            if from_cache and cached_data:
                cached_data["from_cache"] = True
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        body: dict[str, Any] = {
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": min(radius_meters, 50000),
                }
            },
            "languageCode": self.language,
            "maxResultCount": apply_max_items_limit(max_results),
        }

        if include_types:
            body["includedTypes"] = include_types

        # Field mask for response - include full details for unified tool
        field_mask = ",".join(
            [
                "places.id",
                "places.displayName",
                "places.formattedAddress",
                "places.location",
                "places.rating",
                "places.userRatingCount",
                "places.priceLevel",
                "places.types",
                "places.websiteUri",
                "places.nationalPhoneNumber",
                "places.currentOpeningHours",
                "places.googleMapsUri",
                "places.photos",
                "places.editorialSummary",
                "places.reviews",
            ]
        )

        response = await self._make_request(
            "POST",
            "/places:searchNearby",
            json_data=body,
            extra_headers={"X-Goog-FieldMask": field_mask},
        )

        # Track API call (only for non-cached responses)
        track_google_api_call("places", "/places:searchNearby", cached=False)

        places = response.get("places", [])

        logger.info(
            "places_search_nearby_completed",
            user_id=str(self.user_id),
            lat=latitude,
            lon=longitude,
            radius=radius_meters,
            results_count=len(places),
        )

        result = {
            "places": places,
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_meters": radius_meters,
            "total": len(places),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }

        # Cache results if eligible
        if use_cache and can_cache and places:
            await cache.set_nearby(self.user_id, latitude, longitude, radius_meters, result)

        return result

    async def get_place_details(
        self,
        place_id: str,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get detailed information about a specific place.

        Args:
            place_id: Google Place ID
            use_cache: Whether to use Redis cache (default True)

        Returns:
            Complete place details

        Example:
            >>> details = await client.get_place_details("ChIJLU7jZClu5kcR4...")
            >>> print(details["displayName"]["text"])
            >>> print(details["formattedAddress"])
        """
        # Check cache first
        cache = await self._get_cache()

        if use_cache:
            cached_data, from_cache, cached_at, cache_age = await cache.get_details(
                self.user_id, place_id
            )
            if from_cache and cached_data:
                cached_data["from_cache"] = True
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        field_mask = ",".join(
            [
                "id",
                "displayName",
                "formattedAddress",
                "location",
                "rating",
                "userRatingCount",
                "priceLevel",
                "types",
                "websiteUri",
                "nationalPhoneNumber",
                "internationalPhoneNumber",
                "currentOpeningHours",
                "regularOpeningHours",
                "googleMapsUri",
                "reviews",
                "editorialSummary",
                "photos",
                # Service options (boolean attributes for features)
                "dineIn",
                "takeout",
                "delivery",
                "curbsidePickup",
                "reservable",
                # Amenities
                "outdoorSeating",
                "liveMusic",
                "restroom",
                "allowsDogs",
                "goodForChildren",
                "goodForGroups",
                "goodForWatchingSports",
                "menuForChildren",
                # Food & drink
                "servesBeer",
                "servesBreakfast",
                "servesBrunch",
                "servesCocktails",
                "servesCoffee",
                "servesDessert",
                "servesDinner",
                "servesLunch",
                "servesVegetarianFood",
                "servesWine",
                # Accessibility
                "accessibilityOptions",
                # Parking
                "parkingOptions",
                # Payment
                "paymentOptions",
            ]
        )

        response = await self._make_request(
            "GET",
            f"/places/{place_id}",
            params={"languageCode": self.language},
            extra_headers={"X-Goog-FieldMask": field_mask},
        )

        # Track API call (only for non-cached responses)
        track_google_api_call("places", "/places/{id}", cached=False)

        logger.info(
            "places_get_details_completed",
            user_id=str(self.user_id),
            place_id=place_id,
            name=response.get("displayName", {}).get("text", "Unknown"),
        )

        # Add freshness metadata
        response["from_cache"] = False
        response[FIELD_CACHED_AT] = None

        # Cache results
        if use_cache:
            await cache.set_details(self.user_id, place_id, response)

        return response

    async def autocomplete(
        self,
        input_text: str,
        location_bias: dict[str, Any] | None = None,
        include_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get autocomplete suggestions for a partial query.

        Args:
            input_text: Partial search text
            location_bias: Optional location to bias results
            include_types: Filter by place types

        Returns:
            List of autocomplete suggestions

        Example:
            >>> suggestions = await client.autocomplete("rest Paris")
            >>> for s in suggestions:
            ...     print(s["text"]["text"])
        """
        body: dict[str, Any] = {
            "input": input_text,
            "languageCode": self.language,
        }

        if location_bias:
            body["locationBias"] = location_bias

        if include_types:
            body["includedPrimaryTypes"] = include_types

        response = await self._make_request(
            "POST",
            "/places:autocomplete",
            json_data=body,
        )

        # Track API call (autocomplete is always fresh, no caching)
        track_google_api_call("places", "/places:autocomplete", cached=False)

        suggestions = response.get("suggestions", [])

        logger.info(
            "places_autocomplete_completed",
            user_id=str(self.user_id),
            input=input_text,
            suggestions_count=len(suggestions),
        )

        return suggestions

    # =========================================================================
    # GEOCODING OPERATIONS
    # =========================================================================

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """
        Convert coordinates to address using Google Geocoding API.

        Performs reverse geocoding to get structured address from lat/lon.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            Dict with address components:
            - formatted_address: Full human-readable address
            - street_number: Street number
            - route: Street name
            - locality: City/town
            - administrative_area_level_1: State/region
            - administrative_area_level_2: County/district
            - country: Country name
            - postal_code: ZIP/postal code
            - location: {lat, lon} coordinates

        Raises:
            HTTPException: On API errors

        Example:
            >>> result = await client.reverse_geocode(48.8584, 2.2945)
            >>> print(result["formatted_address"])
            "Champ de Mars, 5 Avenue Anatole France, 75007 Paris, France"
        """
        await self._rate_limit()

        # Geocoding API endpoint (different from Places API)
        # NOTE: Geocoding API does NOT support OAuth - requires API key
        params = {
            "latlng": f"{latitude},{longitude}",
            "language": self.language,
            "key": settings.google_api_key,  # Geocoding API requires API key, not OAuth
        }

        headers = {}  # No auth header needed - API key is in params

        client = await self._get_client()

        try:
            response = await client.get(GOOGLE_GEOCODING_API_URL, headers=headers, params=params)

            if response.status_code >= 400:
                error_detail = response.text
                logger.error(
                    "geocoding_api_error",
                    user_id=str(self.user_id),
                    status_code=response.status_code,
                    error=error_detail,
                    latitude=latitude,
                    longitude=longitude,
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Google Geocoding API error: {error_detail}",
                )

            data = response.json()

            # Track API call (reverse geocoding)
            track_google_api_call("geocoding", "/geocode/json", cached=False)

            if data.get("status") != "OK":
                status_msg = data.get("status", "UNKNOWN_ERROR")
                error_msg = data.get("error_message", "No error message")
                logger.warning(
                    "geocoding_api_status_error",
                    user_id=str(self.user_id),
                    status=status_msg,
                    error_message=error_msg,
                    latitude=latitude,
                    longitude=longitude,
                )
                return {
                    "success": False,
                    "status": status_msg,
                    "error_message": error_msg,
                    "formatted_address": None,
                    "location": {"lat": latitude, "lon": longitude},
                }

            results = data.get("results", [])
            if not results:
                return {
                    "success": False,
                    "status": "ZERO_RESULTS",
                    "formatted_address": None,
                    "location": {"lat": latitude, "lon": longitude},
                }

            # Take the first (most precise) result
            result = results[0]
            address_components = result.get("address_components", [])

            # Parse address components into structured data
            parsed = {
                "success": True,
                "formatted_address": result.get("formatted_address", ""),
                "place_id": result.get("place_id"),
                "location": {"lat": latitude, "lon": longitude},
                "location_type": result.get("geometry", {}).get("location_type"),
            }

            # Extract specific address components
            component_mapping = {
                "street_number": "street_number",
                "route": "route",
                "locality": "locality",
                "administrative_area_level_1": "administrative_area_level_1",
                "administrative_area_level_2": "administrative_area_level_2",
                "country": "country",
                "postal_code": "postal_code",
            }

            for component in address_components:
                types = component.get("types", [])
                for comp_type, field_name in component_mapping.items():
                    if comp_type in types:
                        parsed[field_name] = component.get("long_name")
                        if comp_type == "country":
                            parsed["country_code"] = component.get("short_name")

            logger.info(
                "reverse_geocode_success",
                user_id=str(self.user_id),
                latitude=latitude,
                longitude=longitude,
                formatted_address=parsed.get("formatted_address", "")[:50],
            )

            return parsed

        except httpx.RequestError as e:
            logger.error(
                "geocoding_api_request_error",
                user_id=str(self.user_id),
                error=str(e),
                latitude=latitude,
                longitude=longitude,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Google Geocoding API unavailable: {e!s}",
            ) from e

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def set_language(self, language: str) -> None:
        """
        Change the default language.

        Args:
            language: Language code (e.g., "fr", "en", "de")
        """
        self.language = language

    @staticmethod
    def get_common_place_types() -> list[str]:
        """
        Get list of common place types for filtering.

        Returns:
            List of place type identifiers
        """
        return [
            "restaurant",
            "cafe",
            "bar",
            "hotel",
            "lodging",
            "supermarket",
            "pharmacy",
            "hospital",
            "doctor",
            "bank",
            "atm",
            "gas_station",
            "parking",
            "train_station",
            "airport",
            "museum",
            "tourist_attraction",
            "park",
            "gym",
            "shopping_mall",
        ]
