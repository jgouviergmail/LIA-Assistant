"""
Redis cache helpers for JSON serialization and complex data structures.

Phase 3.2.9: Generic helpers to prevent Redis serialization errors.

These helpers eliminate the need for manual json.dumps()/json.loads() in API clients,
reducing code duplication and preventing common serialization errors.

Best Practices:
- Use cache_set_json() for dicts/lists (automatic JSON serialization)
- Use cache_get_json() for reading JSON data (automatic deserialization)
- Use cache_set() for strings/ints/floats (direct storage)
- Always include TTL to prevent unbounded cache growth

Metrics:
- Automatically logs cache operations for debugging
- Compatible with Prometheus metrics collection

Security:
- No sensitive data logged (only cache keys and sizes)
- Respects Redis ACL if configured

References:
- Redis data types: https://redis.io/docs/data-types/
- Best practices: https://redis.io/docs/manual/patterns/

Version: 1.0.0
Created: November 2025 (Gmail integration debugging session)
"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)


async def cache_set_json(
    redis_client: aioredis.Redis,
    key: str,
    value: dict | list,
    ttl_seconds: int,
    *,
    add_timestamp: bool = True,
) -> None:
    """
    Set JSON-serializable data in Redis with automatic serialization.

    This helper prevents the common error:
        redis.exceptions.DataError: Invalid input of type: 'dict'.
        Convert to a bytes, string, int or float first.

    Args:
        redis_client: Redis async client
        key: Cache key (use namespaced keys like "gmail:search:{user_id}:{query_hash}")
        value: Dict or list to cache (must be JSON-serializable)
        ttl_seconds: Time to live in seconds (use constants from settings)
        add_timestamp: If True, adds "cached_at" timestamp to metadata

    Raises:
        TypeError: If value is not JSON-serializable
        redis.RedisError: If Redis operation fails

    Example:
        >>> from src.infrastructure.cache.redis import get_redis_cache
        >>> redis_client = await get_redis_cache()
        >>>
        >>> # Cache search results
        >>> emails_data = {"emails": [...], "total": 10}
        >>> await cache_set_json(
        ...     redis_client,
        ...     "gmail:search:user123:abc123",
        ...     emails_data,
        ...     ttl_seconds=300  # 5 minutes
        ... )

    Best Practices:
        - Use descriptive namespaced keys: "{domain}:{operation}:{id}"
        - Set appropriate TTL based on data volatility
        - For user-specific data, include user_id in key
        - For search results, include query hash to avoid collisions
    """
    try:
        # Wrap data with metadata
        cache_data: dict[str, Any] = {"data": value}

        if add_timestamp:
            cache_data["cached_at"] = datetime.now(UTC).isoformat()

        # Serialize to JSON string
        json_str = json.dumps(cache_data, ensure_ascii=False)

        # Store in Redis
        await redis_client.setex(
            key,
            ttl_seconds,
            json_str,
        )

        logger.debug(
            "cache_set_json_success",
            key=key,
            ttl_seconds=ttl_seconds,
            data_size_bytes=len(json_str),
        )

    except TypeError as e:
        logger.error(
            "cache_set_json_serialization_error",
            key=key,
            error=str(e),
            value_type=type(value).__name__,
        )
        raise TypeError(
            f"Value not JSON-serializable: {type(value).__name__}. "
            f"Ensure all nested objects support JSON serialization."
        ) from e

    except Exception as e:
        logger.error(
            "cache_set_json_redis_error",
            key=key,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def cache_get_json(
    redis_client: aioredis.Redis,
    key: str,
) -> dict | None:
    """
    Get JSON data from Redis with automatic deserialization.

    Automatically handles:
    - JSON deserialization
    - Missing keys (returns None)
    - Metadata extraction (cached_at, data)

    Args:
        redis_client: Redis async client
        key: Cache key

    Returns:
        Deserialized data dict, or None if key doesn't exist/expired

    Raises:
        json.JSONDecodeError: If cached data is not valid JSON
        redis.RedisError: If Redis operation fails

    Example:
        >>> cache_data = await cache_get_json(redis_client, "gmail:search:user123:abc123")
        >>> if cache_data:
        ...     emails = cache_data.get("data", {})
        ...     cached_at = cache_data.get("cached_at")
        ...     print(f"Cache age: {datetime.now(UTC) - datetime.fromisoformat(cached_at)}")

    Best Practices:
        - Always check for None before using data
        - Log cache hits/misses for monitoring
        - Consider cache_age for displaying stale data warnings
    """
    try:
        cached_value = await redis_client.get(key)

        if not cached_value:
            logger.debug("cache_get_json_miss", key=key)
            return None

        # Deserialize JSON
        cache_data: dict[str, Any] = json.loads(cached_value)

        logger.debug(
            "cache_get_json_hit",
            key=key,
            has_data=("data" in cache_data),
            has_timestamp=("cached_at" in cache_data),
        )

        return cache_data

    except json.JSONDecodeError as e:
        logger.error(
            "cache_get_json_decode_error",
            key=key,
            error=str(e),
            cached_value_preview=cached_value[:100] if cached_value else None,
        )
        # Delete corrupted cache entry
        await redis_client.delete(key)
        return None

    except Exception as e:
        logger.error(
            "cache_get_json_redis_error",
            key=key,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def cache_get_or_compute(
    redis_client: aioredis.Redis,
    key: str,
    ttl_seconds: int,
    compute_fn: Callable[[], Awaitable[dict[str, Any] | list[Any]]],
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Get data from cache or compute and cache it (cache-aside pattern).

    This is the recommended pattern for API client methods that support caching.

    Args:
        redis_client: Redis async client
        key: Cache key
        ttl_seconds: Time to live for computed data
        compute_fn: Async function that computes the data (must return dict/list)
        force_refresh: If True, bypass cache and recompute

    Returns:
        Dict with "data" and metadata (cached_at, from_cache)

    Example:
        >>> async def fetch_emails_from_api():
        ...     response = await gmail_api.list()
        ...     return {"emails": response.get("messages", [])}
        >>>
        >>> result = await cache_get_or_compute(
        ...     redis_client,
        ...     "gmail:search:user123:query_hash",
        ...     ttl_seconds=300,
        ...     compute_fn=fetch_emails_from_api,
        ... )
        >>> emails = result["data"]["emails"]
        >>> if result.get("from_cache"):
        ...     print(f"Cache age: {result.get('cache_age_seconds')}s")

    Best Practices:
        - Use this pattern in API client methods for consistency
        - Pass force_refresh from tool parameters for cache busting
        - Log cache_age for monitoring cache effectiveness
    """
    # Check cache first
    if not force_refresh:
        cache_data = await cache_get_json(redis_client, key)
        if cache_data:
            # Calculate cache age
            cached_at_str = cache_data.get("cached_at")
            cache_age_seconds = None
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                cache_age_seconds = (datetime.now(UTC) - cached_at).total_seconds()

            return {
                **cache_data,
                "from_cache": True,
                "cache_age_seconds": cache_age_seconds,
            }

    # Cache miss or force refresh - compute data
    logger.debug(
        "cache_computing_data",
        key=key,
        force_refresh=force_refresh,
    )

    computed_data = await compute_fn()

    # Cache the computed data
    await cache_set_json(
        redis_client,
        key,
        computed_data,
        ttl_seconds,
    )

    return {
        "data": computed_data,
        "cached_at": datetime.now(UTC).isoformat(),
        "from_cache": False,
    }


