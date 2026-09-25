"""Turning the address the person typed into coordinates.

Extracted from :mod:`service` on 2026-09-07, when recording this read pushed
that module past its shrink-only size cap AND its enclosing function over the
complexity ratchet. Neither cap moves, so the answer is an extraction — and
this is a unit: one question (where is this address?), one paid call, one
failure mode.

**It is a READ, and it is recorded.** The call reaches Google Places through
its CLIENT rather than a tool, so the gate that fills the consultation register
never saw it — and it is a paid Maps call on the DEPLOYMENT's key, made on the
person's own address. The spend goes through the ONE persistence path every
family shares, a ``TrackingContext`` of its own: the direct recorder it used
until 2026-09-20 wrote the usage log and the user statistics but neither the
run's summary row nor the instance's daily ledger — half a ledger. The
tracker keeps its own session on purpose: Google bills a search that finds
nothing, and the request that then answers 400 rolls ITS session back.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import structlog

from src.core.config import settings
from src.core.exceptions import raise_invalid_input
from src.domains.chat.service import TrackingContext

logger = structlog.get_logger(__name__)

#: What the register names this read.
SECTION_GEOCODING = "geocoding"


async def resolve_home_coordinates(
    *,
    user_id: UUID,
    user: Any,
    location: Any,
) -> tuple[float, float, str | None]:
    """Geocode the address when the coordinates say nothing.

    Args:
        user_id: Whose home location is being set.
        user: The account, for its language.
        location: The submitted location (address, lat, lon, place_id).

    Returns:
        ``(latitude, longitude, place_id)`` — the submitted values untouched
        when they were already meaningful.

    Raises:
        HTTPException: When the address cannot be resolved.
    """
    final_lat = location.lat
    final_lon = location.lon
    final_place_id = location.place_id

    if abs(location.lat) < 0.0001 and abs(location.lon) < 0.0001:
        # Coordinates are essentially (0,0) - need geocoding
        logger.info(
            "home_location_geocoding_required",
            user_id=str(user_id),
            has_address=bool(location.address),
        )

        try:
            from src.domains.connectors.clients.google_places_client import (
                GooglePlacesClient,
            )

            places_client = GooglePlacesClient(
                user_id=user_id,
                language=user.language or settings.default_language,
            )

            # Use search_text to geocode the address. Recorded twice over: as
            # a CONSULTATION (it is the person's own address, reached through
            # the client rather than a tool, so the gate never saw it) and as
            # a SPEND (the client records into the tracker opened here).
            _started = perf_counter()
            _geocode_failed = False
            try:
                async with TrackingContext(
                    f"profile_geocoding_{uuid4().hex[:12]}", user_id, "profile_geocoding", None
                ):
                    result = await places_client.search_text(
                        query=location.address,
                        max_results=1,
                        use_cache=False,  # Don't cache geocoding results
                    )
            except Exception:
                _geocode_failed = True
                raise
            finally:
                from src.domains.shared.consultation_surfaces import (
                    record_surface_consultations,
                )

                record_surface_consultations(
                    surface="profile",
                    user_id=user_id,
                    opened=["geocoding"],
                    failed=["geocoding"] if _geocode_failed else (),
                    duration_ms=int((perf_counter() - _started) * 1000),
                )

            places = result.get("places", [])
            if not places:
                raise_invalid_input(
                    f"Could not find location for address: {location.address[:50]}",
                    address=location.address,
                    error="no_results",
                )

            # Extract coordinates from first result
            first_place = places[0]
            place_location = first_place.get("location", {})

            if not place_location.get("latitude") or not place_location.get("longitude"):
                raise_invalid_input(
                    f"Could not geocode address: {location.address[:50]}",
                    address=location.address,
                    error="no_coordinates",
                )

            final_lat = place_location["latitude"]
            final_lon = place_location["longitude"]
            final_place_id = first_place.get("id")

            logger.info(
                "home_location_geocoded",
                user_id=str(user_id),
                lat=final_lat,
                lon=final_lon,
                place_id=final_place_id,
            )

        except Exception as e:
            from fastapi import HTTPException

            if isinstance(e, HTTPException):
                raise  # Re-raise HTTP exceptions (invalid_input, etc.)

            logger.error(
                "home_location_geocoding_failed",
                user_id=str(user_id),
                has_address=bool(location.address),
                error=str(e),
            )
            raise_invalid_input(
                f"Failed to geocode address: {str(e)[:100]}",
                address=location.address,
                error=str(e),
            )

    return final_lat, final_lon, final_place_id
