"""
Integration tests for RedisRateLimiter with real Redis instance.

Tests the distributed rate limiter against actual Redis to verify:
- Real Lua script execution
- Sliding window accuracy
- Multi-request behavior
- Persistence across connections

Requires: Redis server running on localhost:6379 (or configured REDIS_URL)

Phase: PHASE 2.4 - Rate Limiting Distribué Redis
Created: 2025-11-20
"""

import asyncio
import time

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.rate_limiting import RedisRateLimiter


@pytest.fixture
async def redis_client():
    """
    Create real Redis client for integration tests.

    Uses REDIS_URL from settings. Skips tests if Redis is unavailable.
    """
    try:
        redis = Redis.from_url(
            str(settings.redis_url),
            decode_responses=False,  # RedisRateLimiter expects bytes
        )
        # Test connection
        await redis.ping()
        yield redis
        await redis.aclose()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest.fixture
async def limiter(redis_client):
    """Create RedisRateLimiter with real Redis."""
    limiter = RedisRateLimiter(redis_client)
    yield limiter
    # Cleanup
    await limiter.close()


@pytest.fixture
async def test_key():
    """Generate unique test key with timestamp to avoid conflicts."""
    return f"test:rate_limit:{int(time.time() * 1000000)}"


class TestRedisRateLimiterIntegration:
    """Integration tests with real Redis."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_lua_script_loads_successfully(self, limiter, test_key):
        """
        Test that Lua script loads successfully into Redis.

        Verifies that the sliding window script is valid Lua syntax
        and can be executed by Redis.
        """
        result = await limiter.acquire(
            key=test_key,
            max_calls=10,
            window_seconds=60,
        )

        assert result is True
        assert limiter.script_sha is not None
        assert len(limiter.script_sha) == 40  # SHA-1 hash length

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_allows_requests_within_limit(self, limiter, test_key):
        """
        Test that requests within rate limit are allowed.

        Should allow up to max_calls requests within the window.
        """
        max_calls = 10
        window_seconds = 60

        # Make max_calls requests
        for i in range(max_calls):
            result = await limiter.acquire(
                key=test_key,
                max_calls=max_calls,
                window_seconds=window_seconds,
            )
            assert result is True, f"Request {i + 1}/{max_calls} should be allowed"

        # Verify current usage
        usage = await limiter.get_current_usage(test_key, window_seconds)
        assert usage == max_calls

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_blocks_requests_over_limit(self, limiter, test_key):
        """
        Test that requests exceeding rate limit are denied.

        After reaching max_calls, additional requests should be blocked.
        """
        max_calls = 5
        window_seconds = 60

        # Fill up the limit
        for _ in range(max_calls):
            result = await limiter.acquire(test_key, max_calls, window_seconds)
            assert result is True

        # Next request should be denied
        result = await limiter.acquire(test_key, max_calls, window_seconds)
        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sliding_window_accuracy(self, limiter, test_key):
        """
        Test sliding window algorithm accuracy.

        Requests should become available again after sliding out of the window.
        """
        max_calls = 3
        window_seconds = 2  # Short window for fast test

        # Make 3 requests (fill limit)
        for _ in range(max_calls):
            result = await limiter.acquire(test_key, max_calls, window_seconds)
            assert result is True

        # 4th request denied (limit reached)
        result = await limiter.acquire(test_key, max_calls, window_seconds)
        assert result is False

        # Wait for window to slide (oldest request should expire)
        await asyncio.sleep(window_seconds + 0.1)

        # Now should allow new requests
        result = await limiter.acquire(test_key, max_calls, window_seconds)
        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_independent_keys(self, limiter):
        """
        Test that different keys have independent rate limits.

        Each key should maintain its own sliding window counter.
        """
        key1 = f"test:user:123:contacts:{int(time.time() * 1000000)}"
        key2 = f"test:user:456:contacts:{int(time.time() * 1000000)}"

        max_calls = 5
        window_seconds = 60

        # Fill limit for key1
        for _ in range(max_calls):
            result = await limiter.acquire(key1, max_calls, window_seconds)
            assert result is True

        # key1 should be blocked
        result = await limiter.acquire(key1, max_calls, window_seconds)
        assert result is False

        # key2 should still be allowed (independent counter)
        result = await limiter.acquire(key2, max_calls, window_seconds)
        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_reset_clears_counter(self, limiter, test_key):
        """
        Test that reset() clears the rate limit counter.

        After reset, requests should be allowed again.
        """
        max_calls = 3
        window_seconds = 60

        # Fill up the limit
        for _ in range(max_calls):
            await limiter.acquire(test_key, max_calls, window_seconds)

        # Verify limit reached
        result = await limiter.acquire(test_key, max_calls, window_seconds)
        assert result is False

        # Reset counter
        await limiter.reset(test_key)

        # Should allow requests again
        result = await limiter.acquire(test_key, max_calls, window_seconds)
        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_current_usage_accuracy(self, limiter, test_key):
        """
        Test that get_current_usage() returns accurate count.

        Usage should reflect actual number of requests in window.
        """
        max_calls = 10
        window_seconds = 60

        # Initial usage should be 0
        usage = await limiter.get_current_usage(test_key, window_seconds)
        assert usage == 0

        # Make 5 requests
        for _ in range(5):
            await limiter.acquire(test_key, max_calls, window_seconds)

        # Usage should be 5
        usage = await limiter.get_current_usage(test_key, window_seconds)
        assert usage == 5

        # Make 3 more requests
        for _ in range(3):
            await limiter.acquire(test_key, max_calls, window_seconds)

        # Usage should be 8
        usage = await limiter.get_current_usage(test_key, window_seconds)
        assert usage == 8

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_requests_same_key(self, limiter, test_key):
        """
        Test concurrent requests to same key are handled correctly.

        Lua script atomicity should prevent race conditions.
        """
        max_calls = 10
        window_seconds = 60

        # Launch 15 concurrent requests (5 over limit)
        tasks = [limiter.acquire(test_key, max_calls, window_seconds) for _ in range(15)]
        results = await asyncio.gather(*tasks)

        # Exactly max_calls (10) should be allowed
        allowed_count = sum(results)
        assert allowed_count == max_calls

        # Verify usage matches
        usage = await limiter.get_current_usage(test_key, window_seconds)
        assert usage == max_calls

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_window_expiration(self, limiter):
        """
        Test that Redis keys expire after window + buffer.

        Keys should be automatically cleaned up to prevent memory leaks.
        """
        key = f"test:expiration:{int(time.time() * 1000000)}"
        window_seconds = 1

        # Make a request
        await limiter.acquire(key, max_calls=10, window_seconds=window_seconds)

        # Key should exist
        exists = await limiter.redis.exists(key)
        assert exists == 1

        # Wait for expiration (window + buffer = 11 seconds)
        await asyncio.sleep(window_seconds + 11)

        # Key should be expired
        exists = await limiter.redis.exists(key)
        assert exists == 0


class TestRedisRateLimiterMultiInstance:
    """Test rate limiter behavior across multiple instances (simulated)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_limiters_same_key(self, redis_client):
        """
        Test that multiple limiter instances share rate limit.

        Simulates horizontal scaling - multiple app instances should
        enforce same rate limit using shared Redis state.
        """
        # Create two limiter instances (simulating two app servers)
        limiter1 = RedisRateLimiter(redis_client)
        limiter2 = RedisRateLimiter(redis_client)

        test_key = f"test:multi_instance:{int(time.time() * 1000000)}"
        max_calls = 10
        window_seconds = 60

        # Limiter1 makes 6 requests
        for _ in range(6):
            result = await limiter1.acquire(test_key, max_calls, window_seconds)
            assert result is True

        # Limiter2 makes 4 requests (should fill remaining limit)
        for _ in range(4):
            result = await limiter2.acquire(test_key, max_calls, window_seconds)
            assert result is True

        # Both limiters should now block (limit reached)
        result1 = await limiter1.acquire(test_key, max_calls, window_seconds)
        result2 = await limiter2.acquire(test_key, max_calls, window_seconds)

        assert result1 is False
        assert result2 is False

        # Verify total usage
        usage = await limiter1.get_current_usage(test_key, window_seconds)
        assert usage == max_calls

        # Cleanup
        await limiter1.close()
        await limiter2.close()


