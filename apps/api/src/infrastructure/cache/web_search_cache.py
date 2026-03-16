"""
Redis cache for web search and web fetch tool results.

Reduces external API calls (Brave, Perplexity, Wikipedia) and improves
response time for repeated queries within a configurable TTL window.

V2 Features (Freshness Transparency):
- Metadata wrapper with cached_at timestamp (ISO 8601 UTC)
- Returns CacheResult with (data, from_cache, cached_at, cache_age_seconds)
- Precise cache age calculation for UX transparency
"""

import json
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.core.config import get_settings

from .base import (
    CacheResult,
    create_cache_entry,
    make_search_key,
    parse_cache_entry,
    record_cache_miss,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Cache type identifiers for Prometheus labels
CACHE_TYPE_WEB_SEARCH = "web_search"
CACHE_TYPE_WEB_FETCH = "web_fetch"


class WebSearchCache:
    """
    Redis-based cache for web search and web fetch tool results.

    Cache strategies:
    - Web search (unified): configurable TTL (default 5 min)
    - Web fetch (page content): configurable TTL (default 10 min)

    Cache keys include user_id for multi-tenant isolation.
    Query + recency params are hashed for search keys.
    URL is hashed for fetch keys.

    Cache invalidation:
    - Automatic TTL expiration
    - Manual bypass via force_refresh parameter on tools
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        """Initialize web search cache.

        Args:
            redis_client: Redis async client.
        """
        self.redis = redis_client

    # ========================================================================
    # Key Generation
    # ========================================================================

    def _make_search_key(self, user_id: UUID, query: str, recency: str | None) -> str:
        """Generate cache key for unified web search.

        Combines query and recency filter into the hash to differentiate
        the same query with different freshness requirements.

        Note: The planner (LLM) may reformulate the user's query differently
        on each invocation, producing different cache keys for semantically
        identical requests. Cache hits are most effective for:
        - Identical programmatic queries (FOR_EACH loops, retries)
        - Short TTL deduplication of rapid successive identical calls
        - Same tool called with same parameters within the TTL window

        Args:
            user_id: User UUID.
            query: Search query string (as passed by the planner).
            recency: Recency filter (day/week/month/None).

        Returns:
            Cache key string.
        """
        composite_query = f"{query}|recency={recency or 'none'}"
        return make_search_key(settings.web_search_cache_prefix, user_id, composite_query)

    def _make_fetch_key(self, user_id: UUID, url: str) -> str:
        """Generate cache key for web fetch.

        Args:
            user_id: User UUID.
            url: URL to fetch.

        Returns:
            Cache key string.
        """
        return make_search_key(settings.web_fetch_cache_prefix, user_id, url)

    # ========================================================================
    # Web Search Cache Operations
    # ========================================================================

    async def get_search(
        self, user_id: UUID, query: str, recency: str | None = None
    ) -> CacheResult:
        """Get cached web search results.

        Args:
            user_id: User UUID.
            query: Search query string.
            recency: Recency filter (day/week/month/None).

        Returns:
            CacheResult with data and metadata.
        """
        if not settings.web_search_cache_enabled:
            return CacheResult.miss()

        key = self._make_search_key(user_id, query, recency)
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    CACHE_TYPE_WEB_SEARCH,
                    {"user_id": str(user_id), "query_preview": query[:30]},
                )
                if result.from_cache:
                    logger.info(
                        "web_search_cache_hit",
                        user_id=str(user_id),
                        query_preview=query[:30],
                        recency=recency,
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result

            logger.info(
                "web_search_cache_miss",
                user_id=str(user_id),
                query_preview=query[:30],
                recency=recency,
            )
            record_cache_miss(CACHE_TYPE_WEB_SEARCH)
            return CacheResult.miss()

        except Exception as e:
            logger.warning(
                "web_search_cache_get_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return CacheResult.miss()

    async def set_search(
        self,
        user_id: UUID,
        query: str,
        data: dict[str, Any],
        recency: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        """Cache web search results with V2 metadata wrapper.

        Args:
            user_id: User UUID.
            query: Search query string.
            data: Search results to cache.
            recency: Recency filter used for this search.
            ttl_seconds: Time-to-live in seconds (default from settings).
        """
        if not settings.web_search_cache_enabled:
            return

        if ttl_seconds is None:
            ttl_seconds = settings.web_search_cache_ttl_seconds

        key = self._make_search_key(user_id, query, recency)
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.info(
                "web_search_cache_set",
                user_id=str(user_id),
                query_preview=query[:30],
                recency=recency,
                ttl_seconds=ttl_seconds,
            )
        except Exception as e:
            logger.warning(
                "web_search_cache_set_failed",
                user_id=str(user_id),
                error=str(e),
            )

    # ========================================================================
    # Web Fetch Cache Operations
    # ========================================================================

    async def get_fetch(self, user_id: UUID, url: str) -> CacheResult:
        """Get cached web fetch (page content) result.

        Args:
            user_id: User UUID.
            url: URL that was fetched.

        Returns:
            CacheResult with data and metadata.
        """
        if not settings.web_search_cache_enabled:
            return CacheResult.miss()

        key = self._make_fetch_key(user_id, url)
        try:
            cached = await self.redis.get(key)
            if cached:
                result = parse_cache_entry(
                    cached,
                    CACHE_TYPE_WEB_FETCH,
                    {"user_id": str(user_id), "url_preview": url[:50]},
                )
                if result.from_cache:
                    logger.info(
                        "web_fetch_cache_hit",
                        user_id=str(user_id),
                        url_preview=url[:50],
                        cache_age_seconds=result.cache_age_seconds,
                    )
                    return result

            logger.info(
                "web_fetch_cache_miss",
                user_id=str(user_id),
                url_preview=url[:50],
            )
            record_cache_miss(CACHE_TYPE_WEB_FETCH)
            return CacheResult.miss()

        except Exception as e:
            logger.warning(
                "web_fetch_cache_get_failed",
                user_id=str(user_id),
                error=str(e),
            )
            return CacheResult.miss()

    async def set_fetch(
        self,
        user_id: UUID,
        url: str,
        data: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """Cache web fetch result with V2 metadata wrapper.

        Args:
            user_id: User UUID.
            url: URL that was fetched.
            data: Extracted page content to cache.
            ttl_seconds: Time-to-live in seconds (default from settings).
        """
        if not settings.web_search_cache_enabled:
            return

        if ttl_seconds is None:
            ttl_seconds = settings.web_fetch_cache_ttl_seconds

        key = self._make_fetch_key(user_id, url)
        try:
            cache_entry = create_cache_entry(data, ttl_seconds)
            await self.redis.set(key, json.dumps(cache_entry), ex=ttl_seconds)
            logger.info(
                "web_fetch_cache_set",
                user_id=str(user_id),
                url_preview=url[:50],
                ttl_seconds=ttl_seconds,
            )
        except Exception as e:
            logger.warning(
                "web_fetch_cache_set_failed",
                user_id=str(user_id),
                error=str(e),
            )
