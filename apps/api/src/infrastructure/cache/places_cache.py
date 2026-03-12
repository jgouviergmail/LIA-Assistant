"""
Redis cache for Google Places data.
Reduces API calls and improves response time for frequent queries.

V2 Features (Freshness Transparency):
- Metadata wrapper with cached_at timestamp (ISO 8601 UTC)
- Returns (data, from_cache, cached_at, cache_age_seconds) tuple
- Precise cache age calculation for UX transparency
"""

import json
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.core.config import get_settings

from .base import (
    create_cache_entry,
    make_payload_hash,
    make_resource_key,
    parse_cache_entry,
    record_cache_miss,
    sanitize_key_part,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


class PlacesCache:
    """
    Redis-based cache for Google Places queries.

    Cache strategies:
    - Search places: 5 min TTL (default)
    - Nearby places: 5 min TTL (default)
    - Place details: 5 min TTL (default)

    Cache invalidation:
    - Automatic TTL expiration
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        """
        Initialize places cache.

        Args:
            redis_client: Redis async client.
        """
        self.redis = redis_client

    def _make_search_key(
        self,
        user_id: UUID,
        query: str,
        include_type: str | None = None,
        open_now: bool | None = None,
        location_bias: dict[str, Any] | None = None,
        min_rating: float | None = None,
        price_levels: list[str] | None = None,
    ) -> str:
        """
        Generate cache key for search_text.

        Args:
            user_id: User UUID.
            query: Search query string.
            include_type: Optional type filter.
            open_now: Optional open_now filter.
            location_bias: Optional location bias.
            min_rating: Optional minimum rating filter.
            price_levels: Optional price level filter.

        Returns:
            Cache key with robust hash.
        """
        # Create composite key payload for hashing
        key_payload = {
            "q": query.lower().strip(),
            "type": include_type,
            "open": open_now,
            "bias": location_bias,
            "min_rating": min_rating,
            "price_levels": sorted(price_levels) if price_levels else None,
        }

        # Hash payload using centralized helper
        query_hash = make_payload_hash(key_payload, length=16)

        # Sanitized query prefix for readability (uniqueness from hash)
        query_prefix = sanitize_key_part(query, max_length=20) or "query"

        return f"places_search:{user_id}:{query_prefix}:{query_hash}"

    def _make_nearby_key(self, user_id: UUID, lat: float, lon: float, radius: int) -> str:
        """
        Generate cache key for search_nearby.

        Args:
            user_id: User UUID.
            lat: Latitude.
            lon: Longitude.
            radius: Radius in meters.

        Returns:
            Cache key.
        """
        # Round coordinates to ~11m precision (4 decimal places) to improve cache hit rate
        lat_rounded = round(lat, 4)
        lon_rounded = round(lon, 4)
        return f"places_nearby:{user_id}:{lat_rounded}:{lon_rounded}:{radius}"

    def _make_details_key(self, user_id: UUID, place_id: str) -> str:
        """Generate cache key for get_place_details."""
        return make_resource_key("places_details", user_id, place_id)

    async def get_search(
        self,
        user_id: UUID,
        query: str,
        include_type: str | None = None,
        open_now: bool | None = None,
        location_bias: dict[str, Any] | None = None,
        min_rating: float | None = None,
        price_levels: list[str] | None = None,
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached search results with metadata.

        Args:
            user_id: User UUID.
            query: Search query string.
            include_type: Optional type filter.
            open_now: Optional open_now filter.
            location_bias: Optional location bias.
            min_rating: Optional minimum rating filter.
            price_levels: Optional price level filter.

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds).
        """
        key = self._make_search_key(
            user_id, query, include_type, open_now, location_bias, min_rating, price_levels
        )
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    "places_search",
                    {"user_id": str(user_id), "query_preview": query[:20]},
                )
                if result.from_cache:
                    logger.debug(
                        "places_cache_hit",
                        cache_type="search",
                        user_id=str(user_id),
                        query_preview=query[:20],
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug(
                "places_cache_miss",
                cache_type="search",
                user_id=str(user_id),
                query_preview=query[:20],
            )
            record_cache_miss("places_search")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "places_cache_get_failed",
                cache_type="search",
                user_id=str(user_id),
                error=str(e),
            )
            return None, False, None, None

    async def set_search(
        self,
        user_id: UUID,
        query: str,
        data: dict[str, Any],
        include_type: str | None = None,
        open_now: bool | None = None,
        location_bias: dict[str, Any] | None = None,
        min_rating: float | None = None,
        price_levels: list[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Cache search results with metadata wrapper.

        Args:
            user_id: User UUID.
            query: Search query string.
            data: Search results to cache.
            include_type: Optional type filter.
            open_now: Optional open_now filter.
            location_bias: Optional location bias.
            min_rating: Optional minimum rating filter.
            price_levels: Optional price level filter.
            ttl_seconds: Time-to-live in seconds.
        """
        if ttl_seconds is None:
            ttl_seconds = settings.get_connector_cache_ttl("google_places_search")

        key = self._make_search_key(
            user_id, query, include_type, open_now, location_bias, min_rating, price_levels
        )
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "places_cache_set",
                cache_type="search",
                user_id=str(user_id),
                query_preview=query[:20],
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "places_cache_set_failed",
                cache_type="search",
                user_id=str(user_id),
                error=str(e),
            )

    async def get_nearby(
        self, user_id: UUID, lat: float, lon: float, radius: int
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached nearby search results with metadata.

        Args:
            user_id: User UUID.
            lat: Latitude.
            lon: Longitude.
            radius: Radius in meters.

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds).
        """
        key = self._make_nearby_key(user_id, lat, lon, radius)
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    "places_nearby",
                    {"user_id": str(user_id), "lat": lat, "lon": lon, "radius": radius},
                )
                if result.from_cache:
                    logger.debug(
                        "places_cache_hit",
                        cache_type="nearby",
                        user_id=str(user_id),
                        lat=lat,
                        lon=lon,
                        radius=radius,
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug(
                "places_cache_miss",
                cache_type="nearby",
                user_id=str(user_id),
                lat=lat,
                lon=lon,
                radius=radius,
            )
            record_cache_miss("places_nearby")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "places_cache_get_failed",
                cache_type="nearby",
                user_id=str(user_id),
                error=str(e),
            )
            return None, False, None, None

    async def set_nearby(
        self,
        user_id: UUID,
        lat: float,
        lon: float,
        radius: int,
        data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Cache nearby search results.

        Args:
            user_id: User UUID.
            lat: Latitude.
            lon: Longitude.
            radius: Radius in meters.
            data: Results to cache.
            ttl_seconds: Time-to-live in seconds.
        """
        if ttl_seconds is None:
            ttl_seconds = settings.get_connector_cache_ttl("google_places_nearby")

        key = self._make_nearby_key(user_id, lat, lon, radius)
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "places_cache_set",
                cache_type="nearby",
                user_id=str(user_id),
                lat=lat,
                lon=lon,
                radius=radius,
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "places_cache_set_failed",
                cache_type="nearby",
                user_id=str(user_id),
                error=str(e),
            )

    async def get_details(
        self, user_id: UUID, place_id: str
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached place details with metadata.

        Args:
            user_id: User UUID.
            place_id: Google Place ID.

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds).
        """
        key = self._make_details_key(user_id, place_id)
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    "places_details",
                    {"user_id": str(user_id), "place_id": place_id},
                )
                if result.from_cache:
                    logger.debug(
                        "places_cache_hit",
                        cache_type="details",
                        user_id=str(user_id),
                        place_id=place_id,
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug(
                "places_cache_miss",
                cache_type="details",
                user_id=str(user_id),
                place_id=place_id,
            )
            record_cache_miss("places_details")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "places_cache_get_failed",
                cache_type="details",
                user_id=str(user_id),
                error=str(e),
            )
            return None, False, None, None

    async def set_details(
        self,
        user_id: UUID,
        place_id: str,
        data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Cache place details.

        Args:
            user_id: User UUID.
            place_id: Google Place ID.
            data: Details to cache.
            ttl_seconds: Time-to-live in seconds.
        """
        if ttl_seconds is None:
            ttl_seconds = settings.get_connector_cache_ttl("google_places_details")

        key = self._make_details_key(user_id, place_id)
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "places_cache_set",
                cache_type="details",
                user_id=str(user_id),
                place_id=place_id,
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "places_cache_set_failed",
                cache_type="details",
                user_id=str(user_id),
                error=str(e),
            )
