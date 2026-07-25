"""Google profile-image proxy (COEP: require-corp compatibility).

Extracted from ``auth/router.py`` (file-size ratchet): a single, cohesive
concern — fetching the user's Google avatar server-side because
``lh3.googleusercontent.com`` sends no CORS headers, which breaks images
under our COEP policy.
"""

from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from src.core.config import settings
from src.core.constants import PROFILE_IMAGE_MAX_BYTES, PROFILE_IMAGE_MAX_REDIRECTS
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


def _is_allowed_image_url(candidate: str) -> bool:
    """Whether a URL may be contacted by the proxy.

    Applied to EVERY hop, not just the URL the caller supplied: a redirect is a
    destination we choose to follow, so it deserves the same scrutiny as the
    original request.

    Args:
        candidate: Absolute URL about to be requested.

    Returns:
        True when the URL is HTTPS and its host is in the allowlist.
    """
    parsed = urlparse(candidate)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_IMAGE_DOMAINS


async def _read_bounded(response: httpx.Response) -> bytes:
    """Read a streamed response, refusing to exceed ``PROFILE_IMAGE_MAX_BYTES``.

    ``response.content`` would buffer whatever the remote sends. The host is
    allowlisted, but "trusted not to be malicious" is not "trusted to be
    finite" — a mis-served endpoint answering with a huge body would otherwise
    land entirely in the API's memory.

    Args:
        response: An open streaming response.

    Returns:
        The body bytes.

    Raises:
        BaseAPIException: 400 when the body exceeds the ceiling.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > PROFILE_IMAGE_MAX_BYTES:
            raise_invalid_input("Image too large", max_bytes=PROFILE_IMAGE_MAX_BYTES)
        chunks.append(chunk)
    return b"".join(chunks)


async def _fetch_image_following_redirects(
    client: httpx.AsyncClient,
    url: str,
    *,
    user_id: UUID,
) -> tuple[httpx.Response, bytes]:
    """Fetch an image, validating every hop before it is requested (SEC-026).

    Args:
        client: HTTP client to use.
        url: Already-validated starting URL.
        user_id: Owner, for the audit trail.

    Returns:
        Tuple of (final response, bounded body bytes).

    Raises:
        BaseAPIException: 400 on a disallowed hop, a redirect loop, an
            oversized body, or a non-200 final status.
    """
    current = url

    for _hop in range(PROFILE_IMAGE_MAX_REDIRECTS + 1):
        if not _is_allowed_image_url(current):
            logger.warning(
                "profile_image_proxy_redirect_blocked",
                user_id=str(user_id),
                original_url=url[:100],
                final_hostname=urlparse(current).hostname,
            )
            raise_invalid_input(
                "Redirect to disallowed domain",
                domain=urlparse(current).hostname,
            )

        async with client.stream(
            "GET",
            current,
            follow_redirects=False,
            timeout=settings.http_timeout_external_api,
            headers={"User-Agent": "LIA/1.0"},
        ) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise_invalid_input("Redirect without a destination")
                # Resolve relative redirects against the current URL, exactly as
                # a client would — then loop, so the new target is validated
                # before anything is sent to it.
                current = urljoin(current, location)
                continue

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

            return response, await _read_bounded(response)

    logger.warning(
        "profile_image_proxy_too_many_redirects",
        user_id=str(user_id),
        original_url=url[:100],
        max_redirects=PROFILE_IMAGE_MAX_REDIRECTS,
    )
    raise_invalid_input("Too many redirects", max_redirects=PROFILE_IMAGE_MAX_REDIRECTS)


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
            # SEC-026: follow redirects MANUALLY. With `follow_redirects=True`,
            # httpx walks the whole chain and only then hands back the final
            # response — so the destination was checked *after* it had already
            # been contacted and its body downloaded. Validating each hop before
            # issuing it means a disallowed host is never reached at all.
            response, content = await _fetch_image_following_redirects(client, url, user_id=user_id)

            # Get content type from response
            content_type = response.headers.get("content-type", "image/jpeg")

            logger.info(
                "profile_image_proxy_success",
                user_id=str(user_id),
                content_length=len(content),
            )

            return StreamingResponse(
                iter([content]),
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
