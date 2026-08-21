"""Street View Static thumbnail availability (lot SV, 2026-08).

"What does the entrance look like?" — location and place cards can show a
Street View thumbnail. The METADATA endpoint is free and answers whether
imagery exists at a point; only when it does is the (authenticated, billed)
proxy URL handed to a card — so a card never renders a broken or grey
placeholder image, and nothing is billed for places without coverage.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from src.core.config import settings
from src.core.constants import STREET_VIEW_METADATA_URL
from src.domains.connectors.clients.google_api_tracker import track_google_api_call

logger = structlog.get_logger(__name__)


def _street_view_enabled() -> bool:
    """Street View needs both the feature flag and the platform API key."""
    return bool(getattr(settings, "street_view_enabled", False) and settings.google_api_key)


async def _fetch_metadata(lat: float, lon: float) -> dict[str, Any]:
    """Call the free Street View metadata endpoint for one point."""
    params = {
        "location": f"{lat},{lon}",
        "key": settings.google_api_key,
    }
    async with httpx.AsyncClient(timeout=settings.http_timeout_connector_standard) as client:
        response = await client.get(STREET_VIEW_METADATA_URL, params=params)
        response.raise_for_status()
        return dict(response.json())


async def street_view_thumbnail_url(lat: float, lon: float) -> str | None:
    """Proxy URL for a Street View thumbnail, or None when unavailable.

    Fail-quiet: any metadata failure just means "no thumbnail" — a card
    must never break because Street View is down or disabled.

    Args:
        lat: Latitude of the point.
        lon: Longitude of the point.

    Returns:
        The authenticated proxy URL when imagery exists, None otherwise.
    """
    if not _street_view_enabled():
        return None
    try:
        metadata = await _fetch_metadata(lat, lon)
    except Exception as exc:
        logger.warning("street_view_metadata_failed", error=str(exc))
        return None
    # Metadata requests are free — tracked at $0 for observability only.
    track_google_api_call("street_view", "/streetview/metadata", cached=False)
    if metadata.get("status") != "OK":
        return None
    return f"/api/v1/connectors/street-view?location={lat},{lon}"
