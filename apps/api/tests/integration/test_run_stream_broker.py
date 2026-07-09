"""Integration tests for the run stream broker against real Redis (ADR-117)."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.streaming.run_stream_broker import (
    publish_chunk,
    publish_end,
    run_stream_key,
    subscribe,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client():
    """Real Redis client (same decode mode as get_redis_cache). Skips if down."""
    try:
        redis = Redis.from_url(
            str(settings.redis_url),
            decode_responses=True,  # broker envelope fields are strings
        )
        await redis.ping()
        yield redis
        await redis.aclose()
    except Exception as e:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {e}")


async def test_publish_subscribe_roundtrip_with_replay(redis_client) -> None:
    """A late subscriber replays from 0-0 and terminates on the end marker."""
    run_id = f"test_{uuid.uuid4().hex[:8]}"
    try:
        for i in range(5):
            await publish_chunk(redis_client, run_id, json.dumps({"type": "token", "i": i}))
        await publish_end(redis_client, run_id, "completed")

        events = [event async for event in subscribe(redis_client, run_id)]

        chunk_events = [e for e in events if e.kind == "chunk"]
        assert [json.loads(e.payload)["i"] for e in chunk_events] == [0, 1, 2, 3, 4]
        assert events[-1].kind == "end"
        assert events[-1].payload == "completed"
        # TTL armed by publish_end
        assert await redis_client.ttl(run_stream_key(run_id)) > 0
    finally:
        await redis_client.delete(run_stream_key(run_id))


async def test_live_tail_and_keepalive(redis_client) -> None:
    """A subscriber attached before production sees a keepalive, then chunks."""
    run_id = f"test_{uuid.uuid4().hex[:8]}"

    async def producer() -> None:
        # Longer than one block window so the subscriber sees a keepalive first
        await asyncio.sleep(settings.background_runs_xread_block_ms / 1000 + 0.5)
        await publish_chunk(redis_client, run_id, json.dumps({"type": "token", "i": 0}))
        await publish_end(redis_client, run_id, "completed")

    try:
        prod = asyncio.create_task(producer())
        kinds = [event.kind async for event in subscribe(redis_client, run_id)]
        await prod
        assert "keepalive" in kinds
        assert "chunk" in kinds
        assert kinds[-1] == "end"
    finally:
        await redis_client.delete(run_stream_key(run_id))
