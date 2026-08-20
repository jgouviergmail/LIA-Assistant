"""Per-user SSE stream registry — newest-wins capacity protection.

Incident 2026-08-14/15: one client's EventSource churn (mobile network)
accumulated dozens of half-dead notification streams, each pinning a pooled
Redis pub/sub connection, until ``MaxConnectionsError`` degraded every
Redis-backed path for hours. The registry bounds concurrent streams per user:
the newest stream always registers, the OLDEST is evicted (never the new one
— EventSource cannot read an HTTP refusal status, the Lot-6 trap of 2026-08).

The registry is a best-effort capacity guard, not a distributed lock: no
owner token or fencing is required (nothing durable is claimed), and every
failure mode is fail-open — a Redis outage must degrade to "no cap", never
kill streams.
"""

from unittest.mock import AsyncMock

import pytest

from src.domains.notifications import stream_registry


@pytest.fixture
def redis() -> AsyncMock:
    mock = AsyncMock()
    mock.zadd = AsyncMock()
    mock.zremrangebyrank = AsyncMock()
    mock.expire = AsyncMock()
    mock.zscore = AsyncMock(return_value=123.0)
    mock.zrem = AsyncMock()
    mock.zcard = AsyncMock(return_value=0)
    return mock


class TestRegisterStream:
    async def test_registers_then_trims_to_cap_newest_kept(self, redis: AsyncMock) -> None:
        await stream_registry.register_stream(redis, "user-1", "stream-a", cap=5, ttl_seconds=120)

        key = stream_registry._key("user-1")
        zadd_args = redis.zadd.await_args
        assert zadd_args.args[0] == key
        assert list(zadd_args.args[1].keys()) == ["stream-a"]
        # Rank trim keeps the `cap` HIGHEST scores (newest): remove everything
        # below rank -(cap) — i.e. indices [0, -(cap+1)].
        redis.zremrangebyrank.assert_awaited_once_with(key, 0, -6)
        redis.expire.assert_awaited_once_with(key, 120)

    async def test_scores_are_monotonic(self, redis: AsyncMock) -> None:
        """Two registrations in a row order newest-last (strictly increasing)."""
        await stream_registry.register_stream(redis, "u", "s1", cap=2, ttl_seconds=60)
        first = redis.zadd.await_args.args[1]["s1"]
        await stream_registry.register_stream(redis, "u", "s2", cap=2, ttl_seconds=60)
        second = redis.zadd.await_args.args[1]["s2"]
        assert second > first


class TestStreamIsActive:
    async def test_present_member_is_active(self, redis: AsyncMock) -> None:
        redis.zscore.return_value = 456.7
        assert await stream_registry.stream_is_active(redis, "u", "s") is True
        redis.zscore.assert_awaited_once_with(stream_registry._key("u"), "s")

    async def test_evicted_member_is_inactive(self, redis: AsyncMock) -> None:
        redis.zscore.return_value = None
        assert await stream_registry.stream_is_active(redis, "u", "s") is False

    async def test_redis_failure_is_fail_open(self, redis: AsyncMock) -> None:
        """An unreachable Redis must never evict a live stream."""
        redis.zscore.side_effect = ConnectionError("down")
        assert await stream_registry.stream_is_active(redis, "u", "s") is True


class TestUnregisterStream:
    async def test_removes_and_reports_remaining(self, redis: AsyncMock) -> None:
        redis.zcard.return_value = 2
        remaining = await stream_registry.unregister_stream(redis, "u", "s")
        redis.zrem.assert_awaited_once_with(stream_registry._key("u"), "s")
        assert remaining == 2

    async def test_redis_failure_reports_positive_remaining(self, redis: AsyncMock) -> None:
        """On failure the caller must NOT delete the shared per-user marker:
        pretending streams remain is the safe verdict for the OAuth-dedup key."""
        redis.zrem.side_effect = ConnectionError("down")
        remaining = await stream_registry.unregister_stream(redis, "u", "s")
        assert remaining > 0


class TestRefreshRegistry:
    async def test_extends_ttl(self, redis: AsyncMock) -> None:
        await stream_registry.refresh_registry(redis, "u", ttl_seconds=120)
        redis.expire.assert_awaited_once_with(stream_registry._key("u"), 120)

    async def test_redis_failure_is_swallowed(self, redis: AsyncMock) -> None:
        redis.expire.side_effect = ConnectionError("down")
        await stream_registry.refresh_registry(redis, "u", ttl_seconds=120)


class TestRegisterFailureIsFailOpen:
    async def test_register_failure_does_not_raise(self, redis: AsyncMock) -> None:
        redis.zadd.side_effect = ConnectionError("down")
        await stream_registry.register_stream(redis, "u", "s", cap=5, ttl_seconds=60)
