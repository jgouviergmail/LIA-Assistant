"""
Google Geocoding API helpers.

Provides forward and reverse geocoding using Google Geocoding API.
Uses API key authentication (GOOGLE_API_KEY) - no OAuth required.

API Reference:
- https://developers.google.com/maps/documentation/geocoding/overview

Usage:
    from src.domains.connectors.clients.google_geocoding_helpers import (
        forward_geocode,
        reverse_geocode,
    )

    # Forward geocode: address → coordinates
    result = await forward_geocode("149 Rue de Sèvres, 75015 Paris, France")
    if result:
        lat, lon, locality, country_code = result

    # Reverse geocode: coordinates → address
    address = await reverse_geocode(48.8566, 2.3522, language="fr")
"""

import httpx
import structlog

from src.core.config import settings
from src.domains.connectors.clients.google_api_tracker import track_google_api_call

logger = structlog.get_logger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

GOOGLE_GEOCODING_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# ============================================================================
# CONNECTION POOLING
# ============================================================================
# Reuse httpx.AsyncClient across calls to avoid TLS handshake overhead (~50-100ms)
# Uses lazy initialization pattern to avoid startup cost if geocoding not used.

_geocoding_client: httpx.AsyncClient | None = None


def _get_geocoding_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client for geocoding API calls.

    Uses module-level singleton pattern for connection pooling.
    The client is created lazily on first use.

    Note: Client cleanup is handled by the application shutdown hook.
    See: src/main.py shutdown event handler.
    """
    global _geocoding_client
    if _geocoding_client is None:
        _geocoding_client = httpx.AsyncClient(
            timeout=settings.http_timeout_geocoding_api,
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
                keepalive_expiry=30.0,
            ),
        )
    return _geocoding_client


async def close_geocoding_client() -> None:
    """Close the shared geocoding client.

    Call this during application shutdown to properly close connections.
    Safe to call even if client was never created.
    """
    global _geocoding_client
    if _geocoding_client is not None:
        await _geocoding_client.aclose()
        _geocoding_client = None
        logger.debug("google_geocoding_client_closed")


# ============================================================================
# FORWARD GEOCODING (address → coordinates)
# ============================================================================


async def forward_geocode(
    address: str,
    language: str = "en",
) -> tuple[float, float, str, str] | None:
    """
    Geocode an address to coordinates using Google Geocoding API.

    Handles all international address formats reliably:
    - "149 Rue de Sèvres, 75015 Paris, France" → Paris coordinates
    - "221B Baker Street, London W1U 6RS, UK" → London coordinates
    - "1600 Amphitheatre Parkway, Mountain View, CA" → California coordinates

    Args:
        address: Full address string
        language: Language code for results (default: en for internal processing)

    Returns:
        Tuple of (lat, lon, locality_name, country_code) if successful,
        None if geocoding fails or API key not configured.

    Note:
        Cost: ~$5 per 1000 requests.
        Use as fallback when primary geocoding fails.
    """
    if not settings.google_api_key:
        logger.debug("google_forward_geocode_skipped_no_api_key")
        return None

    try:
        params = {
            "address": address,
            "key": settings.google_api_key,
            "language": language,
        }

        client = _get_geocoding_client()
        response = await client.get(GOOGLE_GEOCODING_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

        # Track API call (always non-cached for geocoding)
        track_google_api_call("geocoding", "/geocode/json", cached=False)

        if data.get("status") != "OK":
            logger.debug(
                "google_forward_geocode_status",
                address=address[:50],
                status=data.get("status"),
            )
            return None

        results = data.get("results", [])
        if not results:
            return None

        # Get the first (most relevant) result
        result = results[0]
        geometry = result.get("geometry", {})
        location = geometry.get("location", {})

        lat = location.get("lat")
        lon = location.get("lng")

        if lat is None or lon is None:
            return None

        # Extract locality (city) and country from address components
        locality = ""
        country_code = ""
        for component in result.get("address_components", []):
            types = component.get("types", [])
            if "locality" in types:
                locality = component.get("long_name", "")
            elif "administrative_area_level_1" in types and not locality:
                # Fallback to admin area if no locality
                locality = component.get("long_name", "")
            elif "country" in types:
                country_code = component.get("short_name", "")

        # If no locality found, use first part of formatted address
        if not locality:
            locality = result.get("formatted_address", address).split(",")[0]

        logger.debug(
            "google_forward_geocode_success",
            original_address=address[:50],
            resolved_locality=locality,
            country=country_code,
            lat=lat,
            lon=lon,
        )

        return (lat, lon, locality, country_code)

    except httpx.TimeoutException:
        logger.warning("google_forward_geocode_timeout", address=address[:50])
    except httpx.HTTPStatusError as e:
        logger.warning(
            "google_forward_geocode_http_error",
            address=address[:50],
            status_code=e.response.status_code,
        )
    except Exception as e:
        logger.warning(
            "google_forward_geocode_error",
            address=address[:50],
            error=str(e),
            error_type=type(e).__name__,
        )

    return None


# ============================================================================
# REVERSE GEOCODING (coordinates → address)
# ============================================================================


async def reverse_geocode(
    lat: float,
    lon: float,
    language: str = "fr",
    simplify: bool = True,
) -> str | None:
    """
    Reverse geocode coordinates to a human-readable address.

    Uses Google Geocoding API to convert lat/lon to street address.

    Args:
        lat: Latitude
        lon: Longitude
        language: Language code for address formatting (default: fr)
        simplify: If True, simplify address by removing postal code and country

    Returns:
        Formatted address string or None if geocoding fails.

    Example:
        >>> await reverse_geocode(48.8566, 2.3522, language="fr")
        "Rue de Rivoli, Paris"
    """
    if not settings.google_api_key:
        logger.debug("google_reverse_geocode_skipped_no_api_key")
        return None

    try:
        params = {
            "latlng": f"{lat},{lon}",
            "key": settings.google_api_key,
            "language": language,
            "result_type": "street_address|route|locality",  # Prefer street addresses
        }

        client = _get_geocoding_client()
        response = await client.get(GOOGLE_GEOCODING_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

        # Track API call (always non-cached for geocoding)
        track_google_api_call("geocoding", "/geocode/json", cached=False)

        results = data.get("results", [])
        if not results:
            logger.debug("google_reverse_geocode_no_results", lat=lat, lon=lon)
            return None

        # Get the first (most precise) result
        address = results[0].get("formatted_address", "")
        if not address:
            return None

        if simplify:
            # Simplify: remove country and postal code for brevity
            # "123 Rue Example, 75001 Paris, France" -> "123 Rue Example, Paris"
            parts = [p.strip() for p in address.split(",")]
            if len(parts) >= 3:
                # Keep street + city, drop postal code and country
                address = ", ".join(parts[:2])

        logger.debug(
            "google_reverse_geocode_success",
            lat=lat,
            lon=lon,
            address=address[:50],
        )

        return address

    except httpx.TimeoutException:
        logger.warning("google_reverse_geocode_timeout", lat=lat, lon=lon)
    except httpx.HTTPStatusError as e:
        logger.warning(
            "google_reverse_geocode_http_error",
            lat=lat,
            lon=lon,
            status_code=e.response.status_code,
        )
    except Exception as e:
        logger.warning(
            "google_reverse_geocode_error",
            lat=lat,
            lon=lon,
            error=str(e),
            error_type=type(e).__name__,
        )

    return None


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "GOOGLE_GEOCODING_API_URL",
    "close_geocoding_client",
    "forward_geocode",
    "reverse_geocode",
]
