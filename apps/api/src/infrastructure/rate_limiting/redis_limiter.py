"""
Redis-based distributed rate limiter using sliding window algorithm.

This module provides a distributed rate limiter that works across multiple
application instances using Redis as a central coordination point.

Key Features:
- Sliding window algorithm for smooth rate limiting
- Atomic operations using Lua scripts (no race conditions)
- Configurable limits per key
- Support for horizontal scaling

Phase: PHASE 2.4 - Rate Limiting Distribué Redis
Created: 2025-11-20
"""

import asyncio
import time

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.infrastructure.observability.metrics_redis import (
    extract_key_prefix,
    redis_lua_script_executions_total,
    redis_rate_limit_allows_total,
    redis_rate_limit_check_duration_seconds,
    redis_rate_limit_errors_total,
    redis_rate_limit_hits_total,
    redis_sliding_window_requests_current,
)

logger = structlog.get_logger(__name__)


# Lua script for atomic sliding window rate limiting
# This script implements a sliding window counter using sorted sets
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local max_calls = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local current_time = tonumber(ARGV[3])
local request_id = ARGV[4]

-- Remove old entries outside the window
local window_start = current_time - window_seconds
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- Count current requests in window
local current_count = redis.call('ZCARD', key)

-- Check if we can allow this request
if current_count < max_calls then
    -- Add this request to the sorted set with current timestamp as score
    redis.call('ZADD', key, current_time, request_id)
    -- Set expiration to window + buffer
    redis.call('EXPIRE', key, window_seconds + 10)
    return 1  -- Request allowed
else
    return 0  -- Request denied (rate limit exceeded)
