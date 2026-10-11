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
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
from pydantic import TypeAdapter

from src.core.exceptions import raise_invalid_input
from src.core.i18n import normalize_language
from src.domains.chat.service import TrackingContext
from src.domains.users.models import User
from src.domains.users.schemas import HomeLocationData, HomeLocationUpdate

if TYPE_CHECKING:
    from src.domains.connectors.clients.google_places_client import GooglePlacesClient

logger = structlog.get_logger(__name__)

#: What the register names this read.
SECTION_GEOCODING = "geocoding"


async def _close_owned_client(client: GooglePlacesClient) -> None:
    try:
        await client.close()
    except Exception as exc:
        # Cleanup cannot replace a lookup result or undo its persisted usage.
        logger.warning("home_location_client_close_failed", exception_type=type(exc).__name__)


async def resolve_home_coordinates(
    *,
    user_id: UUID,
    user: User,
    location: HomeLocationUpdate,
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
        from src.infrastructure.llm.usage_guard import enforce_usage_limit

        await enforce_usage_limit(user_id, layer="profile_geocoding")
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
                language=normalize_language(user.language),
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

                try:
                    record_surface_consultations(
                        surface="profile",
                        user_id=user_id,
                        opened=["geocoding"],
                        failed=["geocoding"] if _geocode_failed else (),
                        duration_ms=int((perf_counter() - _started) * 1000),
                    )
                finally:
                    await _close_owned_client(places_client)

            places = result.get("places", [])
            if not places:
                raise_invalid_input(
                    "Could not find the requested home address",
                    error="no_results",
                )

            # Extract coordinates from first result
            first_place = places[0]
            place_location = first_place.get("location", {})

            if place_location.get("latitude") is None or place_location.get("longitude") is None:
                raise_invalid_input(
                    "Could not resolve home coordinates",
                    error="no_coordinates",
                )

            numeric = TypeAdapter(float)
            resolved = HomeLocationData(
                address=location.address,
                lat=numeric.validate_python(place_location["latitude"], strict=True),
                lon=numeric.validate_python(place_location["longitude"], strict=True),
                place_id=first_place.get("id"),
            )
            final_lat, final_lon, final_place_id = resolved.lat, resolved.lon, resolved.place_id

            logger.info(
                "home_location_geocoded",
                user_id=str(user_id),
                has_coordinates=True,
            )

        except Exception as e:
            from fastapi import HTTPException

            if isinstance(e, HTTPException):
                raise  # Re-raise HTTP exceptions (invalid_input, etc.)

            logger.error(
                "home_location_geocoding_failed",
                user_id=str(user_id),
                has_address=bool(location.address),
                exception_type=type(e).__name__,
            )
            raise_invalid_input(
                "Home address resolution failed",
                error="geocoding_failed",
            )

    return final_lat, final_lon, final_place_id
