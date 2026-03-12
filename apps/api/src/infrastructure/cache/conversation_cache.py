"""
Conversation ID Cache Service for HITL operations.

Provides a Redis-backed cache for user_id → conversation_id mapping to avoid
database lookups on every chat request (performance optimization).

Architecture:
    Request → Redis Cache (fast path ~1ms) → conversation_id
                   ↓ (cache miss)
              PostgreSQL DB → Cache Set → conversation_id

Usage:
    # In router (async context)
    conversation_id = await get_conversation_id_cached(user_id)

    # Cache invalidation (when conversation is deleted)
    await invalidate_conversation_id_cache(user_id)

Reference: PERF 2026-01-13 - Chat page load optimization
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from prometheus_client import Counter
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.constants import REDIS_KEY_CONVERSATION_ID_PREFIX

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = structlog.get_logger(__name__)


# ============================================================================
# PROMETHEUS METRICS
# ============================================================================
# Track cache performance for monitoring and alerting

conversation_id_cache_total = Counter(
    "conversation_id_cache_total",
    "Total conversation ID cache operations",
    ["result"],  # "hit", "miss", "error"
)


# ============================================================================
# CACHE SERVICE
# ============================================================================


class ConversationIdCache:
    """
    Service for caching user_id → conversation_id mappings in Redis.

    Provides async methods for cache get/set/invalidate with automatic
    fallback to database on cache miss or Redis errors.

    Thread-safe and suitable for concurrent access.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        """
        Initialize conversation ID cache service.

        Args:
            redis_client: Redis client from get_redis_cache()
        """
        self.redis = redis_client
        self._key_prefix = REDIS_KEY_CONVERSATION_ID_PREFIX
        self._ttl_seconds = settings.conversation_id_cache_ttl_seconds

    def _make_key(self, user_id: UUID) -> str:
        """Generate cache key for user_id."""
        return f"{self._key_prefix}{user_id}"

    async def get(self, user_id: UUID) -> str | None:
        """
        Get conversation_id from cache.

        Args:
            user_id: User UUID

        Returns:
            Conversation ID string or None if not cached

        Raises:
            RedisError: If Redis operation fails (caller should handle)
        """
        cache_key = self._make_key(user_id)
        result = await self.redis.get(cache_key)

        if result:
            # Redis returns bytes, decode to string
            conversation_id = result.decode() if isinstance(result, bytes) else str(result)
            logger.debug(
                "conversation_id_cache_hit",
                user_id=str(user_id),
                conversation_id=conversation_id,
            )
            conversation_id_cache_total.labels(result="hit").inc()
            return conversation_id

        logger.debug(
            "conversation_id_cache_miss",
            user_id=str(user_id),
        )
        conversation_id_cache_total.labels(result="miss").inc()
        return None

    async def set(self, user_id: UUID, conversation_id: str) -> None:
        """
        Set conversation_id in cache with TTL.

        Args:
            user_id: User UUID
            conversation_id: Conversation ID string to cache

        Raises:
            RedisError: If Redis operation fails (caller should handle)
        """
        cache_key = self._make_key(user_id)
        await self.redis.setex(cache_key, self._ttl_seconds, conversation_id)

        logger.debug(
            "conversation_id_cache_set",
            user_id=str(user_id),
            conversation_id=conversation_id,
            ttl_seconds=self._ttl_seconds,
        )

    async def invalidate(self, user_id: UUID) -> None:
        """
        Invalidate conversation_id cache for a user.

        Call this when:
        - Conversation is hard-deleted
        - Conversation ownership changes (rare)

        Note: NOT needed for reset_conversation since the ID stays the same.

        Args:
            user_id: User UUID

        Raises:
            RedisError: If Redis operation fails (caller should handle)
        """
        cache_key = self._make_key(user_id)
        await self.redis.delete(cache_key)

        logger.debug(
            "conversation_id_cache_invalidated",
            user_id=str(user_id),
        )


# ============================================================================
# MODULE-LEVEL FUNCTIONS (convenience wrappers)
# ============================================================================


async def get_conversation_id_cached(user_id: UUID) -> str | None:
    """
    Get conversation_id from cache or DB with automatic caching.

    Convenience function that handles Redis connection, cache miss fallback
    to database, and graceful error handling.

    Flow:
    1. Check Redis cache first (fast path, ~1ms)
    2. If cache miss, query DB and cache result
    3. If Redis error, fallback to direct DB query
    4. Return conversation_id or None if no conversation exists

    Args:
        user_id: User UUID

    Returns:
        Conversation ID string or None if no active conversation

    Example:
        >>> conversation_id = await get_conversation_id_cached(user_id)
        >>> if conversation_id:
        ...     pending_hitl = await check_pending_hitl(conversation_id)
    """
    from src.domains.conversations.repository import ConversationRepository
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database import get_db_context

    try:
        redis = await get_redis_cache()
        cache = ConversationIdCache(redis)

        # Fast path: check cache
        cached = await cache.get(user_id)
        if cached:
            return cached

        # Cache miss: query DB
        async with get_db_context() as db:
            repo = ConversationRepository(db)
            conversation = await repo.get_active_for_user(user_id)

            if conversation:
                conversation_id = str(conversation.id)

                # Cache for future requests (non-blocking error handling)
                try:
                    await cache.set(user_id, conversation_id)
                except RedisError as cache_err:
                    logger.warning(
                        "conversation_id_cache_set_failed",
                        user_id=str(user_id),
                        error=str(cache_err),
                    )

                return conversation_id

            # No active conversation
            return None

    except RedisError as e:
        # Redis unavailable: fallback to direct DB query
        logger.warning(
            "conversation_id_cache_redis_error",
            user_id=str(user_id),
            error=str(e),
        )
        conversation_id_cache_total.labels(result="error").inc()

        # Fallback: query DB directly without caching
        try:
            async with get_db_context() as db:
                repo = ConversationRepository(db)
                conversation = await repo.get_active_for_user(user_id)
                return str(conversation.id) if conversation else None
        except Exception as db_err:
            logger.error(
                "conversation_id_fallback_db_error",
                user_id=str(user_id),
                error=str(db_err),
            )
            return None

    except Exception as e:
        # Unexpected error: log and return None (graceful degradation)
        logger.error(
            "conversation_id_cache_unexpected_error",
            user_id=str(user_id),
            error=str(e),
            error_type=type(e).__name__,
        )
        conversation_id_cache_total.labels(result="error").inc()
        return None


async def invalidate_conversation_id_cache(user_id: UUID) -> None:
    """
    Invalidate conversation_id cache for a user.

    Convenience function with graceful error handling.

    Call this when:
    - Conversation is hard-deleted
    - Conversation ownership changes (rare)

    Note: NOT needed for reset_conversation since the ID stays the same.

    Args:
        user_id: User UUID

    Example:
        >>> await invalidate_conversation_id_cache(user_id)
    """
    from src.infrastructure.cache.redis import get_redis_cache

    try:
        redis = await get_redis_cache()
        cache = ConversationIdCache(redis)
        await cache.invalidate(user_id)

    except RedisError as e:
        # Non-fatal: cache will expire naturally via TTL
        logger.warning(
            "conversation_id_cache_invalidation_redis_error",
            user_id=str(user_id),
            error=str(e),
        )