end
"""


class RedisRateLimiter:
    """
    Distributed rate limiter using Redis sliding window algorithm.

    This implementation uses a Lua script to ensure atomicity of rate limit
    checks and updates, preventing race conditions in distributed environments.

    The sliding window algorithm provides smoother rate limiting compared to
    fixed windows by tracking individual request timestamps.

    Example:
        ```python
        limiter = RedisRateLimiter(redis_client)

        # Allow 20 calls per 60 seconds
        allowed = await limiter.acquire(
            key="user:123:contacts_search",
            max_calls=20,
            window_seconds=60
        )

        if not allowed:
            raise RateLimitExceeded()
        ```

    Attributes:
        redis: Async Redis client for distributed coordination
        script_sha: SHA hash of the Lua script (loaded once)
    """

    def __init__(self, redis: Redis):
        """
        Initialize the rate limiter.

        Args:
            redis: Async Redis client instance
        """
        self.redis = redis
        self.script_sha: str | None = None
        self._script_load_lock = asyncio.Lock()

    async def _ensure_script_loaded(self) -> str:
        """
        Ensure the Lua script is loaded into Redis.

        The script is loaded once and cached by SHA hash for subsequent calls.
        This is more efficient than sending the full script with each request.

        Returns:
            SHA hash of the loaded script

        Raises:
            RedisError: If script loading fails
        """
        if self.script_sha is not None:
            return self.script_sha

        async with self._script_load_lock:
            # Double-check after acquiring lock
            if self.script_sha is not None:
                return self.script_sha

            try:
                self.script_sha = await self.redis.script_load(SLIDING_WINDOW_SCRIPT)
                logger.debug(
                    "rate_limit_script_loaded",
                    script_sha=self.script_sha,
                )
                return self.script_sha
            except RedisError as e:
                logger.error(
                    "rate_limit_script_load_failed",
                    error=str(e),
                )
                raise

    async def acquire(
        self,
        key: str,
        max_calls: int,
        window_seconds: int,
    ) -> bool:
        """
        Attempt to acquire a rate limit token.

        This method checks if the request is within the allowed rate limit
        and atomically updates the request counter if allowed.

        Metrics tracked:
        - redis_rate_limit_check_duration_seconds: Duration of check
        - redis_rate_limit_allows_total: Accepted requests counter
        - redis_rate_limit_hits_total: Rejected requests counter
        - redis_lua_script_executions_total: Script execution status
        - redis_rate_limit_errors_total: Error counter by type

        Args:
            key: Unique identifier for this rate limit bucket
                 (e.g., "user:123:contacts_search", "api:gmail:send")
            max_calls: Maximum number of calls allowed in the window
            window_seconds: Time window in seconds

        Returns:
            True if request is allowed (within rate limit)
            False if request should be denied (rate limit exceeded)

        Raises:
            RedisError: If Redis operations fail (should be handled by caller)

        Example:
            ```python
            # Rate limit: 20 requests per minute for user's contact searches
            allowed = await limiter.acquire(
                key=f"user:{user_id}:contacts_search",
                max_calls=20,
                window_seconds=60,
            )
            ```
        """
        # Extract key prefix for metrics (avoid high cardinality)
        key_prefix = extract_key_prefix(key)

        # Track check duration
        start_time = time.perf_counter()

        try:
            # Ensure script is loaded
            script_sha = await self._ensure_script_loaded()

            # Generate unique request ID (timestamp + microseconds)
            current_time = time.time()
            request_id = f"{current_time:.6f}"

            # Execute Lua script atomically
            raw_result = await self.redis.evalsha(
                script_sha,
                1,  # Number of keys
                key,  # KEYS[1]
                str(max_calls),  # ARGV[1]
                str(window_seconds),  # ARGV[2]
                str(current_time),  # ARGV[3]
                request_id,  # ARGV[4]
            )
            result: int = int(raw_result)

            allowed = bool(result)

            # Record check duration
            duration = time.perf_counter() - start_time
            redis_rate_limit_check_duration_seconds.labels(key_prefix=key_prefix).observe(duration)

            # Track decision (allow vs hit)
            if allowed:
                redis_rate_limit_allows_total.labels(key_prefix=key_prefix).inc()
            else:
                redis_rate_limit_hits_total.labels(key_prefix=key_prefix).inc()

            # Track successful Lua script execution
            redis_lua_script_executions_total.labels(
                script_name="sliding_window", status="success"
            ).inc()

            logger.debug(
                "rate_limit_check",
                key=key,
                key_prefix=key_prefix,
                max_calls=max_calls,
                window_seconds=window_seconds,
                allowed=allowed,
                duration_ms=round(duration * 1000, 2),
            )

            return allowed

        except RedisError as e:
            # Record error metrics
            duration = time.perf_counter() - start_time
            redis_rate_limit_check_duration_seconds.labels(key_prefix=key_prefix).observe(duration)

            error_type = type(e).__name__
            redis_rate_limit_errors_total.labels(error_type=error_type).inc()

            redis_lua_script_executions_total.labels(
                script_name="sliding_window", status="error"
            ).inc()

            logger.error(
                "rate_limit_redis_error",
                key=key,
                key_prefix=key_prefix,
                error=str(e),
                error_type=error_type,
                duration_ms=round(duration * 1000, 2),
            )
            # On Redis failure, fail open (allow request) to prevent blocking
            # This is a trade-off: availability > strict rate limiting
            return True

    async def get_current_usage(self, key: str, window_seconds: int) -> int:
        """
        Get current usage count for a rate limit key.

        This is useful for debugging or showing users their current usage.

        Metrics tracked:
        - redis_sliding_window_requests_current: Current window size

        Args:
            key: Rate limit bucket identifier
            window_seconds: Time window in seconds

        Returns:
            Number of requests in current window

        Raises:
            RedisError: If Redis operations fail
        """
        # Extract key prefix for metrics
        key_prefix = extract_key_prefix(key)

        try:
            current_time = time.time()
            window_start = current_time - window_seconds

            # Remove old entries
            await self.redis.zremrangebyscore(key, "-inf", window_start)

            # Count current entries
            count: int = await self.redis.zcard(key)

            # Update sliding window size metric
            redis_sliding_window_requests_current.labels(key_prefix=key_prefix).set(count)

            logger.debug(
                "rate_limit_usage_check",
                key=key,
                key_prefix=key_prefix,
                window_seconds=window_seconds,
                current_count=count,
            )

            return count

        except RedisError as e:
            redis_rate_limit_errors_total.labels(error_type=type(e).__name__).inc()

            logger.error(
                "rate_limit_usage_check_failed",
                key=key,
                key_prefix=key_prefix,
                error=str(e),
            )
            raise

    async def reset(self, key: str) -> None:
        """
        Reset rate limit counter for a specific key.

        Useful for testing or administrative resets.

        Args:
            key: Rate limit bucket identifier

        Raises:
            RedisError: If Redis operations fail
        """
        try:
            await self.redis.delete(key)
            logger.info(
                "rate_limit_reset",
                key=key,
            )
        except RedisError as e:
            logger.error(
                "rate_limit_reset_failed",
                key=key,
                error=str(e),
            )
            raise

    async def close(self) -> None:
        """
        Close Redis connection.

        Should be called on application shutdown.
        """
        if self.redis:
            await self.redis.aclose()
            logger.debug("rate_limiter_closed")
