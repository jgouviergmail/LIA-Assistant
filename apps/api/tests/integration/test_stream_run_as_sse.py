"""Integration test: SSE formatting of a run stream (real Redis, ADR-117)."""

from __future__ import annotations

import json
import uuid

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.agents.api.router import stream_run_as_sse
from src.infrastructure.streaming.run_stream_broker import (
    publish_chunk,
    publish_end,
    run_stream_key,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client(monkeypatch):
    """Real Redis client; also patches the router's get_redis_cache.

    The production singleton binds to the first event loop that creates it;
    pytest-asyncio gives each test its own loop, so the subscriber must use
    a per-test client.
    """
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


async def test_sse_lines_order_and_termination(redis_client) -> None:
    run_id = f"test_{uuid.uuid4().hex[:8]}"
    try:
        await publish_chunk(
            redis_client, run_id, json.dumps({"type": "token", "content": "hi", "metadata": None})
        )
        await publish_chunk(
            redis_client,
            run_id,
            json.dumps({"type": "done", "content": "", "metadata": {"total_tokens": 1}}),
        )
        await publish_end(redis_client, run_id, "completed")

        lines = [line async for line in stream_run_as_sse(run_id)]

        data_lines = [line for line in lines if line.startswith("data: ")]
        assert len(data_lines) == 2
        assert json.loads(data_lines[0][6:])["type"] == "token"
        assert json.loads(data_lines[1][6:])["type"] == "done"
        # Every data line is a complete SSE frame
        assert all(line.endswith("\n\n") for line in data_lines)
        # Generator terminated by itself on the end marker (no hang) —
        # reaching this assertion at all proves it.
    finally:
        await redis_client.delete(run_stream_key(run_id))
