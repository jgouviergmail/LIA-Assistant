"""Media proxy endpoints for the connectors family (extracted 2026-08).

Authenticated, rate-limited proxies for BILLED Google image requests
(static maps for routes/locations, Street View thumbnails). Split from
connectors/router.py (file-size ratchet) as one cohesive sub-router,
included by the main connectors router so paths and the demo-mode
account-linking guard are unchanged.
"""

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.core.config import settings
from src.core.constants import (
    GOOGLE_STATIC_MAPS_URL_LIMIT,
    RATE_LIMIT_STATIC_MAP_PER_MINUTE,
    STATIC_MAP_MARKER_DEST_COLOR,
    STATIC_MAP_MARKER_ORIGIN_COLOR,
    STATIC_MAP_MAX_DIMENSION,
    STATIC_MAP_MIN_DIMENSION,
    STATIC_MAP_POLYLINE_COLOR,
    STATIC_MAP_POLYLINE_WEIGHT,
    STREET_VIEW_DEFAULT_HEIGHT,
    STREET_VIEW_DEFAULT_WIDTH,
)
from src.core.exceptions import (
    InternalServerError,
    raise_configuration_missing,
    raise_external_service_connection_error,
    raise_external_service_fetch_error,
    raise_internal_error,
    raise_invalid_input,
)
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

media_proxy_router = APIRouter()

# Per-user budget for the Google media proxies. The dependency chains
# `get_current_active_session`, so it also carries the authentication these
# endpoints require.
rate_limit_static_map = create_user_rate_limiter(
    action="static_map",
    max_calls=RATE_LIMIT_STATIC_MAP_PER_MINUTE,
)