class TestRedisRateLimiterPerformance:
    """Performance benchmarks for rate limiter."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.benchmark
    async def test_acquire_latency(self, limiter, test_key):
        """
        Benchmark acquire() latency.

        Should complete in < 10ms on localhost Redis.
        """
        iterations = 100

        start = time.time()
        for _ in range(iterations):
            await limiter.acquire(test_key, max_calls=1000, window_seconds=60)
        elapsed = time.time() - start

        avg_latency_ms = (elapsed / iterations) * 1000

        # Average latency should be < 10ms (usually 1-3ms on localhost)
        assert avg_latency_ms < 10, f"Avg latency {avg_latency_ms:.2f}ms exceeds 10ms"

        print(f"\nAverage acquire() latency: {avg_latency_ms:.2f}ms ({iterations} iterations)")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.benchmark
    async def test_concurrent_throughput(self, limiter):
        """
        Benchmark concurrent request throughput.

        Should handle 100+ concurrent requests efficiently.
        """
        num_concurrent = 100
        test_key = f"test:throughput:{int(time.time() * 1000000)}"

        start = time.time()
        tasks = [
            limiter.acquire(test_key, max_calls=1000, window_seconds=60)
            for _ in range(num_concurrent)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start

        # All should succeed
        assert all(results)

        throughput = num_concurrent / elapsed

        # Should handle > 100 requests/second
        assert throughput > 100, f"Throughput {throughput:.0f} req/s is too low"

        print(
            f"\nConcurrent throughput: {throughput:.0f} req/s ({num_concurrent} requests in {elapsed:.3f}s)"
        )
