"""Notification SSE stream — per-user cap wiring (newest wins).

Pins the router-level behavior added after the 2026-08-14/15 Redis pool
exhaustion: each stream registers in the per-user registry, checks its slot
at every keepalive tick, announces ``superseded`` and closes when evicted,
and only deletes the shared per-user SSE marker (OAuth-health dedup) when it
was the LAST stream of that user.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.notifications.router import stream_notifications


class _FakePubSub:
    """Scripted pub/sub: always times out (keepalive path)."""

    def __init__(self) -> None:
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.channel = channel

    async def get_message(self, *, ignore_subscribe_messages: bool, timeout: float):
        await asyncio.sleep(0)
        return None

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed.append(channel)

    async def close(self) -> None:
        self.closed = True


def _fake_redis(*, zscore_result, zcard_result: int) -> AsyncMock:
    redis = AsyncMock()
    redis.pubsub = lambda: _FakePubSub()
    redis.set = AsyncMock()
    redis.expire = AsyncMock()
    redis.delete = AsyncMock()
    redis.zadd = AsyncMock()
    redis.zremrangebyrank = AsyncMock()
    redis.zscore = AsyncMock(return_value=zscore_result)
    redis.zrem = AsyncMock()
    redis.zcard = AsyncMock(return_value=zcard_result)
    return redis


async def _collect(response, limit: int) -> list[str]:
    chunks: list[str] = []
    iterator = response.body_iterator
    try:
        async for chunk in iterator:
            chunks.append(chunk)
            if len(chunks) >= limit:
                break
    finally:
        await iterator.aclose()
    return chunks


@pytest.fixture
def user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


async def _run_stream(monkeypatch, user, redis, limit: int) -> list[str]:
    from src.infrastructure.cache import redis as redis_module

    async def fake_get_redis_cache():
        return redis

    monkeypatch.setattr(redis_module, "get_redis_cache", fake_get_redis_cache)
    response = await stream_notifications(current_user=user)
    return await _collect(response, limit)


class TestStreamRegistration:
    async def test_connection_registers_stream_with_settings_cap(self, monkeypatch, user) -> None:
        redis = _fake_redis(zscore_result=1.0, zcard_result=1)
        chunks = await _run_stream(monkeypatch, user, redis, limit=2)

        assert chunks[0].startswith("event: connected")
        redis.zadd.assert_awaited()
        # Trim derives from the SETTING, never a hardcoded cap.
        cap = settings.sse_max_streams_per_user
        redis.zremrangebyrank.assert_awaited_with(f"sse:streams:{user.id}", 0, -(cap + 1))


class TestEviction:
    async def test_evicted_stream_announces_superseded_and_closes(self, monkeypatch, user) -> None:
        redis = _fake_redis(zscore_result=None, zcard_result=1)
        chunks = await _run_stream(monkeypatch, user, redis, limit=10)

        # connected, then the eviction verdict at the first keepalive tick —
        # and the generator ENDS (no further keepalives).
        assert chunks[0].startswith("event: connected")
        assert any(c.startswith("event: superseded") for c in chunks)
        assert chunks[-1].startswith("event: superseded")

    async def test_surviving_stream_keeps_sending_keepalives(self, monkeypatch, user) -> None:
        redis = _fake_redis(zscore_result=1.0, zcard_result=1)
        chunks = await _run_stream(monkeypatch, user, redis, limit=3)

        assert chunks[0].startswith("event: connected")
        assert chunks[1].startswith(": keepalive")
        assert chunks[2].startswith(": keepalive")


class TestSharedMarkerCleanup:
    async def test_last_stream_deletes_the_shared_marker(self, monkeypatch, user) -> None:
        redis = _fake_redis(zscore_result=None, zcard_result=0)
        await _run_stream(monkeypatch, user, redis, limit=10)

        assert redis.zrem.await_args.args[0] == f"sse:streams:{user.id}"
        redis.delete.assert_awaited_once_with(f"sse:connection:{user.id}")

    async def test_marker_survives_while_other_streams_remain(self, monkeypatch, user) -> None:
        """Multi-tab regression: the first tab to close must not delete the
        marker the OAuth health check reads while another tab still streams."""
        redis = _fake_redis(zscore_result=None, zcard_result=1)
        await _run_stream(monkeypatch, user, redis, limit=10)

        redis.delete.assert_not_awaited()
