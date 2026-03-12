"""
Redis client setup for caching and session management.

Production-grade connection pooling with:
- max_connections: Limit concurrent connections
- socket_timeout: Close idle connections
- socket_connect_timeout: Fail-fast on connection issues
- health_check_interval: Validate connections with PING

Reference: https://redis.io/docs/latest/develop/clients/pools-and-muxing/
"""

from typing import Any

import redis.asyncio as aioredis
import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_OAUTH_STATE_PREFIX, REDIS_KEY_SESSION_PREFIX

logger = structlog.get_logger(__name__)

# Redis clients for different databases
_redis_cache: aioredis.Redis | None = None
_redis_session: aioredis.Redis | None = None


async def get_redis_cache() -> aioredis.Redis:
    """
    Get Redis client for caching with production-grade connection pooling.

    Returns:
        aioredis.Redis: Redis client for cache operations
    """
    global _redis_cache

    if _redis_cache is None:
        redis_url = str(settings.redis_url)
        # Replace DB number in URL
        base_url = redis_url.rsplit("/", 1)[0]
        cache_url = f"{base_url}/{settings.redis_cache_db}"

        _redis_cache = aioredis.from_url(
            cache_url,
            encoding="utf-8",
            decode_responses=True,
            # Connection pool settings
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            health_check_interval=settings.redis_health_check_interval,
        )
        logger.info(
            "redis_cache_connected",
            db=settings.redis_cache_db,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            health_check_interval=settings.redis_health_check_interval,
        )

    return _redis_cache


async def get_redis_session() -> aioredis.Redis:
    """
    Get Redis client for session management with production-grade connection pooling.

    Returns:
        aioredis.Redis: Redis client for session operations
    """
    global _redis_session

    if _redis_session is None:
        redis_url = str(settings.redis_url)
        # Replace DB number in URL
        base_url = redis_url.rsplit("/", 1)[0]
        session_url = f"{base_url}/{settings.redis_session_db}"

        _redis_session = aioredis.from_url(
            session_url,
            encoding="utf-8",
            decode_responses=True,
            # Connection pool settings
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            health_check_interval=settings.redis_health_check_interval,
        )
        logger.info(
            "redis_session_connected",
            db=settings.redis_session_db,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            health_check_interval=settings.redis_health_check_interval,
        )

    return _redis_session


async def close_redis() -> None:
    """Close all Redis connections."""
    global _redis_cache, _redis_session

    if _redis_cache:
        await _redis_cache.close()
        logger.info("redis_cache_closed")

    if _redis_session:
        await _redis_session.close()
        logger.info("redis_session_closed")


class CacheService:
    """Service for cache operations."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def get(self, key: str) -> str | None:
        """Get value from cache."""
        result = await self.redis.get(key)
        return str(result) if result else None

    async def set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
    ) -> None:
        """Set value in cache with optional expiration."""
        await self.redis.set(key, value, ex=expire)

    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        await self.redis.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        return bool(await self.redis.exists(key))


class SessionService:
    """Service for session operations."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def create_session(
        self,
        user_id: str,
        refresh_token: str,
        expire_days: int = 7,
    ) -> None:
        """Create user session with refresh token."""
        key = f"{REDIS_KEY_SESSION_PREFIX}{user_id}"
        await self.redis.sadd(key, refresh_token)
        await self.redis.expire(key, expire_days * 24 * 3600)

    async def get_sessions(self, user_id: str) -> set[str]:
        """Get all refresh tokens for user."""
        key = f"{REDIS_KEY_SESSION_PREFIX}{user_id}"
        result: set[Any] = await self.redis.smembers(key)
        return {str(item) for item in result}

    async def remove_session(self, user_id: str, refresh_token: str) -> None:
        """Remove specific refresh token from user sessions."""
        key = f"{REDIS_KEY_SESSION_PREFIX}{user_id}"
        await self.redis.srem(key, refresh_token)

    async def remove_all_sessions(self, user_id: str) -> None:
        """Remove all sessions for user (logout from all devices)."""
        key = f"{REDIS_KEY_SESSION_PREFIX}{user_id}"
        await self.redis.delete(key)

    async def verify_refresh_token(self, user_id: str, refresh_token: str) -> bool:
        """Verify if refresh token exists in user sessions."""
        key = f"{REDIS_KEY_SESSION_PREFIX}{user_id}"
        result: int = await self.redis.sismember(key, refresh_token)
        return bool(result)

    async def store_oauth_state(self, state: str, data: dict, expire_minutes: int = 5) -> None:
        """Store OAuth state token temporarily."""
        key = f"{REDIS_KEY_OAUTH_STATE_PREFIX}{state}"
        import json

        await self.redis.setex(key, expire_minutes * 60, json.dumps(data))

    async def get_oauth_state(self, state: str) -> dict[str, str] | None:
        """
        Retrieve OAuth state token.

        Security: Single-use token pattern - automatically deleted after retrieval.
        This prevents replay attacks by ensuring state tokens can only be used once.

        Args:
            state: OAuth state token

        Returns:
            dict with state data, or None if not found/expired
        """
        import json

        key = f"{REDIS_KEY_OAUTH_STATE_PREFIX}{state}"
        data = await self.redis.get(key)
        if data:
            await self.redis.delete(key)  # Single-use token
            parsed: dict[str, str] = json.loads(data)
            return parsed
        return None

    async def delete_oauth_state(self, state: str) -> None:
        """
        Explicitly delete OAuth state token.

        Note: Normally not needed as get_oauth_state() auto-deletes (single-use pattern).
        This method is provided for error cleanup scenarios where state needs to be
        invalidated without retrieval.

        Args:
            state: OAuth state token to delete
        """
        key = f"{REDIS_KEY_OAUTH_STATE_PREFIX}{state}"
        await self.redis.delete(key)
