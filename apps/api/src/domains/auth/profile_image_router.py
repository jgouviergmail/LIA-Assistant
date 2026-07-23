"""Google profile-image proxy (COEP: require-corp compatibility).

Extracted from ``auth/router.py`` (file-size ratchet): a single, cohesive
concern — fetching the user's Google avatar server-side because
``lh3.googleusercontent.com`` sends no CORS headers, which breaks images
under our COEP policy.
"""

from urllib.parse import urlparse

import httpx
import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.core.config import settings
from src.core.exceptions import (
    raise_external_service_connection_error,
    raise_external_service_fetch_error,
    raise_invalid_input,
)
from src.core.session_dependencies import get_current_active_session
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Allowed Google image domains (prevent SSRF)
ALLOWED_IMAGE_DOMAINS: frozenset[str] = frozenset(
    {
        "lh3.googleusercontent.com",
        "lh4.googleusercontent.com",
        "lh5.googleusercontent.com",
        "lh6.googleusercontent.com",
    }
)


@router.get(
    "/profile-image-proxy",
    summary="Proxy Google profile image",
    description="Proxy endpoint for Google profile images to work with COEP: require-corp. "
    "Only allows images from Google's user content domains (lh3/4/5/6.googleusercontent.com).",
    responses={
        200: {"content": {"image/*": {}}, "description": "Profile image"},
        400: {"description": "Invalid or disallowed URL"},
        502: {"description": "Failed to fetch image from source"},
    },
)
async def proxy_profile_image(
    url: str = Query(..., description="Google profile image URL to proxy"),
    current_user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """
    Proxy Google profile images for COEP compatibility.

    Google's lh3.googleusercontent.com doesn't send CORS headers,
    which breaks images when using COEP: require-corp.
    This proxy fetches the image server-side and returns it with proper headers.

    Security:
    - Only allows URLs from Google's user content domains
    - Requires authentication (prevents abuse)

    Args:
        url: Full URL to the Google profile image
        current_user: Current authenticated user (for rate limiting/auth)

    Returns:
        StreamingResponse with the image data
    """
    user_id = current_user.id

    # Parse and validate URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise_invalid_input("Invalid URL format", url=url[:100] if url else None)

    # Security: Only allow Google image domains
    if parsed.hostname not in ALLOWED_IMAGE_DOMAINS:
        logger.warning(
            "profile_image_proxy_blocked_domain",
            user_id=str(user_id),
            domain=parsed.hostname,
        )
        raise_invalid_input(
            "Domain not allowed. Only Google profile images are supported.",
            domain=parsed.hostname,
        )

    # Security: Only allow HTTPS
    if parsed.scheme != "https":
        raise_invalid_input("Only HTTPS URLs are allowed", scheme=parsed.scheme)

    # Fetch the image
    logger.info(
        "profile_image_proxy_request",
        user_id=str(user_id),
        url=url[:100] if len(url) > 100 else url,
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                follow_redirects=True,
                timeout=settings.http_timeout_external_api,
                headers={
                    "User-Agent": "LIA/1.0",
                },
            )

            # Security: validate final URL after redirects (SSRF prevention)
            final_hostname = urlparse(str(response.url)).hostname
            if final_hostname not in ALLOWED_IMAGE_DOMAINS:
                logger.warning(
                    "profile_image_proxy_redirect_blocked",
                    user_id=str(user_id),
                    original_url=url[:100],
                    final_hostname=final_hostname,
                )
                raise_invalid_input(
                    "Redirect to disallowed domain",
                    domain=final_hostname,
                )

            if response.status_code != 200:
                logger.warning(
                    "profile_image_proxy_fetch_failed",
                    user_id=str(user_id),
                    url=url[:100],
                    status_code=response.status_code,
                )
                raise_external_service_fetch_error(
                    "google_profile_image", "image", response.status_code
                )

            # Get content type from response
            content_type = response.headers.get("content-type", "image/jpeg")

            logger.info(
                "profile_image_proxy_success",
                user_id=str(user_id),
                content_length=len(response.content),
            )

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Cross-Origin-Resource-Policy": "cross-origin",
                    "Cache-Control": "private, max-age=86400",
                },
            )

    except httpx.TimeoutException:
        logger.warning(
            "profile_image_proxy_timeout",
            user_id=str(user_id),
            url=url[:100],
        )
        raise_external_service_connection_error("google_profile_image")
    except httpx.RequestError as e:
        logger.warning(
            "profile_image_proxy_request_error",
            user_id=str(user_id),
            url=url[:100],
            error=str(e),
        )
        raise_external_service_connection_error("google_profile_image")
