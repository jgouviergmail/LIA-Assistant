"""Optional enrichments of a place detail card (2026-08).

Both enrichments here share one contract: they apply to the DETAIL payload
only, mutate it in place, and are strictly fail-quiet — a venue card never
breaks or waits because an optional signal could not be fetched. They live
together (extracted from ``places_tools``, file-size ratchet) because that
contract, not their data source, is what makes them one family.

Street View hero (lot SV) gives a photo-less place an image; air quality
answers "on va au parc cet après-midi ?".

"On va au parc cet après-midi ?" is answered by the air quality AT THE
PLACE, and the detail payload already carries its coordinates. Scope is
deliberately narrow, for cost and for meaning:

- DETAIL only, never a list: enriching ten search results would fire ten
  billed call pairs for a signal nobody asked for;
- air quality only, no pollen: pollen is a REGIONAL daily figure, already
  surfaced on the weather card — repeating it per venue would suggest a
  per-place measurement the API never made.

Reuses the weather enrichment wholesale (same client, same Redis cache keyed
on the coordinate bucket, same fail-quiet contract), so a place near a
previously-seen point costs nothing.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from src.domains.agents.tools.weather_environment_enrichment import (
    environment_extras_or_none,
)

logger = structlog.get_logger(__name__)


async def apply_street_view_fallback(details: dict[str, Any]) -> None:
    """Give a photo-less place a Street View hero when imagery exists (lot SV).

    A place WITH a Places photo never triggers the metadata call. Cheaper too:
    Street View is $2/1000 vs $7/1000 for Place Photos.
    """
    if details.get("photo_url"):
        return
    location = details.get("location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        return
    from src.domains.connectors.street_view import street_view_thumbnail_url

    street_view = await street_view_thumbnail_url(lat, lon)
    if street_view:
        details["photo_url"] = street_view


async def attach_place_air_quality(
    details: dict[str, Any],
    connector_service: Any,
    user_id: UUID,
    language: str,
) -> None:
    """Attach air quality to a place detail payload, in place (fail-quiet).

    Args:
        details: Normalized place details (mutated when data is available).
        connector_service: ConnectorService for the activation check.
        user_id: Owner of the connectors (billing attribution).
        language: User language — the API returns localized categories.
    """
    try:
        location = details.get("location") or {}
        lat, lon = location.get("lat"), location.get("lon")
        if lat is None or lon is None:
            return

        extras = await environment_extras_or_none(
            user_id, connector_service, float(lat), float(lon), language
        )
        if not extras or not extras.get("has_air_quality"):
            return

        details["aqi"] = extras.get("aqi")
        details["aqi_category"] = extras.get("aqi_category", "")
        details["aqi_label"] = extras.get("aqi_label", "")
        details["has_air_quality"] = True
    except Exception as exc:
        # A venue card never fails because air quality could not be read.
        logger.debug("place_air_quality_failed", error=str(exc))
