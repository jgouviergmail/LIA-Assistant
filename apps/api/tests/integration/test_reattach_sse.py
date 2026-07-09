"""Integration tests: SSE reattach semantics of stream_run_as_sse (Lot 2).

Real Redis. Covers: replay flushed without pacing + ``: replay-end``
boundary comment, stale voice_audio_chunk dropped during replay (kept
live), and subscriber presence INCR/DECR around the read.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.agents.api.router import stream_run_as_sse
from src.infrastructure.streaming.run_stream_broker import (
    has_listeners,
    listeners_key,
    publish_chunk,
    publish_end,
    run_stream_key,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client(monkeypatch):
    """Real Redis client; patches the router-side get_redis_cache singleton."""
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as e:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {e}")

    async def _get_test_redis() -> Redis:
        return redis

    monkeypatch.setattr("src.infrastructure.cache.redis.get_redis_cache", _get_test_redis)
    yield redis
    await redis.aclose()


def _chunk(chunk_type: str, content: str) -> str:
    return json.dumps({"type": chunk_type, "content": content, "metadata": None})


async def test_replay_end_comment_marks_backlog_boundary(redis_client) -> None:
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    try:
        # Backlog before the subscriber attaches
        await publish_chunk(redis_client, stream_id, _chunk("token", "old1"))
        await publish_chunk(redis_client, stream_id, _chunk("token", "old2"))

        async def live_tail() -> None:
            await asyncio.sleep(0.3)
            await publish_chunk(redis_client, stream_id, _chunk("token", "live1"))
            await publish_end(redis_client, stream_id, "completed")

        tail = asyncio.create_task(live_tail())
        lines = [line async for line in stream_run_as_sse(stream_id)]
        await tail

        data_contents = [
            json.loads(line[6:])["content"] for line in lines if line.startswith("data: ")
        ]
        assert data_contents == ["old1", "old2", "live1"]
        # The boundary comment sits between the backlog and the live tail
        boundary_index = lines.index(": replay-end\n\n")
        old2_index = lines.index(f"data: {_chunk('token', 'old2')}\n\n")
        live1_index = lines.index(f"data: {_chunk('token', 'live1')}\n\n")
        assert old2_index < boundary_index < live1_index
    finally:
        await redis_client.delete(run_stream_key(stream_id))


async def test_stale_voice_chunks_dropped_in_replay_kept_live(redis_client) -> None:
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    try:
        # Backlog: one voice chunk (stale audio) + one token
        await publish_chunk(redis_client, stream_id, _chunk("voice_audio_chunk", "STALE"))
        await publish_chunk(redis_client, stream_id, _chunk("token", "old"))

        async def live_tail() -> None:
            await asyncio.sleep(0.3)
            await publish_chunk(redis_client, stream_id, _chunk("voice_audio_chunk", "LIVE"))
            await publish_end(redis_client, stream_id, "completed")

        tail = asyncio.create_task(live_tail())
        payloads = [
            json.loads(line[6:])
            async for line in stream_run_as_sse(stream_id)
            if line.startswith("data: ")
        ]
        await tail

        voice_contents = [p["content"] for p in payloads if p["type"] == "voice_audio_chunk"]
        assert voice_contents == ["LIVE"]  # stale one dropped, live one kept
    finally:
        await redis_client.delete(run_stream_key(stream_id))


async def test_subscriber_presence_incr_then_decr(redis_client) -> None:
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    try:
        presence_during: list[bool] = []

        async def live_tail() -> None:
            await asyncio.sleep(0.3)
            presence_during.append(await has_listeners(redis_client, stream_id))
            await publish_chunk(redis_client, stream_id, _chunk("token", "x"))
            await publish_end(redis_client, stream_id, "completed")

        tail = asyncio.create_task(live_tail())
        async for _line in stream_run_as_sse(stream_id):
            pass
        await tail

        assert presence_during == [True]  # counted while attached
        assert await has_listeners(redis_client, stream_id) is False  # decremented after
    finally:
        await redis_client.delete(run_stream_key(stream_id))
        await redis_client.delete(listeners_key(stream_id))


async def test_presence_ttl_survives_long_attachment(redis_client, monkeypatch) -> None:
    """Regression (self-review 2026-07): the presence counter must NOT expire
    while a subscriber stays attached longer than the listener TTL — voice
    would be wrongly skipped mid-run. The relay loop re-arms it (~TTL/3).
    """
    monkeypatch.setattr(settings, "background_runs_listener_ttl_seconds", 2)
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    presence_probes: list[bool] = []

    async def slow_producer() -> None:
        # Longer than the 2s TTL: without touches the counter would vanish
        for i in range(4):
            await asyncio.sleep(1.0)
            presence_probes.append(await has_listeners(redis_client, stream_id))
            await publish_chunk(redis_client, stream_id, _chunk("token", f"t{i}"))
        await publish_end(redis_client, stream_id, "completed")

    try:
        producer = asyncio.create_task(slow_producer())
        async for _line in stream_run_as_sse(stream_id):
            pass
        await producer
        # The subscriber stayed attached ~4s (2x TTL): every probe must be True
        assert presence_probes == [True, True, True, True]
        # And decremented away after detach
        assert await has_listeners(redis_client, stream_id) is False
    finally:
        await redis_client.delete(run_stream_key(stream_id))
        await redis_client.delete(listeners_key(stream_id))
