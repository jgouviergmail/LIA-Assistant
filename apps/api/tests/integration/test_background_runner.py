"""Integration tests for the detached chat-run producer (real Redis, ADR-117).

The producer consumes a chat-chunk async generator and publishes every
chunk to the run stream, ALWAYS terminating with an end marker:
  - generator completes  -> end(completed)
  - generator raises     -> end(error)   (the real generator emits its own
                                          error/done chunks before raising)
  - task cancelled       -> end(killed) + finalize_partial callback
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.agents.api.background_runner import (
    drain_chat_producers,
    get_active_chat_producer_count,
    spawn_chat_run_producer,
)
from src.domains.agents.api.schemas import ChatStreamChunk
from src.infrastructure.streaming.run_stream_broker import (
    RunStreamEvent,
    active_run_key,
    get_active_run,
    register_active_run,
    run_stream_key,
    subscribe,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client(monkeypatch):
    """Real Redis client (same decode mode as get_redis_cache). Skips if down.

    Also patches the runner module's get_redis_cache: the production
    singleton is bound to the FIRST event loop that creates it, while
    pytest-asyncio gives each test its own loop — reusing the singleton
    across tests would hang on a closed loop.
    """
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as e:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {e}")

    async def _get_test_redis() -> Redis:
        return redis

    monkeypatch.setattr("src.domains.agents.api.background_runner.get_redis_cache", _get_test_redis)
    yield redis
    await redis.aclose()


async def _collect(redis: Redis, run_id: str) -> list[RunStreamEvent]:
    return [event async for event in subscribe(redis, run_id) if event.kind != "keepalive"]


def _token(content: str) -> ChatStreamChunk:
    return ChatStreamChunk(type="token", content=content, metadata=None)


async def test_producer_publishes_all_chunks_and_completed_marker(redis_client) -> None:
    run_id = f"test_{uuid.uuid4().hex[:8]}"

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        for i in range(5):
            yield _token(f"tok{i}")
            await asyncio.sleep(0.01)

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(), run_id=run_id, stream_id=run_id, user_id="u", session_id="s"
        )
        events = await _collect(redis_client, run_id)
        await task
        assert [e.kind for e in events] == ["chunk"] * 5 + ["end"]
        assert events[-1].payload == "completed"
        assert get_active_chat_producer_count() == 0
    finally:
        await redis_client.delete(run_stream_key(run_id))


async def test_producer_failing_generator_ends_with_error_marker(redis_client) -> None:
    run_id = f"test_{uuid.uuid4().hex[:8]}"

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("partial")
        raise RuntimeError("llm exploded")

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(), run_id=run_id, stream_id=run_id, user_id="u", session_id="s"
        )
        events = await _collect(redis_client, run_id)
        await task  # must NOT re-raise: producer swallows and marks the stream
        assert events[-1].kind == "end"
        assert events[-1].payload == "error"
    finally:
        await redis_client.delete(run_stream_key(run_id))


async def test_cancelled_producer_ends_killed_and_finalizes_partial(redis_client) -> None:
    run_id = f"test_{uuid.uuid4().hex[:8]}"
    finalized: list[tuple[str, str]] = []

    async def finalize_partial(content: str, reason: str) -> None:
        finalized.append((content, reason))

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("hello ")
        yield _token("world")
        await asyncio.sleep(30)  # cancellation lands here
        yield _token("never")

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(),
            run_id=run_id,
            stream_id=run_id,
            user_id="u",
            session_id="s",
            finalize_partial=finalize_partial,
        )
        await asyncio.sleep(0.3)  # let the two chunks flow
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        events = await _collect(redis_client, run_id)
        assert events[-1].kind == "end"
        assert events[-1].payload == "killed"
        assert finalized == [("hello world", "killed")]
    finally:
        await redis_client.delete(run_stream_key(run_id))


async def test_content_replacement_replaces_accumulated_content(redis_client) -> None:
    run_id = f"test_{uuid.uuid4().hex[:8]}"
    finalized: list[tuple[str, str]] = []

    async def finalize_partial(content: str, reason: str) -> None:
        finalized.append((content, reason))

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("raw ")
        yield ChatStreamChunk(type="content_replacement", content="FINAL enriched", metadata=None)
        await asyncio.sleep(30)

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(),
            run_id=run_id,
            stream_id=run_id,
            user_id="u",
            session_id="s",
            finalize_partial=finalize_partial,
        )
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finalized == [("FINAL enriched", "killed")]
    finally:
        await redis_client.delete(run_stream_key(run_id))


async def test_hitl_resumption_fresh_stream_avoids_stale_end_marker(redis_client) -> None:
    """HITL resumption reuses run_id (billing) but MUST get a fresh stream.

    Regression guard: publishing the resumption onto the interrupt phase's
    stream would append after that phase's terminal marker, so a
    replay-from-0 subscriber would stop at the stale marker and never see
    the resumption content.
    """
    billing_run_id = f"test_{uuid.uuid4().hex[:8]}"
    stream_phase1 = f"{billing_run_id}_s1"
    stream_phase2 = f"{billing_run_id}_s2"

    async def phase1() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("hitl question")  # interrupt phase ends cleanly

    async def phase2() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("resumption ")
        yield _token("answer")

    try:
        # Phase 1 (interrupt): completes and writes its terminal marker
        await spawn_chat_run_producer(
            chat_stream=phase1(),
            run_id=billing_run_id,
            stream_id=stream_phase1,
            user_id="u",
            session_id="s",
        )
        # Phase 2 (resumption): SAME billing run_id, FRESH stream
        await spawn_chat_run_producer(
            chat_stream=phase2(),
            run_id=billing_run_id,
            stream_id=stream_phase2,
            user_id="u",
            session_id="s",
        )
        events = await _collect(redis_client, stream_phase2)
        contents = [json.loads(e.payload)["content"] for e in events if e.kind == "chunk"]
        # The subscriber sees ONLY the resumption content, fully, and terminates
        assert contents == ["resumption ", "answer"]
        assert events[-1].kind == "end"
        assert events[-1].payload == "completed"
    finally:
        await redis_client.delete(run_stream_key(stream_phase1))
        await redis_client.delete(run_stream_key(stream_phase2))


async def test_drain_chat_producers_waits_then_reports_pending(redis_client) -> None:
    """The shutdown drain awaits fast producers and reports slow ones."""
    fast_id = f"test_{uuid.uuid4().hex[:8]}"
    slow_id = f"test_{uuid.uuid4().hex[:8]}"

    async def fast() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("quick")
        await asyncio.sleep(0.5)  # still in flight when the drain starts

    async def slow() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("slow")
        await asyncio.sleep(30)

    slow_task = None
    try:
        spawn_chat_run_producer(
            chat_stream=fast(), run_id=fast_id, stream_id=fast_id, user_id="u", session_id="s"
        )
        slow_task = spawn_chat_run_producer(
            chat_stream=slow(), run_id=slow_id, stream_id=slow_id, user_id="u", session_id="s"
        )
        await asyncio.sleep(0.1)  # both producers started, both still in flight
        done, pending = await drain_chat_producers(timeout=2.0)
        assert done == 1  # the fast producer finished within the drain window
        assert pending == 1  # the slow one is honestly reported as pending
    finally:
        if slow_task is not None and not slow_task.done():
            slow_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await slow_task
        await redis_client.delete(run_stream_key(fast_id))
        await redis_client.delete(run_stream_key(slow_id))


async def test_producer_heartbeat_keeps_lock_then_releases_on_completion(
    redis_client, monkeypatch
) -> None:
    """Lot 2: the heartbeat outlives the lock TTL; completion releases it."""
    monkeypatch.setattr(settings, "background_runs_active_ttl_seconds", 2)
    monkeypatch.setattr(settings, "background_runs_heartbeat_seconds", 1)
    conv = f"conv_{uuid.uuid4().hex[:8]}"
    stream_id = f"s_{uuid.uuid4().hex[:8]}"

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("start")
        await asyncio.sleep(3.5)  # > lock TTL: only the heartbeat keeps it alive
        yield _token("end")

    try:
        assert await register_active_run(redis_client, conv, run_id="R", stream_id=stream_id)
        task = spawn_chat_run_producer(
            chat_stream=stream(),
            run_id="R",
            stream_id=stream_id,
            user_id="u",
            session_id="s",
            conversation_id=conv,
        )
        await asyncio.sleep(3.0)  # beyond the original TTL
        assert await get_active_run(redis_client, conv) is not None  # heartbeat kept it
        await task
        assert await get_active_run(redis_client, conv) is None  # released at completion
    finally:
        await redis_client.delete(active_run_key(conv))
        await redis_client.delete(run_stream_key(stream_id))


async def test_killed_producer_releases_lock_immediately(redis_client, monkeypatch) -> None:
    """Lot 2: a cancelled producer releases the lock without waiting for TTL."""
    monkeypatch.setattr(settings, "background_runs_active_ttl_seconds", 30)
    conv = f"conv_{uuid.uuid4().hex[:8]}"
    stream_id = f"s_{uuid.uuid4().hex[:8]}"

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("start")
        await asyncio.sleep(60)

    try:
        assert await register_active_run(redis_client, conv, run_id="R", stream_id=stream_id)
        task = spawn_chat_run_producer(
            chat_stream=stream(),
            run_id="R",
            stream_id=stream_id,
            user_id="u",
            session_id="s",
            conversation_id=conv,
        )
        await asyncio.sleep(0.3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Released by the shielded finally — NOT left to the 30s TTL
        assert await get_active_run(redis_client, conv) is None
    finally:
        await redis_client.delete(active_run_key(conv))
        await redis_client.delete(run_stream_key(stream_id))


async def test_user_cancel_signal_ends_run_as_cancelled(redis_client) -> None:
    """Lot 3: the cross-worker cancel signal cooperatively stops the producer.

    Expected terminal sequence on the stream: the already-published chunks,
    then a SYNTHESIZED done chunk carrying metadata.cancelled (subscribers
    finish their normal SSE lifecycle), then the end marker with status
    "cancelled" (not "killed"). The partial content is finalized with the
    "cancelled" reason and the consumed signal is cleared.
    """
    from src.infrastructure.streaming.run_stream_broker import (
        is_cancel_requested,
        request_cancel,
    )

    run_id = f"test_{uuid.uuid4().hex[:8]}"
    finalized: list[tuple[str, str]] = []

    async def finalize_partial(content: str, reason: str) -> None:
        finalized.append((content, reason))

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("partial ")
        yield _token("answer")
        await asyncio.sleep(30)  # the cancel lands here
        yield _token("never")

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(),
            run_id=run_id,
            stream_id=run_id,
            user_id="u",
            session_id="s",
            finalize_partial=finalize_partial,
        )
        await asyncio.sleep(0.3)  # let the two chunks flow
        await request_cancel(redis_client, run_id)
        with pytest.raises(asyncio.CancelledError):
            await task  # watcher polls every 1s -> cancelled within ~1s

        events = await _collect(redis_client, run_id)
        # Terminal sequence: tokens..., synthesized done(cancelled), end(cancelled)
        assert events[-1].kind == "end"
        assert events[-1].payload == "cancelled"
        done_chunks = [
            json.loads(e.payload) for e in events if e.kind == "chunk" and '"done"' in e.payload
        ]
        assert len(done_chunks) == 1
        assert done_chunks[0]["metadata"] == {"cancelled": True}
        # Partial archived with the user-cancel reason
        assert finalized == [("partial answer", "cancelled")]
        # Consumed signal cleared
        assert await is_cancel_requested(redis_client, run_id) is False
    finally:
        await redis_client.delete(run_stream_key(run_id))


async def test_hard_kill_still_reports_killed_not_cancelled(redis_client) -> None:
    """Lot 3 guard: a shutdown-drain kill (no user signal) keeps status
    "killed" — the two abort causes must stay distinguishable in metrics
    and archive metadata."""
    run_id = f"test_{uuid.uuid4().hex[:8]}"

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield _token("x")
        await asyncio.sleep(30)

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(), run_id=run_id, stream_id=run_id, user_id="u", session_id="s"
        )
        await asyncio.sleep(0.3)
        task.cancel()  # hard kill, no cancel signal
        with pytest.raises(asyncio.CancelledError):
            await task
        events = await _collect(redis_client, run_id)
        assert events[-1].payload == "killed"
        # No synthesized done chunk on hard kill
        assert not any(e.kind == "chunk" and '"done"' in e.payload for e in events)
    finally:
        await redis_client.delete(run_stream_key(run_id))
