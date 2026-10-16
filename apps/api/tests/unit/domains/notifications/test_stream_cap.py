"""Notification SSE stream — per-user cap wiring (newest wins), revoked sessions.

Pins the router-level behavior added after the 2026-08-14/15 Redis pool
exhaustion: each stream registers in the per-user registry, checks its slot
at every keepalive tick, announces ``superseded`` and closes when evicted,
and only deletes the shared per-user SSE marker (OAuth-health dedup) when it
was the LAST stream of that user. The same tick closes a stream whose session
was revoked (point 22).
"""

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import structlog

from src.core.config import settings
from src.domains.notifications import router as notifications_router
from src.domains.notifications.router import stream_notifications
from tests.support.structlog_capture import fresh_module_logger


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

    async def aclose(self) -> None:
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


async def _run_stream(
    monkeypatch, user, redis, limit: int, lia_session: str | None = None
) -> list[str]:
    from src.infrastructure.cache import redis as redis_module

    async def fake_get_redis_cache():
        return redis

    monkeypatch.setattr(redis_module, "get_redis_cache", fake_get_redis_cache)
    response = await stream_notifications(current_user=user, lia_session=lia_session)
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


class TestARevokedSessionClosesTheStream:
    """Point 22: « sign out this device » cut the chat streams within one
    keepalive, never this one — a revoked device kept receiving the person's
    notifications for as long as its tab stayed open."""

    async def test_a_revoked_session_is_announced_and_the_stream_closes(
        self, monkeypatch, user
    ) -> None:
        still_valid = AsyncMock(return_value=False)
        monkeypatch.setattr(notifications_router, "session_still_valid", still_valid)
        redis = _fake_redis(zscore_result=1.0, zcard_result=1)

        chunks = await _run_stream(monkeypatch, user, redis, limit=10, lia_session="session-1")

        assert chunks[-1].startswith("event: session_revoked")
        assert not any(c.startswith(": keepalive") for c in chunks)
        still_valid.assert_awaited_with("session-1")

    async def test_a_live_session_keeps_streaming(self, monkeypatch, user) -> None:
        monkeypatch.setattr(
            notifications_router, "session_still_valid", AsyncMock(return_value=True)
        )
        redis = _fake_redis(zscore_result=1.0, zcard_result=1)

        chunks = await _run_stream(monkeypatch, user, redis, limit=3, lia_session="session-1")

        assert [chunk.strip() for chunk in chunks[1:]] == [": keepalive", ": keepalive"]


@pytest.mark.parametrize("closing", ["session_revoked", "superseded"])
async def test_continuous_notifications_cannot_postpone_authority_checks(
    monkeypatch, user, closing: str
) -> None:
    """A busy stream must check its deadline before handing out more private data."""
    clock = [0.0]
    timeouts: list[float] = []

    class Traffic(_FakePubSub):
        async def get_message(self, **kwargs):
            timeouts.append(kwargs["timeout"])
            clock[0] += 6.0
            return {"type": "message", "data": '{"content":"private"}'}

    redis = _fake_redis(zscore_result=None if closing == "superseded" else 1.0, zcard_result=1)
    pubsub = Traffic()
    redis.pubsub = lambda: pubsub
    monkeypatch.setattr(settings, "http_timeout_sse_polling", 10)
    monkeypatch.setattr(notifications_router, "monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(notifications_router, "session_still_valid", AsyncMock(return_value=False))

    chunks = await _run_stream(monkeypatch, user, redis, limit=6, lia_session="session-1")

    assert chunks[-1].startswith(f"event: {closing}")
    assert sum(chunk.startswith("event: notification") for chunk in chunks) == 1
    assert timeouts == [10.0, 4.0]
    assert pubsub.closed and pubsub.unsubscribed


@pytest.mark.parametrize("phase", ["subscribe", "poll"])
async def test_a_redis_failure_never_repeats_private_notification_text(
    monkeypatch, user, phase: str
) -> None:
    private = "PRIVATE_NOTIFICATION_BODY"

    class FailingPubSub(_FakePubSub):
        polls = 0

        async def subscribe(self, channel: str) -> None:
            if phase == "subscribe":
                raise ValueError(private)
            await super().subscribe(channel)

        async def get_message(self, **kwargs):
            self.polls += 1
            if self.polls == 1:
                raise ValueError(private)
            return None

    redis = _fake_redis(zscore_result=1.0, zcard_result=1)
    pubsub = FailingPubSub()
    redis.pubsub = lambda: pubsub
    monkeypatch.setattr(notifications_router.asyncio, "sleep", AsyncMock())
    with (
        contextmanager(fresh_module_logger)(notifications_router),
        structlog.testing.capture_logs() as logs,
    ):
        chunks = await _run_stream(monkeypatch, user, redis, limit=2)

    visible = [entry for entry in logs if entry["log_level"] != "debug"]
    assert private not in str(visible) and private not in str(chunks)
    assert any(entry.get("error_type") == "ValueError" for entry in visible)
    assert pubsub.closed


async def test_unsubscribe_failure_still_closes_the_pubsub_connection(monkeypatch, user) -> None:
    pubsub = _FakePubSub()
    pubsub.unsubscribe = AsyncMock(side_effect=OSError("unsubscribe failed"))
    redis = _fake_redis(zscore_result=1.0, zcard_result=1)
    redis.pubsub = lambda: pubsub

    chunks = await _run_stream(monkeypatch, user, redis, limit=1)

    assert chunks[0].startswith("event: connected")
    assert pubsub.closed
