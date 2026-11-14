"""Cancellation and detection-cache behavior under real runtime authority and Redis."""

import asyncio
from collections.abc import AsyncGenerator, Iterator
from contextlib import suppress

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.core.conversation_execution import RunAdmission
from src.domains.agents.api import hitl_pending
from src.domains.agents.api.background_runner import spawn_chat_run_producer
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.utils import hitl_cache
from src.domains.agents.utils.hitl_store import HITLStore
from src.infrastructure.streaming.run_admission import owned_execution
from src.infrastructure.streaming.run_stream_broker import request_cancel
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.conversation_executions import reserved as reserved

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def reset_detection_cache() -> Iterator[None]:
    hitl_cache._cache.clear()
    yield
    hitl_cache._cache.clear()


def interrupt_data(admission: RunAdmission) -> dict[str, object]:
    """A valid question carries its admitted billing identity."""
    return {
        "action_requests": [{"type": "tool_confirmation", "tool_name": "send_email_tool"}],
        "run_id": admission.run_id,
    }


@pytest.mark.parametrize("user_cancel", [True, False])
async def test_user_cancel_clears_the_question_but_shutdown_preserves_it(
    reserved: RunAdmission,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
    user_cancel: bool,
) -> None:
    monkeypatch.setattr(settings, "background_runs_cancel_poll_seconds", 0.01)
    store = HITLStore(redis_client, settings.hitl_pending_data_ttl_seconds)
    runtime_id = str(reserved.target.runtime_id)
    saved = asyncio.Event()

    async def stream() -> AsyncGenerator[ChatStreamChunk]:
        await store.save_interrupt(runtime_id, interrupt_data(reserved))
        saved.set()
        await asyncio.Event().wait()
        yield ChatStreamChunk(type="done", content="", metadata=None)

    task = spawn_chat_run_producer(chat_stream=stream(), admission=reserved, session_id="test")
    try:
        await asyncio.wait_for(saved.wait(), 5)
        assert await store.has_interrupt(runtime_id)
        if user_cancel:
            await request_cancel(redis_client, reserved.stream_id)
        else:
            task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert await store.has_interrupt(runtime_id) is not user_cancel
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def test_save_interrupt_invalidates_stale_negative_cache(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    runtime_id = str(reserved.target.runtime_id)
    store = HITLStore(redis_client, settings.hitl_pending_data_ttl_seconds)
    async with owned_execution(reserved):
        assert await hitl_pending.check_pending_hitl(runtime_id) is None
        await store.save_interrupt(runtime_id, interrupt_data(reserved))
        detected = await hitl_pending.check_pending_hitl(runtime_id)
        assert detected is not None and detected["action_requests"]


async def test_clear_interrupt_invalidates_stale_positive_cache(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    runtime_id = str(reserved.target.runtime_id)
    store = HITLStore(redis_client, settings.hitl_pending_data_ttl_seconds)
    async with owned_execution(reserved):
        await store.save_interrupt(runtime_id, interrupt_data(reserved))
        assert await hitl_pending.check_pending_hitl(runtime_id) is not None
        await store.clear_interrupt(runtime_id)
        assert await hitl_pending.check_pending_hitl(runtime_id) is None
