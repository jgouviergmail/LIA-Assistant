"""A real Pub/Sub notification stream closes and releases its connection on revocation."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest
from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from starlette.types import Message

from src.core.config import settings
from src.domains.agents.api import session_watch
from src.domains.notifications import router
from src.infrastructure.cache import redis as redis_module
from src.infrastructure.cache.session_store import SessionStore
from src.infrastructure.cache.user_channel import user_notifications_channel

pytestmark = pytest.mark.integration


async def test_a_busy_revoked_stream_stops_before_the_next_payload_and_releases_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    assert redis.connection_pool.connection_kwargs["db"] == 15
    await redis.ping()
    pubsub = redis.pubsub()
    owner = uuid4()
    store = SessionStore(redis)
    session = await store.create_session(user_id=str(owner))
    clock = [0.0]

    async def connection() -> Redis:
        return redis

    monkeypatch.setattr(redis_module, "get_redis_cache", connection)
    monkeypatch.setattr(session_watch, "get_redis_session", connection)
    monkeypatch.setattr(redis, "pubsub", lambda: pubsub)
    monkeypatch.setattr(router, "monotonic", lambda: clock[0])
    monkeypatch.setattr(settings, "http_timeout_sse_polling", 1)
    response = await router.stream_notifications(
        current_user=SimpleNamespace(id=owner), lia_session=session.session_id
    )
    events = response.body_iterator
    try:
        assert (await anext(events)).startswith("event: connected")
        subscribed = await pubsub.get_message(ignore_subscribe_messages=False, timeout=2)
        assert subscribed is not None and subscribed["type"] == "subscribe"
        assert len(redis.connection_pool._in_use_connections) == 1
        await redis.publish(user_notifications_channel(owner), '{"text":"first"}')
        assert '"first"' in await anext(events)

        await store.delete_session(session.session_id)
        clock[0] = 2
        await redis.publish(user_notifications_channel(owner), '{"text":"must not arrive"}')
        closing = await anext(events)
        assert closing.startswith("event: session_revoked")
        assert "must not arrive" not in closing
        with pytest.raises(StopAsyncIteration):
            await anext(events)
        assert pubsub.connection is None
        assert not redis.connection_pool._in_use_connections
    finally:
        await events.aclose()
        await pubsub.aclose()
        await store.delete_session(session.session_id)
        await redis.delete(
            f"sse:connection:{owner}", f"sse:streams:{owner}", f"user:{owner}:sessions"
        )
        await redis.aclose()


async def test_repeated_asgi_disconnects_do_not_exhaust_a_two_connection_redis_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use real Pub/Sub and ASGI level cancellation, with no spare-capacity workaround."""
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True, max_connections=2)
    assert redis.connection_pool.connection_kwargs["db"] == 15
    owner = uuid4()
    channel = user_notifications_channel(owner)
    created: list[PubSub] = []
    native_pubsub = redis.pubsub

    def open_pubsub() -> PubSub:
        pubsub = native_pubsub()
        created.append(pubsub)
        return pubsub

    async def connection() -> Redis:
        return redis

    monkeypatch.setattr(redis_module, "get_redis_cache", connection)
    monkeypatch.setattr(redis, "pubsub", open_pubsub)
    try:
        await redis.ping()
        for _ in range(24):
            connected = anyio.Event()
            response = await router.stream_notifications(
                current_user=SimpleNamespace(id=owner), lia_session=None
            )

            async def receive(ready: anyio.Event = connected) -> Message:
                await ready.wait()
                return {"type": "http.disconnect"}

            async def send(message: Message, ready: anyio.Event = connected) -> None:
                body = message.get("body", b"")
                if isinstance(body, bytes) and body.startswith(b"event: connected"):
                    ready.set()

            await asyncio.wait_for(
                response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send),
                timeout=5,
            )
            assert (await redis.pubsub_numsub(channel))[0][1] == 0
            assert await redis.exists(f"sse:connection:{owner}", f"sse:streams:{owner}") == 0
            assert await redis.ping()
    finally:
        for pubsub in created:
            await pubsub.aclose()
        await redis.delete(f"sse:connection:{owner}", f"sse:streams:{owner}")
        await redis.aclose()
