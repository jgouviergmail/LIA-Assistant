"""
Redis cache for Google Routes API data.
Reduces API calls and improves response time for frequent route queries.

Cache Strategy:
- Routes with traffic: 5 min TTL (ROUTES_CACHE_TTL_SECONDS)
- Route matrix: 10 min TTL (ROUTES_MATRIX_CACHE_TTL_SECONDS)
- Static routes (no traffic): 30 min TTL

Note: Routes API uses global API key, so cache keys are NOT user-specific.
This allows cache sharing across users for the same routes.
"""

import json
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
import structlog

from src.core.config import get_settings

from .base import (
    create_cache_entry,
    make_payload_hash,
    parse_cache_entry,
    record_cache_miss,
    sanitize_key_part,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Note: TTL defaults are now configurable via settings:
# - settings.routes_cache_traffic_ttl_seconds (default: 300 = 5 minutes)
# - settings.routes_cache_static_ttl_seconds (default: 1800 = 30 minutes)
# - settings.routes_cache_matrix_ttl_seconds (default: 600 = 10 minutes)


class RoutesCache:
    """
    Redis-based cache for Google Routes API queries.

    Cache strategies:
    - Route computation (traffic): 5 min TTL
    - Route computation (static): 30 min TTL
    - Route matrix: 10 min TTL

    Cache keys are NOT user-specific (global API key).
    This improves cache hit rate for common routes.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        """
        Initialize routes cache.

        Args:
            redis_client: Redis async client.
        """
        self.redis = redis_client

    def _make_route_key(
        self,
        origin: str,
        destination: str,
        travel_mode: str,
        avoid_tolls: bool = False,
        avoid_highways: bool = False,
        avoid_ferries: bool = False,
        departure_time: str | None = None,
        arrival_time: str | None = None,
    ) -> str:
        """
        Generate cache key for route computation.

        Args:
            origin: Origin address/coordinates.
            destination: Destination address/coordinates.
            travel_mode: DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER.
            avoid_tolls: Avoid toll roads flag.
            avoid_highways: Avoid highways flag.
            avoid_ferries: Avoid ferries flag.
            departure_time: Optional departure time (affects traffic).
            arrival_time: Optional arrival time (for TRANSIT mode with arrivalTime).

        Returns:
            Cache key with robust hash.
        """
        # Normalize origin/destination for better cache hits
        origin_normalized = self._normalize_location(origin)
        dest_normalized = self._normalize_location(destination)

        # Create composite key payload
        # Note: arrival_time creates a different cache key than departure_time
        # because the route calculation is fundamentally different
        key_payload = {
            "origin": origin_normalized,
            "destination": dest_normalized,
            "mode": travel_mode,
            "avoid_tolls": avoid_tolls,
            "avoid_highways": avoid_highways,
            "avoid_ferries": avoid_ferries,
            # Note: times are truncated to hour for better cache hits
            "departure_hour": (
                self._truncate_time_to_hour(departure_time) if departure_time else None
            ),
            "arrival_hour": (self._truncate_time_to_hour(arrival_time) if arrival_time else None),
        }

        # Hash payload using centralized helper
        payload_hash = make_payload_hash(key_payload, length=16)

        # Create readable prefix using centralized helper
        origin_prefix = sanitize_key_part(origin_normalized, max_length=15)
        dest_prefix = sanitize_key_part(dest_normalized, max_length=15)

        return f"routes:route:{origin_prefix}_{dest_prefix}:{travel_mode}:{payload_hash}"

    def _make_matrix_key(
        self,
        origins: list[str],
        destinations: list[str],
        travel_mode: str,
    ) -> str:
        """
        Generate cache key for route matrix computation.

        Args:
            origins: List of origin addresses/coordinates.
            destinations: List of destination addresses/coordinates.
            travel_mode: Transport mode.

        Returns:
            Cache key with robust hash.
        """
        # Normalize and sort for consistent cache keys
        origins_normalized = sorted([self._normalize_location(o) for o in origins])
        destinations_normalized = sorted([self._normalize_location(d) for d in destinations])

        key_payload = {
            "origins": origins_normalized,
            "destinations": destinations_normalized,
            "mode": travel_mode,
        }

        # Hash payload using centralized helper
        payload_hash = make_payload_hash(key_payload, length=16)

        return f"routes:matrix:{len(origins)}x{len(destinations)}:{travel_mode}:{payload_hash}"

    def _normalize_location(self, location: str | dict) -> str:
        """
        Normalize location for cache key consistency.

        Args:
            location: Address string or coordinates dict.

        Returns:
            Normalized string representation.
        """
        if isinstance(location, dict):
            if "lat" in location and "lon" in location:
                # Round coordinates to 4 decimal places (~11m precision)
                return f"{round(location['lat'], 4)},{round(location['lon'], 4)}"
            elif "latitude" in location and "longitude" in location:
                return f"{round(location['latitude'], 4)},{round(location['longitude'], 4)}"
            elif "address" in location:
                return location["address"].lower().strip()  # type: ignore[no-any-return]
            return json.dumps(location, sort_keys=True)
        return str(location).lower().strip()

    def _truncate_time_to_hour(self, iso_time: str) -> str:
        """
        Truncate ISO time to hour for cache grouping.

        This improves cache hits for similar departure times.

        Args:
            iso_time: ISO 8601 timestamp.

        Returns:
            Hour-truncated timestamp.
        """
        try:
            dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
            return dt.replace(minute=0, second=0, microsecond=0).isoformat()
        except Exception:
            logger.warning(
                "route_cache_time_truncation_failed",
                iso_time=iso_time,
                exc_info=True,
            )
            return iso_time

    # =========================================================================
    # ROUTE CACHE OPERATIONS
    # =========================================================================

    async def get_route(
        self,
        origin: str | dict,
        destination: str | dict,
        travel_mode: str,
        avoid_tolls: bool = False,
        avoid_highways: bool = False,
        avoid_ferries: bool = False,
        departure_time: str | None = None,
        arrival_time: str | None = None,
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached route result.

        Args:
            origin: Origin address/coordinates.
            destination: Destination address/coordinates.
            travel_mode: Transport mode.
            avoid_tolls: Avoid toll roads.
            avoid_highways: Avoid highways.
            avoid_ferries: Avoid ferries.
            departure_time: Departure time for traffic.
            arrival_time: Arrival time (for TRANSIT mode with arrivalTime).

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds).
        """
        origin_str = self._normalize_location(origin)
        dest_str = self._normalize_location(destination)

        key = self._make_route_key(
            origin_str,
            dest_str,
            travel_mode,
            avoid_tolls,
            avoid_highways,
            avoid_ferries,
            departure_time,
            arrival_time,
        )

        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    "routes_route",
                    {
                        "origin": origin_str[:30],
                        "destination": dest_str[:30],
                        "travel_mode": travel_mode,
                    },
                )
                if result.from_cache:
                    logger.debug(
                        "routes_cache_hit",
                        cache_type="route",
                        origin=origin_str[:30],
                        destination=dest_str[:30],
                        travel_mode=travel_mode,
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug(
                "routes_cache_miss",
                cache_type="route",
                origin=origin_str[:30],
                destination=dest_str[:30],
                travel_mode=travel_mode,
            )
            record_cache_miss("routes_route")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "routes_cache_get_failed",
                cache_type="route",
                error=str(e),
            )
            return None, False, None, None

    async def set_route(
        self,
        origin: str | dict,
        destination: str | dict,
        travel_mode: str,
        data: dict[str, Any],
        avoid_tolls: bool = False,
        avoid_highways: bool = False,
        avoid_ferries: bool = False,
        departure_time: str | None = None,
        arrival_time: str | None = None,
        is_traffic_aware: bool = True,
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Cache route result.

        Args:
            origin: Origin address/coordinates.
            destination: Destination address/coordinates.
            travel_mode: Transport mode.
            data: Route result to cache.
            avoid_tolls: Avoid toll roads.
            avoid_highways: Avoid highways.
            avoid_ferries: Avoid ferries.
            departure_time: Departure time for traffic.
            arrival_time: Arrival time (for TRANSIT mode with arrivalTime).
            is_traffic_aware: Whether route includes traffic data (shorter TTL).
            ttl_seconds: Custom TTL (optional).
        """
        if ttl_seconds is None:
            if is_traffic_aware:
                ttl_seconds = settings.routes_cache_traffic_ttl_seconds
            else:
                ttl_seconds = settings.routes_cache_static_ttl_seconds

        origin_str = self._normalize_location(origin)
        dest_str = self._normalize_location(destination)

        key = self._make_route_key(
            origin_str,
            dest_str,
            travel_mode,
            avoid_tolls,
            avoid_highways,
            avoid_ferries,
            departure_time,
            arrival_time,
        )

        try:
            # Include metadata in data for MyPy compatibility with CacheEntryV2
            enriched_data = {**data, "_is_traffic_aware": is_traffic_aware}
            cache_entry = create_cache_entry(enriched_data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "routes_cache_set",
                cache_type="route",
                origin=origin_str[:30],
                destination=dest_str[:30],
                travel_mode=travel_mode,
                ttl_seconds=ttl_seconds,
                is_traffic_aware=is_traffic_aware,
            )

        except Exception as e:
            logger.warning(
                "routes_cache_set_failed",
                cache_type="route",
                error=str(e),
            )

    # =========================================================================
    # MATRIX CACHE OPERATIONS
    # =========================================================================

    async def get_matrix(
        self,
        origins: list[str | dict],
        destinations: list[str | dict],
        travel_mode: str,
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached route matrix result.

        Args:
            origins: List of origins.
            destinations: List of destinations.
            travel_mode: Transport mode.

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds).
        """
        origins_str = [self._normalize_location(o) for o in origins]
        destinations_str = [self._normalize_location(d) for d in destinations]

        key = self._make_matrix_key(origins_str, destinations_str, travel_mode)

        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    "routes_matrix",
                    {
                        "origins_count": len(origins),
                        "destinations_count": len(destinations),
                        "travel_mode": travel_mode,
                    },
                )
                if result.from_cache:
                    logger.debug(
                        "routes_cache_hit",
                        cache_type="matrix",
                        origins_count=len(origins),
                        destinations_count=len(destinations),
                        travel_mode=travel_mode,
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug(
                "routes_cache_miss",
                cache_type="matrix",
                origins_count=len(origins),
                destinations_count=len(destinations),
                travel_mode=travel_mode,
            )
            record_cache_miss("routes_matrix")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "routes_cache_get_failed",
                cache_type="matrix",
                error=str(e),
            )
            return None, False, None, None

    async def set_matrix(
        self,
        origins: list[str | dict],
        destinations: list[str | dict],
        travel_mode: str,
        data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Cache route matrix result.

        Args:
            origins: List of origins.
            destinations: List of destinations.
            travel_mode: Transport mode.
            data: Matrix result to cache.
            ttl_seconds: Custom TTL (optional).
        """
        if ttl_seconds is None:
            ttl_seconds = settings.routes_cache_matrix_ttl_seconds

        origins_str = [self._normalize_location(o) for o in origins]
        destinations_str = [self._normalize_location(d) for d in destinations]

        key = self._make_matrix_key(origins_str, destinations_str, travel_mode)

        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "routes_cache_set",
                cache_type="matrix",
                origins_count=len(origins),
                destinations_count=len(destinations),
                travel_mode=travel_mode,
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "routes_cache_set_failed",
                cache_type="matrix",
                error=str(e),
            )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "RoutesCache",
]
