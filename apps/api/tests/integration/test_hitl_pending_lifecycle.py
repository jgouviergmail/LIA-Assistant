"""Integration tests: pending_hitl lifecycle across cancellation and cache.

Lot 1 Phase 0 (HITL action cards preamble) — pins two latent bug classes
BEFORE one-click approvals make them far more visible:

1. Cancel × pending_hitl (T0.1): a user cancel (ADR-117 stop button)
   landing after ``save_interrupt`` but before the run's terminal marker
   must NOT leave an orphan ``hitl_pending:{conversation_id}`` key —
   otherwise the next user message is misrouted into HITL resumption for
   a question the user deliberately killed. A hard kill (shutdown drain)
   must PRESERVE the pending state: the interrupt remains legitimately
   answerable after a restart.

2. Cache staleness (T0.2): the in-memory cache in front of
   ``_check_pending_hitl`` must be invalidated on save and on clear.
   Without invalidation, a user replying faster than the cache TTL
   (exactly what approval buttons enable) is routed as a NEW turn
   instead of a resumption (stale negative), or into a phantom
   resumption right after completion (stale positive).

These tests assert the DESIRED behavior: T0.1a and both T0.2 tests are
expected RED before the corresponding fixes land in this same lot.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.domains.agents.api import hitl_pending
from src.domains.agents.api.background_runner import spawn_chat_run_producer
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.utils.hitl_store import HITLStore
from src.infrastructure.streaming.run_stream_broker import (
    request_cancel,
    run_stream_key,
)

pytestmark = pytest.mark.integration


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def redis_client(monkeypatch):
    """Real Redis client (same decode mode as get_redis_cache). Skips if down.

    Patches every module-level ``get_redis_cache`` acquisition point used by
    the code under test: the production singleton is bound to the FIRST event
    loop that creates it, while pytest-asyncio gives each test its own loop.
    """
    try:
        redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
        await redis.ping()
    except Exception as e:  # noqa: BLE001 — environment guard, not logic
        pytest.skip(f"Redis not available: {e}")

    async def _get_test_redis() -> Redis:
        return redis

    monkeypatch.setattr("src.domains.agents.api.background_runner.get_redis_cache", _get_test_redis)
    # ``_check_pending_hitl_uncached`` imports get_redis_cache from the cache
    # module inside the function body — patch it at the source.
    monkeypatch.setattr("src.infrastructure.cache.redis.get_redis_cache", _get_test_redis)
    yield redis
    await redis.aclose()


@pytest.fixture(autouse=True)
def _reset_hitl_detection_cache():
    """Isolate the in-memory pending-HITL detection cache between tests.

    The cache lives in ``src.domains.agents.utils.hitl_cache`` (extracted from
    the router in Phase 0) — clear it around each test so cross-test residue
    never masks a stale-read regression.
    """
    from src.domains.agents.utils import hitl_cache as hitl_cache_module

    hitl_cache_module._cache.clear()
    yield
    hitl_cache_module._cache.clear()


def _store(redis: Redis) -> HITLStore:
    return HITLStore(redis_client=redis, ttl_seconds=settings.hitl_pending_data_ttl_seconds)


def _valid_interrupt_data(run_id: str) -> dict:
    """Minimal interrupt payload that passes ``clear_if_invalid`` validation."""
    return {
        "action_requests": [
            {
                "type": "tool_confirmation",
                "tool_name": "send_email_tool",
                "tool_args": {"to": "test@example.com", "subject": "hello"},
            }
        ],
        "run_id": run_id,
    }


# ============================================================================
# T0.1 — user cancel vs hard kill
# ============================================================================


async def test_user_cancel_clears_pending_hitl(redis_client: Redis) -> None:
    """A user cancel after save_interrupt must clear the orphan pending_hitl.

    Sequence mirrors the real streaming service: the run saves the pending
    interrupt (question generation in flight), then the user hits stop. The
    cancel watcher cancels the producer with status "cancelled" — the pending
    key must be gone afterwards, or the next message is misrouted into HITL
    resumption for a question the user killed.
    """
    conversation_id = str(uuid.uuid4())
    stream_id = f"test_{uuid.uuid4().hex[:8]}"
    store = _store(redis_client)
    interrupt_saved = asyncio.Event()

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="thinking… ", metadata=None)
        # Real sequence: streaming service saves the pending interrupt while
        # the question is still being generated/streamed.
        await store.save_interrupt(conversation_id, _valid_interrupt_data(stream_id))
        interrupt_saved.set()
        # Question generation "in flight" — cancellation lands here.
        await asyncio.sleep(3600)
        yield ChatStreamChunk(type="token", content="never reached", metadata=None)

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(),
            run_id=stream_id,
            stream_id=stream_id,
            user_id="u",
            session_id="s",
            conversation_id=conversation_id,
        )
        await asyncio.wait_for(interrupt_saved.wait(), timeout=10)
        assert await store.has_interrupt(conversation_id), "precondition: pending saved"

        # User presses stop: signal via the broker, the watcher polls it.
        await request_cancel(redis_client, stream_id)
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=settings.background_runs_cancel_poll_seconds + 10)

        assert not await store.has_interrupt(conversation_id), (
            "user cancel must clear pending_hitl — an orphan key misroutes the "
            "next message into HITL resumption for a question the user killed"
        )
    finally:
        await store.delete_interrupt(conversation_id)
        await redis_client.delete(run_stream_key(stream_id))


async def test_hard_kill_preserves_pending_hitl(redis_client: Redis) -> None:
    """A hard kill (shutdown drain — no user cancel signal) must PRESERVE
    pending_hitl: the interrupt stays legitimately answerable after restart.
    """
    conversation_id = str(uuid.uuid4())
    stream_id = f"test_{uuid.uuid4().hex[:8]}"
    store = _store(redis_client)
    interrupt_saved = asyncio.Event()

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        yield ChatStreamChunk(type="token", content="thinking… ", metadata=None)
        await store.save_interrupt(conversation_id, _valid_interrupt_data(stream_id))
        interrupt_saved.set()
        await asyncio.sleep(3600)
        yield ChatStreamChunk(type="token", content="never reached", metadata=None)

    try:
        task = spawn_chat_run_producer(
            chat_stream=stream(),
            run_id=stream_id,
            stream_id=stream_id,
            user_id="u",
            session_id="s",
            conversation_id=conversation_id,
        )
        await asyncio.wait_for(interrupt_saved.wait(), timeout=10)

        # Hard kill: direct task cancellation, no cancel signal in Redis.
        task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=10)

        assert await store.has_interrupt(conversation_id), (
            "hard kill must preserve pending_hitl — the user may still answer "
            "the delivered question after a restart"
        )
    finally:
        await store.delete_interrupt(conversation_id)
        await redis_client.delete(run_stream_key(stream_id))


# ============================================================================
# T0.2 — detection cache invalidation
# ============================================================================


async def test_save_interrupt_invalidates_stale_negative_cache(redis_client: Redis) -> None:
    """A cached "no pending" answer must not survive a save_interrupt.

    Sequence: a chat request checks (nothing pending → negative cached), the
    run interrupts and saves, the user answers within the cache TTL — the
    detection MUST see the pending interrupt, or the reply starts a new turn
    instead of resuming.
    """
    conversation_id = str(uuid.uuid4())
    store = _store(redis_client)

    try:
        assert await hitl_pending.check_pending_hitl(conversation_id) is None

        await store.save_interrupt(conversation_id, _valid_interrupt_data("run_t02a"))

        detected = await hitl_pending.check_pending_hitl(conversation_id)
        assert detected is not None and detected.get("action_requests"), (
            "save_interrupt must invalidate the negative detection cache — a "
            "fast reply (one-click approval) would otherwise be routed as a "
            "NEW turn instead of a HITL resumption"
        )
    finally:
        await store.delete_interrupt(conversation_id)


async def test_clear_interrupt_invalidates_stale_positive_cache(redis_client: Redis) -> None:
    """A cached "pending" answer must not survive a clear_interrupt.

    Sequence: pending detected (positive cached), resumption completes and
    clears, the user sends the next message within the cache TTL — the
    detection MUST answer "nothing pending", or the message is misrouted
    into a phantom HITL resumption.
    """
    conversation_id = str(uuid.uuid4())
    store = _store(redis_client)

    try:
        await store.save_interrupt(conversation_id, _valid_interrupt_data("run_t02b"))
        detected = await hitl_pending.check_pending_hitl(conversation_id)
        assert detected is not None, "precondition: pending detected and cached"

        await store.clear_interrupt(conversation_id)

        assert await hitl_pending.check_pending_hitl(conversation_id) is None, (
            "clear_interrupt must invalidate the positive detection cache — "
            "the next message would otherwise be misrouted into a phantom "
            "HITL resumption"
        )
    finally:
        await store.delete_interrupt(conversation_id)
