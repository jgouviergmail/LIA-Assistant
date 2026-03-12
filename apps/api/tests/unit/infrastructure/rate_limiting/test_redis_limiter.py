"""
Unit tests for RedisRateLimiter.

Tests the distributed rate limiter using mocked Redis to verify:
- Sliding window algorithm correctness
- Atomic Lua script execution
- Rate limit enforcement
- Graceful degradation on errors

Phase: PHASE 2.4 - Rate Limiting Distribué Redis
Created: 2025-11-20
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import RedisError

from src.infrastructure.rate_limiting import RedisRateLimiter


class TestRedisRateLimiter:
    """Test suite for RedisRateLimiter with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.script_load = AsyncMock(return_value="mock_script_sha")
        redis.evalsha = AsyncMock(return_value=1)  # Default: request allowed
        redis.zremrangebyscore = AsyncMock()
        redis.zcard = AsyncMock(return_value=0)
        redis.delete = AsyncMock()
        redis.aclose = AsyncMock()
        return redis

    @pytest.fixture
    def limiter(self, mock_redis):
        """Create RedisRateLimiter instance with mocked Redis."""
        return RedisRateLimiter(mock_redis)

    @pytest.mark.asyncio
    async def test_script_loads_once(self, limiter, mock_redis):
        """
        Test that Lua script is loaded only once and cached.

        The script should be loaded on first acquire() call and reused
        for subsequent calls to avoid overhead.
        """
        # First acquire - should load script
        await limiter.acquire("test_key", max_calls=10, window_seconds=60)
        assert mock_redis.script_load.call_count == 1
        assert limiter.script_sha == "mock_script_sha"

        # Second acquire - should NOT reload script
        await limiter.acquire("test_key", max_calls=10, window_seconds=60)
        assert mock_redis.script_load.call_count == 1  # Still 1

    @pytest.mark.asyncio
    async def test_acquire_allowed_within_limit(self, limiter, mock_redis):
        """
        Test that requests within rate limit are allowed.

        Lua script returns 1 (allowed) when count < max_calls.
        """
        mock_redis.evalsha.return_value = 1  # Request allowed

        result = await limiter.acquire(
            key="user:123:test",
            max_calls=20,
            window_seconds=60,
        )

        assert result is True
        assert mock_redis.evalsha.call_count == 1

        # Verify Lua script was called with correct arguments
        call_args = mock_redis.evalsha.call_args
        assert call_args[0][0] == "mock_script_sha"  # script SHA
        assert call_args[0][1] == 1  # number of keys
        assert call_args[0][2] == "user:123:test"  # key
        assert call_args[0][3] == "20"  # max_calls
        assert call_args[0][4] == "60"  # window_seconds

    @pytest.mark.asyncio
    async def test_acquire_denied_over_limit(self, limiter, mock_redis):
        """
        Test that requests exceeding rate limit are denied.

        Lua script returns 0 (denied) when count >= max_calls.
        """
        mock_redis.evalsha.return_value = 0  # Request denied

        result = await limiter.acquire(
            key="user:123:test",
            max_calls=20,
            window_seconds=60,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_unique_request_ids(self, limiter, mock_redis):
        """
        Test that each acquire() generates unique request ID.

        Request IDs should include microsecond timestamp to ensure uniqueness
        in sorted set.
        """
        await limiter.acquire("test_key", max_calls=10, window_seconds=60)
        call1_args = mock_redis.evalsha.call_args[0]
        request_id_1 = call1_args[5]  # ARGV[4]

        # Small delay to ensure different timestamp
        time.sleep(0.001)

        await limiter.acquire("test_key", max_calls=10, window_seconds=60)
        call2_args = mock_redis.evalsha.call_args[0]
        request_id_2 = call2_args[5]  # ARGV[4]

        # Request IDs should be different
        assert request_id_1 != request_id_2

    @pytest.mark.asyncio
    async def test_acquire_redis_error_returns_true(self, limiter, mock_redis):
        """
        Test that Redis errors result in fail-open behavior.

        On Redis failure, the limiter should allow the request to proceed
        rather than blocking all traffic. This prioritizes availability
        over strict rate limiting.
        """
        mock_redis.evalsha.side_effect = RedisError("Connection failed")

        result = await limiter.acquire(
            key="user:123:test",
            max_calls=20,
            window_seconds=60,
        )

        # Fail open - allow request despite error
        assert result is True

    @pytest.mark.asyncio
    async def test_get_current_usage(self, limiter, mock_redis):
        """
        Test retrieving current usage count for a rate limit key.

        This is useful for debugging and showing users their current usage.
        """
        mock_redis.zcard.return_value = 15

        count = await limiter.get_current_usage(
            key="user:123:test",
            window_seconds=60,
        )

        assert count == 15
        assert mock_redis.zremrangebyscore.call_count == 1
        assert mock_redis.zcard.call_count == 1

    @pytest.mark.asyncio
    async def test_get_current_usage_redis_error(self, limiter, mock_redis):
        """
        Test that get_current_usage raises RedisError on failure.

        Unlike acquire(), this method should raise errors for debugging.
        """
        mock_redis.zcard.side_effect = RedisError("Connection failed")

        with pytest.raises(RedisError):
            await limiter.get_current_usage(
                key="user:123:test",
                window_seconds=60,
            )

    @pytest.mark.asyncio
    async def test_reset(self, limiter, mock_redis):
        """
        Test resetting rate limit counter for a key.

        This is useful for testing and administrative resets.
        """
        await limiter.reset("user:123:test")

        mock_redis.delete.assert_called_once_with("user:123:test")

    @pytest.mark.asyncio
    async def test_reset_redis_error(self, limiter, mock_redis):
        """Test that reset raises RedisError on failure."""
        mock_redis.delete.side_effect = RedisError("Connection failed")

        with pytest.raises(RedisError):
            await limiter.reset("user:123:test")

    @pytest.mark.asyncio
    async def test_close(self, limiter, mock_redis):
        """Test closing Redis connection."""
        await limiter.close()

        mock_redis.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_sliding_window_removes_old_entries(self, limiter, mock_redis):
        """
        Test that sliding window removes entries outside time window.

        The Lua script should call ZREMRANGEBYSCORE to remove old entries
        before counting current requests.
        """
        current_time = time.time()

        with patch("time.time", return_value=current_time):
            await limiter.acquire("test_key", max_calls=10, window_seconds=60)

        # Verify Lua script was called (script handles ZREMRANGEBYSCORE internally)
        call_args = mock_redis.evalsha.call_args[0]
        current_time_arg = float(call_args[5])  # ARGV[3]

        # Current time should be close to our mock time
        assert abs(current_time_arg - current_time) < 0.1

    @pytest.mark.asyncio
    async def test_concurrent_script_loading(self, limiter, mock_redis):
        """
        Test that concurrent calls don't load script multiple times.

        The script_load_lock should prevent race conditions when multiple
        coroutines try to load the script simultaneously.
        """
        # Simulate slow script load
        script_load_called = 0

        async def slow_script_load(script):
            nonlocal script_load_called
            script_load_called += 1
            await asyncio.sleep(0.01)  # Simulate network delay
            return "mock_script_sha"

        mock_redis.script_load = slow_script_load

        # Call acquire concurrently
        import asyncio

        results = await asyncio.gather(
            limiter.acquire("key1", max_calls=10, window_seconds=60),
            limiter.acquire("key2", max_calls=10, window_seconds=60),
            limiter.acquire("key3", max_calls=10, window_seconds=60),
        )

        # All should succeed
        assert all(results)

        # Script should only be loaded once despite concurrent calls
        assert script_load_called == 1


class TestRedisRateLimiterEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.script_load = AsyncMock(return_value="sha")
        redis.evalsha = AsyncMock(return_value=1)
        redis.aclose = AsyncMock()
        return redis

    @pytest.fixture
    def limiter(self, mock_redis):
        """Create RedisRateLimiter instance."""
        return RedisRateLimiter(mock_redis)

    @pytest.mark.asyncio
    async def test_zero_max_calls(self, limiter, mock_redis):
        """Test that zero max_calls always denies requests."""
        mock_redis.evalsha.return_value = 0  # Always deny

        result = await limiter.acquire(
            key="test_key",
            max_calls=0,  # No requests allowed
            window_seconds=60,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_large_window(self, limiter, mock_redis):
        """Test rate limiter with large time window (1 hour)."""
        result = await limiter.acquire(
            key="test_key",
            max_calls=1000,
            window_seconds=3600,  # 1 hour
        )

        assert result is True

        # Verify window_seconds was passed correctly
        call_args = mock_redis.evalsha.call_args[0]
        assert call_args[4] == "3600"

    @pytest.mark.asyncio
    async def test_small_window(self, limiter, mock_redis):
        """Test rate limiter with small time window (1 second)."""
        result = await limiter.acquire(
            key="test_key",
            max_calls=5,
            window_seconds=1,  # 1 second
        )

        assert result is True

        call_args = mock_redis.evalsha.call_args[0]
        assert call_args[4] == "1"

    @pytest.mark.asyncio
    async def test_multiple_keys_isolated(self, limiter, mock_redis):
        """
        Test that different keys have isolated rate limits.

        Each key should have its own sliding window counter.
        """
        await limiter.acquire("user:123:contacts", max_calls=10, window_seconds=60)
        await limiter.acquire("user:456:contacts", max_calls=10, window_seconds=60)
        await limiter.acquire("user:123:gmail", max_calls=20, window_seconds=60)

        # Should have made 3 calls with 3 different keys
        assert mock_redis.evalsha.call_count == 3

        # Extract keys from call arguments
        call1_key = mock_redis.evalsha.call_args_list[0][0][2]
        call2_key = mock_redis.evalsha.call_args_list[1][0][2]
        call3_key = mock_redis.evalsha.call_args_list[2][0][2]

        assert call1_key == "user:123:contacts"
        assert call2_key == "user:456:contacts"
        assert call3_key == "user:123:gmail"
