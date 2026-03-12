"""
Redis cache for Google Contacts data.
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
    make_resource_key,
    make_search_key,
    make_user_key,
    parse_cache_entry,
    record_cache_miss,
)

logger = structlog.get_logger(__name__)
settings = get_settings()


class ContactsCache:
    """
    Redis-based cache for Google Contacts queries.

    Cache strategies:
    - List contacts: 5 min TTL (relatively stable data)
    - Search contacts: 3 min TTL (query-specific)
    - Contact details: 5 min TTL (specific person data)

    Cache invalidation:
    - Manual invalidation on contact create/update/delete (future)
    - Automatic TTL expiration
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        """
        Initialize contacts cache.

        Args:
            redis_client: Redis async client.
        """
        self.redis = redis_client

    def _make_list_key(self, user_id: UUID) -> str:
        """Generate cache key for list_contacts."""
        return make_user_key("contacts_list", user_id)

    def _make_search_key(self, user_id: UUID, query: str) -> str:
        """
        Generate cache key for search_contacts.

        Args:
            user_id: User UUID.
            query: Search query string.

        Returns:
            Cache key with query hash.
        """
        return make_search_key("contacts_search", user_id, query)

    def _make_details_key(self, user_id: UUID, resource_name: str) -> str:
        """Generate cache key for get_contact_details."""
        return make_resource_key("contacts_details", user_id, resource_name)

    async def get_list(
        self, user_id: UUID
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached list of contacts with metadata.

        Args:
            user_id: User UUID.

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds):
            - data: Cached contacts data or None if not found
            - from_cache: True if cache hit, False if miss
            - cached_at: ISO 8601 timestamp when cached (UTC), or None
            - cache_age_seconds: Age of cache in seconds, or None

        Example:
            >>> data, from_cache, cached_at, age = await cache.get_list(user_id)
            >>> if from_cache:
            >>>     print(f"Cache hit (age: {age}s)")
        """
        key = self._make_list_key(user_id)
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(cached, "contacts_list", {"user_id": str(user_id)})
                if result.from_cache:
                    logger.debug(
                        "contacts_cache_hit",
                        cache_type="list",
                        user_id=str(user_id),
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug("contacts_cache_miss", cache_type="list", user_id=str(user_id))
            record_cache_miss("contacts_list")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "contacts_cache_get_failed",
                cache_type="list",
                user_id=str(user_id),
                error=str(e),
            )
            return None, False, None, None

    async def set_list(
        self, user_id: UUID, data: dict[str, Any], ttl_seconds: int | None = None
    ) -> None:
        """
        Cache list of contacts with metadata wrapper (V2 format).

        Args:
            user_id: User UUID.
            data: Contacts data to cache.
            ttl_seconds: Time-to-live in seconds (default 5 min).
        """
        if ttl_seconds is None:
            ttl_seconds = settings.contacts_cache_list_ttl_seconds

        key = self._make_list_key(user_id)
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "contacts_cache_set",
                cache_type="list",
                user_id=str(user_id),
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "contacts_cache_set_failed",
                cache_type="list",
                user_id=str(user_id),
                error=str(e),
            )

    async def get_search(
        self, user_id: UUID, query: str
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached search results with metadata.

        Args:
            user_id: User UUID.
            query: Search query string.

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds).
        """
        key = self._make_search_key(user_id, query)
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    "contacts_search",
                    {"user_id": str(user_id), "query_preview": query[:20]},
                )
                if result.from_cache:
                    logger.debug(
                        "contacts_cache_hit",
                        cache_type="search",
                        user_id=str(user_id),
                        query_preview=query[:20],
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug(
                "contacts_cache_miss",
                cache_type="search",
                user_id=str(user_id),
                query_preview=query[:20],
            )
            record_cache_miss("contacts_search")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "contacts_cache_get_failed",
                cache_type="search",
                user_id=str(user_id),
                error=str(e),
            )
            return None, False, None, None

    async def set_search(
        self, user_id: UUID, query: str, data: dict[str, Any], ttl_seconds: int | None = None
    ) -> None:
        """
        Cache search results with metadata wrapper (V2 format).

        Args:
            user_id: User UUID.
            query: Search query string.
            data: Search results to cache.
            ttl_seconds: Time-to-live in seconds (default 3 min).
        """
        if ttl_seconds is None:
            ttl_seconds = settings.contacts_cache_search_ttl_seconds

        key = self._make_search_key(user_id, query)
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "contacts_cache_set",
                cache_type="search",
                user_id=str(user_id),
                query_preview=query[:20],
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "contacts_cache_set_failed",
                cache_type="search",
                user_id=str(user_id),
                error=str(e),
            )

    async def get_details(
        self, user_id: UUID, resource_name: str
    ) -> tuple[dict[str, Any] | None, bool, str | None, int | None]:
        """
        Get cached contact details with metadata.

        Args:
            user_id: User UUID.
            resource_name: Google resource name (e.g., people/c123...).

        Returns:
            Tuple of (data, from_cache, cached_at, cache_age_seconds).
        """
        key = self._make_details_key(user_id, resource_name)
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    "contacts_details",
                    {"user_id": str(user_id), "resource_name": resource_name},
                )
                if result.from_cache:
                    logger.debug(
                        "contacts_cache_hit",
                        cache_type="details",
                        user_id=str(user_id),
                        resource_name=resource_name,
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result.as_tuple()

            logger.debug(
                "contacts_cache_miss",
                cache_type="details",
                user_id=str(user_id),
                resource_name=resource_name,
            )
            record_cache_miss("contacts_details")
            return None, False, None, None

        except Exception as e:
            logger.warning(
                "contacts_cache_get_failed",
                cache_type="details",
                user_id=str(user_id),
                error=str(e),
            )
            return None, False, None, None

    async def set_details(
        self,
        user_id: UUID,
        resource_name: str,
        data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Cache contact details with metadata wrapper (V2 format).

        Args:
            user_id: User UUID.
            resource_name: Google resource name.
            data: Contact details to cache.
            ttl_seconds: Time-to-live in seconds (default 5 min).
        """
        if ttl_seconds is None:
            ttl_seconds = settings.contacts_cache_details_ttl_seconds

        key = self._make_details_key(user_id, resource_name)
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.debug(
                "contacts_cache_set",
                cache_type="details",
                user_id=str(user_id),
                resource_name=resource_name,
                ttl_seconds=ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "contacts_cache_set_failed",
                cache_type="details",
                user_id=str(user_id),
                error=str(e),
            )

    async def invalidate_user(self, user_id: UUID) -> None:
        """
        Invalidate all cached data for a user.

        Args:
            user_id: User UUID.

        Note:
            Use when contact data changes (create/update/delete operations).
        """
        patterns = [
            f"contacts_list:{user_id}",
            f"contacts_search:{user_id}:*",
            f"contacts_details:{user_id}:*",
        ]

        invalidated_count = 0
        for pattern in patterns:
            try:
                # For exact keys
                if "*" not in pattern:
                    deleted = await self.redis.delete(pattern)
                    invalidated_count += deleted
                else:
                    # For wildcard patterns, scan and delete
                    cursor = 0
                    while True:
                        cursor, keys = await self.redis.scan(
                            cursor, match=pattern, count=settings.redis_scan_count
                        )
                        if keys:
                            deleted = await self.redis.delete(*keys)
                            invalidated_count += deleted
                        if cursor == 0:
                            break

            except Exception as e:
                logger.warning(
                    "contacts_cache_invalidate_failed",
                    user_id=str(user_id),
                    pattern=pattern,
                    error=str(e),
                )

        logger.info(
            "contacts_cache_invalidated",
            user_id=str(user_id),
            invalidated_count=invalidated_count,
        )