async def cache_invalidate_pattern(
    redis_client: aioredis.Redis,
    pattern: str,
) -> int:
    """
    Invalidate all cache keys matching a pattern.

    WARNING: Use sparingly - SCAN can be expensive on large datasets.
    Prefer specific key deletion when possible.

    Args:
        redis_client: Redis async client
        pattern: Redis pattern with wildcards (e.g., "gmail:search:user123:*")

    Returns:
        Number of keys deleted

    Example:
        >>> # Invalidate all Gmail searches for a user
        >>> deleted_count = await cache_invalidate_pattern(
        ...     redis_client,
        ...     "gmail:search:user123:*"
        ... )
        >>> print(f"Invalidated {deleted_count} cache entries")

    Use Cases:
        - User disconnects connector → invalidate all their cached data
        - Data sync/refresh → invalidate stale caches
        - Testing → clear test data

    Best Practices:
        - Use specific patterns to minimize SCAN cost
        - Consider cache TTL instead of manual invalidation
        - Log invalidation for debugging
    """
    deleted_count = 0

    try:
        # SCAN for matching keys (cursor-based, doesn't block Redis)
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=100,  # Batch size
            )

            if keys:
                deleted_count += await redis_client.delete(*keys)

            if cursor == 0:
                break

        logger.info(
            "cache_invalidate_pattern_success",
            pattern=pattern,
            deleted_count=deleted_count,
        )

        return deleted_count

    except Exception as e:
        logger.error(
            "cache_invalidate_pattern_error",
            pattern=pattern,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


__all__ = [
    "cache_get_json",
    "cache_get_or_compute",
    "cache_invalidate_pattern",
    "cache_set_json",
]
