"""User location service — persistence and cascade for weather notifications.

Implements the Phase 3 last-known location feature:
- Opt-in persistence of browser geolocation (encrypted, non-historized)
- Throttled updates (30 min floor between writes per user)
- Cascade resolution for proactive jobs: last_known (fresh + far) -> home
- Auto-wipe on opt-out or home deletion

All coordinates are encrypted at rest (Fernet, same key as home location).
Logs never contain raw lat/lon — only bucketed distance classes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    LAST_KNOWN_LOCATION_UPDATE_THROTTLE_MINUTES,
)
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.utils.distance import _haversine_distance
from src.domains.auth.models import User
from src.infrastructure.observability.metrics_heartbeat import (
    user_location_put_total,
)

logger = structlog.get_logger(__name__)


class NoLocationAvailableError(Exception):
    """Raised when no usable location can be resolved (no home, no last-known)."""


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """Outcome of an update_last_known_location call."""

    updated: bool
    throttled: bool
    forbidden: bool


@dataclass(frozen=True, slots=True)
class LastKnownLocation:
    """Decrypted last-known location view."""

    lat: float
    lon: float
    accuracy: float | None
    updated_at: datetime
    stale: bool


@dataclass(frozen=True, slots=True)
class EffectiveLocation:
    """Location resolved by the proactive cascade."""

    lat: float
    lon: float
    source: str  # "home" | "last_known"


def _distance_bucket(distance_km: float) -> str:
    """Bucket a distance (km) into a coarse class for observability.

    Exposing raw distance values in logs could aid re-identification when
    combined with other metadata, so we bucket.
    """
    if distance_km < 10:
        return "<10km"
    if distance_km < 50:
        return "10-50km"
    if distance_km < 100:
        return "50-100km"
    if distance_km < 500:
        return "100-500km"
    if distance_km < 1000:
        return "500-1000km"
    return ">=1000km"


def _decrypt_home_coords(user: User) -> tuple[float, float] | None:
    """Decrypt the user's home location and return (lat, lon), or None.

    Home is stored as JSON {address, lat, lon, place_id} (see user model).
    Returns None if home is not set or decryption fails.
    """
    if not user.home_location_encrypted:
        return None
    try:
        payload = json.loads(decrypt_data(user.home_location_encrypted))
    except (ValueError, json.JSONDecodeError):
        logger.warning("home_location_decrypt_failed", user_id=str(user.id))
        return None
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        return None
    return float(lat), float(lon)


def _decrypt_last_known_coords(user: User) -> tuple[float, float, float | None] | None:
    """Decrypt the user's last-known location and return (lat, lon, accuracy).

    Returns None if field is empty or decryption fails.
    """
    if not user.last_known_location_encrypted:
        return None
    try:
        payload = json.loads(decrypt_data(user.last_known_location_encrypted))
    except (ValueError, json.JSONDecodeError):
        logger.warning("last_known_location_decrypt_failed", user_id=str(user.id))
        return None
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        return None
    accuracy = payload.get("accuracy")
    return float(lat), float(lon), float(accuracy) if accuracy is not None else None


class UserLocationService:
    """Service for managing user last-known location and proactive cascade."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def update_last_known_location(
        self,
        user: User,
        lat: float,
        lon: float,
        accuracy: float | None,
    ) -> UpdateResult:
        """Persist a new last-known location for the user.

        Enforces opt-in and a 30-minute throttle between writes for the same
        user. The stored payload is a Fernet-encrypted JSON
        `{lat, lon, accuracy}` with a UTC timestamp kept separately in
        `last_known_location_updated_at`.

        Args:
            user: The authenticated user whose location is being updated.
            lat: Latitude (-90, 90).
            lon: Longitude (-180, 180).
            accuracy: Optional accuracy in meters (non-negative).

        Returns:
            An ``UpdateResult`` describing the outcome (updated / throttled /
            forbidden). ``forbidden`` is set when the user has not opted in.
        """
        if not user.weather_use_last_known_location:
            logger.info(
                "last_known_location_update_forbidden",
                user_id=str(user.id),
                reason="opt_out",
            )
            user_location_put_total.labels(result="forbidden").inc()
            return UpdateResult(updated=False, throttled=False, forbidden=True)

        now = datetime.now(UTC)
        previous = user.last_known_location_updated_at
        if previous is not None:
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=UTC)
            elapsed = now - previous
            throttle = timedelta(minutes=LAST_KNOWN_LOCATION_UPDATE_THROTTLE_MINUTES)
            if elapsed < throttle:
                logger.info(
                    "last_known_location_update_throttled",
                    user_id=str(user.id),
                    elapsed_seconds=int(elapsed.total_seconds()),
                )
                user_location_put_total.labels(result="throttled").inc()
                return UpdateResult(updated=False, throttled=True, forbidden=False)

        payload: dict[str, Any] = {"lat": lat, "lon": lon}
        if accuracy is not None:
            payload["accuracy"] = accuracy
        user.last_known_location_encrypted = encrypt_data(json.dumps(payload))
        user.last_known_location_updated_at = now
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)

        logger.info(
            "last_known_location_updated",
            user_id=str(user.id),
            has_accuracy=accuracy is not None,
        )
        user_location_put_total.labels(result="accepted").inc()
        return UpdateResult(updated=True, throttled=False, forbidden=False)

    async def get_last_known_location(self, user: User) -> LastKnownLocation | None:
        """Return the decrypted last-known location, or ``None`` if absent.

        The ``stale`` flag is based on the configured TTL
        (``settings.last_known_location_ttl_hours``).
        """
        coords = _decrypt_last_known_coords(user)
        if coords is None or user.last_known_location_updated_at is None:
            return None
        lat, lon, accuracy = coords

        updated_at = user.last_known_location_updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        ttl = timedelta(hours=settings.last_known_location_ttl_hours)
        stale = (datetime.now(UTC) - updated_at) > ttl

        return LastKnownLocation(
            lat=lat,
            lon=lon,
            accuracy=accuracy,
            updated_at=updated_at,
            stale=stale,
        )

    async def wipe_last_known_location(self, user: User) -> None:
        """Clear the persisted last-known location for the user.

        Called on opt-out and when the user deletes their home address.
        Idempotent — safe to call when nothing is stored.
        """
        if (
            user.last_known_location_encrypted is None
            and user.last_known_location_updated_at is None
        ):
            return

        user.last_known_location_encrypted = None
        user.last_known_location_updated_at = None
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)

        logger.info("last_known_location_wiped", user_id=str(user.id))

    async def get_effective_location_for_proactive(
        self,
        user: User,
    ) -> EffectiveLocation:
        """Resolve the location to use for a proactive notification.

        Cascade:
            1. If opt-in AND last-known exists AND fresh (< TTL) AND
               distance from home > threshold -> use last-known.
            2. Otherwise -> use home.

        Home is required as a baseline: without it, the cascade cannot
        decide whether the last-known position is "far enough" to prefer.
        Reads configuration from the module-level ``settings`` singleton
        so the cascade is internally consistent with ``get_last_known_location``.

        Raises:
            NoLocationAvailableError: if the user has no home location.
        """
        home_coords = _decrypt_home_coords(user)
        if home_coords is None:
            raise NoLocationAvailableError("User has no home location configured")

        home_lat, home_lon = home_coords

        if not user.weather_use_last_known_location:
            return EffectiveLocation(lat=home_lat, lon=home_lon, source="home")

        last_known = await self.get_last_known_location(user)
        if last_known is None or last_known.stale:
            return EffectiveLocation(lat=home_lat, lon=home_lon, source="home")

        distance_km = _haversine_distance(last_known.lat, last_known.lon, home_lat, home_lon)
        if distance_km < settings.last_known_location_min_distance_km:
            logger.debug(
                "proactive_location_home_preferred_close",
                user_id=str(user.id),
                distance_bucket=_distance_bucket(distance_km),
            )
            return EffectiveLocation(lat=home_lat, lon=home_lon, source="home")

        logger.info(
            "proactive_location_last_known_used",
            user_id=str(user.id),
            distance_bucket=_distance_bucket(distance_km),
        )
        return EffectiveLocation(
            lat=last_known.lat,
            lon=last_known.lon,
            source="last_known",
        )


async def update_user_location_fire_and_forget(
    user_id: Any,
    lat: float,
    lon: float,
    accuracy: float | None,
) -> None:
    """Update the user's last-known location outside the request lifecycle.

    Used by the chat streaming endpoint to persist the browser geolocation
    without blocking the response. Any failure is logged and swallowed —
    this must never break the chat UX.

    Performs a silent opt-in pre-check so users who never enabled the
    feature do not pollute the ``user_location_put_total{result="forbidden"}``
    counter. ``forbidden`` in the counter is then reserved for explicit
    PUT /me/last-location abuse attempts, which is the actionable signal.

    Args:
        user_id: The user's UUID (stringifiable).
        lat: Latitude.
        lon: Longitude.
        accuracy: Optional accuracy in meters.
    """
    from src.infrastructure.database import get_db_context

    try:
        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if user is None or not user.weather_use_last_known_location:
                return  # silent opt-out skip — no metric pollution
            service = UserLocationService(db)
            await service.update_last_known_location(user, lat, lon, accuracy)
    except Exception:
        logger.exception(
            "last_known_location_background_update_failed",
            user_id=str(user_id),
        )