# Google Routes Static Map proxy (MUST be before /{connector_id} to avoid path matching conflict)
#
# This endpoint was public. The stated reason — "browser <img> tags don't send
# session cookies" — does not hold here: the URL handed to the browser is
# RELATIVE (`/api/v1/connectors/google-routes/static-map?...`, built in
# routes_tools.py), so it resolves against the FRONTEND origin and is same-origin;
# the browser attaches the session cookie and Next's `/api/v1/:path*` rewrite
# forwards it. `auth/profile_image_router.py` already relies on exactly that:
# an authenticated proxy consumed from an <img> via a relative URL, and avatars
# render fine in production.
#
# Left public, each call is an unauthenticated, BILLED Google Static Maps request
# that anyone on the internet can issue in a loop (OWASP API4). Authentication
# closes that, and costs nothing functionally: these maps are only ever rendered
# inside an authenticated chat (RouteCard via html_renderer) — never in an email,
# a push or an export. Cards already stored in conversation history keep working:
# the reader is signed in.
@media_proxy_router.get(
    "/google-routes/static-map",
    summary="Proxy Google Routes static map",
    description="Proxy endpoint to generate static map images for routes using API key.",
    responses={
        200: {"content": {"image/png": {}}, "description": "Static map image"},
        400: {"description": "Invalid parameters"},
        401: {"description": "Authentication required"},
        429: {"description": "Per-user rate limit exceeded"},
    },
)
async def proxy_routes_static_map(
    polyline: str,
    width: int = 600,
    height: int = 300,
    origin: str | None = None,
    dest: str | None = None,
    current_user: User = Depends(get_current_active_session),
    _rate_limit: None = Depends(rate_limit_static_map),
) -> StreamingResponse:
    """
    Proxy Google Static Maps API with encoded polyline and optional markers.

    This endpoint generates a static map image showing a route polyline,
    using the server's API key to avoid exposing it to the frontend.
    Optional origin/destination markers ensure accurate visual representation
    even when the polyline is simplified for long routes.

    Authenticated and per-user rate-limited: each call is a BILLED Google
    request, and the relative URL is same-origin so the browser attaches the
    session cookie (see the module-level comment for the full rationale).

    Args:
        polyline: URL-encoded polyline string from Routes API
        width: Map width in pixels (50-2048, default 600)
        height: Map height in pixels (50-2048, default 300)
        origin: Optional origin coordinates as "lat,lng" for green marker
        dest: Optional destination coordinates as "lat,lng" for red marker

    Returns:
        StreamingResponse with the map image
    """
    import re
    from urllib.parse import quote

    import httpx

    try:
        api_key = settings.google_api_key
        if not api_key:
            logger.warning("google_api_key_not_configured_for_static_map")
            raise_configuration_missing("google_routes", "api_key")

        # Validate coordinate format for origin/dest to prevent parameter injection
        _coord_pattern = re.compile(r"^-?\d{1,3}(\.\d+)?,-?\d{1,3}(\.\d+)?$")
        if origin and not _coord_pattern.match(origin):
            raise_invalid_input("origin must be 'lat,lng' format", field="origin")
        if dest and not _coord_pattern.match(dest):
            raise_invalid_input("dest must be 'lat,lng' format", field="dest")

        # Validate dimensions (Google limits from constants)
        width = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, width))
        height = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, height))

        # FastAPI auto-decodes query params, so polyline arrives decoded here
        # We must re-encode it for the Google Static Maps URL
        # Google polyline chars (ASCII 63-126) include URL-unsafe chars like \ | ?
        encoded_polyline = quote(polyline, safe="")

        # Build Static Maps URL with polyline path (colors from constants)
        static_map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap?"
            f"size={width}x{height}"
            f"&path=color:{STATIC_MAP_POLYLINE_COLOR}|weight:{STATIC_MAP_POLYLINE_WEIGHT}|enc:{encoded_polyline}"
        )

        # Add origin marker (label A) - ensures accurate starting point
        if origin:
            static_map_url += f"&markers=color:{STATIC_MAP_MARKER_ORIGIN_COLOR}|label:A|{origin}"

        # Add destination marker (label B) - ensures accurate ending point
        if dest:
            static_map_url += f"&markers=color:{STATIC_MAP_MARKER_DEST_COLOR}|label:B|{dest}"

        # Add API key last
        static_map_url += f"&key={api_key}"

        # Note: Polyline is pre-simplified in routes_tools.py to fit URL limits
        # Google Static Maps URL limit from GOOGLE_STATIC_MAPS_URL_LIMIT
        url_length = len(static_map_url)
        if url_length > GOOGLE_STATIC_MAPS_URL_LIMIT:
            logger.warning(
                "static_map_url_too_long_fallback",
                url_length=url_length,
                polyline_length=len(polyline),
                limit=GOOGLE_STATIC_MAPS_URL_LIMIT,
            )
            raise_external_service_fetch_error("google_routes", "static_map (URL too long)", 414)

        logger.debug(
            "static_map_proxy_request",
            width=width,
            height=height,
            polyline_length=len(polyline),
            url_length=url_length,
            has_origin_marker=bool(origin),
            has_dest_marker=bool(dest),
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                static_map_url,
                follow_redirects=True,
                timeout=settings.http_timeout_connector_standard,
            )

            if response.status_code != 200:
                logger.warning(
                    "static_map_proxy_error",
                    status_code=response.status_code,
                    response_text=response.text[:200] if response.text else None,
                )
                raise_external_service_fetch_error(
                    "google_routes", "static_map", response.status_code
                )

            content_type = response.headers.get("content-type", "image/png")

            logger.debug(
                "static_map_proxy_success",
                content_length=len(response.content),
            )

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 24 hours
                },
            )
    except httpx.RequestError as e:
        logger.error(
            "static_map_proxy_request_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_external_service_connection_error("google_routes")
    except InternalServerError:
        # Re-raise API exceptions as-is
        raise
    except Exception as e:
        # Catch any other unexpected errors for debugging
        logger.exception(
            "static_map_proxy_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_internal_error(
            detail=f"Static map proxy error: {type(e).__name__}",
            error_type=type(e).__name__,
        )


# Location Static Map proxy (single marker, no polyline)
# Same pattern as the route static map above — authenticated and rate limited,
# for the same reason: every call is a billed Google request.
@media_proxy_router.get(
    "/google-location/static-map",
    summary="Proxy Google location static map",
    description="Generate a static map image with a single marker at the given coordinates.",
    responses={
        200: {"content": {"image/png": {}}, "description": "Static map image"},
        400: {"description": "Invalid parameters"},
        401: {"description": "Authentication required"},
        429: {"description": "Per-user rate limit exceeded"},
    },
)
async def proxy_location_static_map(
    lat: str,
    lng: str,
    width: int = 600,
    height: int = 300,
    zoom: int = 14,
    current_user: User = Depends(get_current_active_session),
    _rate_limit: None = Depends(rate_limit_static_map),
) -> StreamingResponse:
    """Proxy Google Static Maps API with a single marker for current position.

    Args:
        lat: Latitude coordinate.
        lng: Longitude coordinate.
        width: Map width in pixels (50-2048, default 600).
        height: Map height in pixels (50-2048, default 300).
        zoom: Zoom level (1-20, default 14).

    Returns:
        StreamingResponse with the map image.
    """
    import re

    import httpx

    try:
        api_key = settings.google_api_key
        if not api_key:
            logger.warning("google_api_key_not_configured_for_location_map")
            raise_configuration_missing("google_location", "api_key")

        # Validate coordinate format
        _coord_pattern = re.compile(r"^-?\d{1,3}(\.\d+)?$")
        if not _coord_pattern.match(lat) or not _coord_pattern.match(lng):
            raise_invalid_input("lat and lng must be numeric", field="coordinates")

        # Validate dimensions
        width = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, width))
        height = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, height))
        zoom = max(1, min(20, zoom))

        static_map_url = (
            f"https://maps.googleapis.com/maps/api/staticmap?"
            f"center={lat},{lng}"
            f"&zoom={zoom}"
            f"&size={width}x{height}"
            f"&markers=color:red|{lat},{lng}"
            f"&key={api_key}"
        )

        logger.debug(
            "location_static_map_proxy_request",
            lat=lat,
            lng=lng,
            width=width,
            height=height,
            zoom=zoom,
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                static_map_url,
                follow_redirects=True,
                timeout=settings.http_timeout_connector_standard,
            )

            if response.status_code != 200:
                logger.warning(
                    "location_static_map_proxy_error",
                    status_code=response.status_code,
                )
                raise_external_service_fetch_error(
                    "google_location", "static_map", response.status_code
                )

            content_type = response.headers.get("content-type", "image/png")

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                },
            )
    except httpx.RequestError as e:
        logger.error(
            "location_static_map_proxy_request_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_external_service_connection_error("google_location")
    except InternalServerError:
        raise
    except Exception as e:
        logger.exception(
            "location_static_map_proxy_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_internal_error(
            detail=f"Location static map proxy error: {type(e).__name__}",
            error_type=type(e).__name__,
        )


# Street View Static proxy (lot SV, 2026-08)
# Same doctrine as the static-map proxies: authenticated + rate limited,
# every call is a billed Google request ($2/1000, 10k free/month). Producers
# only hand this URL out after the FREE metadata endpoint confirmed imagery
# exists (src/domains/connectors/street_view.py), so no grey placeholders.
@media_proxy_router.get(
    "/street-view",
    summary="Proxy Google Street View Static image",
    description="Street View thumbnail at the given coordinates (availability pre-checked).",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Street View image"},
        400: {"description": "Invalid parameters"},
        401: {"description": "Authentication required"},
        429: {"description": "Per-user rate limit exceeded"},
    },
)
async def proxy_street_view(
    location: str,
    width: int = STREET_VIEW_DEFAULT_WIDTH,
    height: int = STREET_VIEW_DEFAULT_HEIGHT,
    current_user: User = Depends(get_current_active_session),
    _rate_limit: None = Depends(rate_limit_static_map),
) -> StreamingResponse:
    """Proxy the Google Street View Static API for one point.

    Args:
        location: Coordinates as "lat,lng".
        width: Image width in pixels (50-2048, default 600).
        height: Image height in pixels (50-2048, default 300).

    Returns:
        StreamingResponse with the Street View image.
    """
    import re

    import httpx

    from src.core.constants import STREET_VIEW_IMAGE_URL
    from src.domains.connectors.clients.google_api_tracker import track_google_api_call

    try:
        api_key = settings.google_api_key
        if not api_key or not settings.street_view_enabled:
            logger.warning("street_view_proxy_unavailable")
            raise_configuration_missing("street_view", "api_key")

        _coord_pattern = re.compile(r"^-?\d{1,3}(\.\d+)?,-?\d{1,3}(\.\d+)?$")
        if not _coord_pattern.match(location):
            raise_invalid_input("location must be 'lat,lng' format", field="location")

        width = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, width))
        height = max(STATIC_MAP_MIN_DIMENSION, min(STATIC_MAP_MAX_DIMENSION, height))

        street_view_url = (
            f"{STREET_VIEW_IMAGE_URL}?size={width}x{height}&location={location}&key={api_key}"
        )

        async with httpx.AsyncClient() as client:
            response = await client.get(
                street_view_url,
                follow_redirects=True,
                timeout=settings.http_timeout_connector_standard,
            )

            if response.status_code != 200:
                logger.warning(
                    "street_view_proxy_error",
                    status_code=response.status_code,
                )
                raise_external_service_fetch_error(
                    "street_view", "street_view_image", response.status_code
                )

            # Billed call — tracked so the pricing table stays exact.
            track_google_api_call("street_view", "/streetview", cached=False)

            return StreamingResponse(
                iter([response.content]),
                media_type=response.headers.get("content-type", "image/jpeg"),
                headers={
                    "Cache-Control": "public, max-age=86400",
                },
            )
    except httpx.RequestError as e:
        logger.error(
            "street_view_proxy_request_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_external_service_connection_error("street_view")
    except InternalServerError:
        raise
    except Exception as e:
        logger.exception(
            "street_view_proxy_unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise_internal_error(
            detail=f"Street View proxy error: {type(e).__name__}",
            error_type=type(e).__name__,
        )
