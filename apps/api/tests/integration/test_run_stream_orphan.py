"""Integration tests: subscriber orphan exit on hard-killed producers.

2026-07 hard-kill audit (ADR-117 hardening). A producer dying WITHOUT its
terminal marker (kill -9, OOM, power loss) used to leave subscribers looping
on keepalives forever. The SSE relay now exits with a synthetic error +
done chunk pair (standard types) once the conversation's active-run lock has
been observed missing (or foreign) for a full grace period AND no chunk
arrived over the same window.

The heartbeated lock is the liveness truth, NOT chunk silence: a live-but-
silent run (long LLM call) must never be declared orphaned.
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
    active_run_key,
    has_listeners,
    listeners_key,
    publish_chunk,
    publish_end,
    register_active_run,
    run_stream_key,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client(monkeypatch):
    """Real Redis client (same decode mode as get_redis_cache). Skips if down.

    Patches the cache module's get_redis_cache: stream_run_as_sse resolves it
    lazily at call time, and the production singleton is bound to the FIRST
    event loop that creates it while pytest-asyncio gives each test its own.
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


@pytest.fixture
def fast_orphan_settings(monkeypatch):
    """Shrink the grace and the XREAD window so tests run in seconds."""
    monkeypatch.setattr(settings, "background_runs_orphan_grace_seconds", 1)
    monkeypatch.setattr(settings, "background_runs_xread_block_ms", 250)


def _token(content: str) -> str:
    return json.dumps({"type": "token", "content": content, "metadata": None})


def _data_frames(lines: list[str]) -> list[dict]:
    return [
        json.loads(line.removeprefix("data: ").strip())
        for line in lines
        if line.startswith("data: ")
    ]


async def _consume(lines: list[str], stream_id: str, conversation_id: str | None) -> None:
    async for line in stream_run_as_sse(
        stream_id, conversation_id=conversation_id, user_language="en"
    ):
        lines.append(line)


async def test_orphan_stream_exits_with_synthetic_error(redis_client, fast_orphan_settings) -> None:
    """Producer hard-killed (chunks, no end marker, lock gone): the relay
    replays the backlog, then exits with error + done within the grace."""
    conv = f"conv_{uuid.uuid4().hex[:8]}"
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    try:
        # Simulated hard kill: chunks were published, then the producer died
        # without a terminal marker and its lock expired (never registered).
        await publish_chunk(redis_client, stream_id, _token("partial "))
        await publish_chunk(redis_client, stream_id, _token("answer"))

        lines: list[str] = []
        await asyncio.wait_for(_consume(lines, stream_id, conv), timeout=10)

        frames = _data_frames(lines)
        # Backlog relayed first, replay boundary emitted at the first keepalive
        assert [f["content"] for f in frames[:2]] == ["partial ", "answer"]
        assert ": replay-end\n\n" in lines
        # Synthetic terminal sequence: error chunk then done chunk
        error_frames = [f for f in frames if f["type"] == "error"]
        assert len(error_frames) == 1
        assert error_frames[0]["metadata"]["error_type"] == "orphaned_run"
        assert error_frames[0]["content"]  # i18n message, never empty
        done_frames = [f for f in frames if f["type"] == "done"]
        assert len(done_frames) == 1
        assert done_frames[0]["metadata"]["error"] is True
        assert done_frames[0]["metadata"]["orphaned"] is True
        # Presence decayed on exit (finally-path decrement)
        assert await has_listeners(redis_client, stream_id) is False
    finally:
        await redis_client.delete(run_stream_key(stream_id))
        await redis_client.delete(listeners_key(stream_id))


async def test_silent_live_run_is_not_orphaned(redis_client, fast_orphan_settings) -> None:
    """The heartbeated lock is the truth: a silent run whose lock is alive
    and owned by this stream must keep the subscriber attached."""
    conv = f"conv_{uuid.uuid4().hex[:8]}"
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    task: asyncio.Task | None = None
    try:
        assert await register_active_run(redis_client, conv, run_id="R", stream_id=stream_id)
        await publish_chunk(redis_client, stream_id, _token("start"))

        lines: list[str] = []
        task = asyncio.create_task(_consume(lines, stream_id, conv))
        # Well beyond the 1s grace: probes run and see OUR live lock
        await asyncio.sleep(3)
        assert not task.done()
        assert not any(f["type"] == "error" for f in _data_frames(lines))

        await publish_end(redis_client, stream_id, "completed")
        await asyncio.wait_for(task, timeout=5)
        # Clean termination through the end marker — no synthetic chunks
        frames = _data_frames(lines)
        assert not any(f["type"] == "error" for f in frames)
        assert not any(f["type"] == "done" for f in frames)
    finally:
        if task is not None and not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await redis_client.delete(active_run_key(conv))
        await redis_client.delete(run_stream_key(stream_id))
        await redis_client.delete(listeners_key(stream_id))


async def test_foreign_lock_is_orphaned(redis_client, fast_orphan_settings) -> None:
    """A lock owned by a NEWER stream means this subscriber's run is dead
    (its producer can no longer heartbeat that lock): orphan exit."""
    conv = f"conv_{uuid.uuid4().hex[:8]}"
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    try:
        assert await register_active_run(
            redis_client, conv, run_id="R2", stream_id="a_newer_stream"
        )
        await publish_chunk(redis_client, stream_id, _token("stale"))

        lines: list[str] = []
        await asyncio.wait_for(_consume(lines, stream_id, conv), timeout=10)
        frames = _data_frames(lines)
        assert any(
            f["type"] == "error" and f["metadata"]["error_type"] == "orphaned_run" for f in frames
        )
    finally:
        await redis_client.delete(active_run_key(conv))
        await redis_client.delete(run_stream_key(stream_id))
        await redis_client.delete(listeners_key(stream_id))


async def test_no_conversation_disables_detection(redis_client, fast_orphan_settings) -> None:
    """conversation_id=None (no lock ever acquired — e.g. a brand-new user's
    first message): lock absence is the NORMAL state, detection stays off."""
    stream_id = f"s_{uuid.uuid4().hex[:8]}"
    task: asyncio.Task | None = None
    try:
        await publish_chunk(redis_client, stream_id, _token("x"))

        lines: list[str] = []
        task = asyncio.create_task(_consume(lines, stream_id, None))
        await asyncio.sleep(3)  # far beyond the grace: still attached
        assert not task.done()
        assert not any(f["type"] == "error" for f in _data_frames(lines))

        await publish_end(redis_client, stream_id, "completed")
        await asyncio.wait_for(task, timeout=5)
    finally:
        if task is not None and not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        await redis_client.delete(run_stream_key(stream_id))
        await redis_client.delete(listeners_key(stream_id))
