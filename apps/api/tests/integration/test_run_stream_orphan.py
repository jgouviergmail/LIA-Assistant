"""SQL liveness survives missing Redis leases; transport loss never transfers admission."""

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.conversation_execution import ExecutionPhase, RunAdmission, RunEnd
from src.domains.agents.api.stream_relay import stream_run_as_sse, transport_state
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.database import session
from src.infrastructure.streaming.run_stream_broker import has_listeners, publish_chunk, publish_end
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.conversation_executions import reserved as reserved

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def real_sql_and_short_windows(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only timings and the SQL connection factory differ from the production subscriber."""
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    monkeypatch.setattr(settings, "background_runs_orphan_grace_seconds", 0.05)
    monkeypatch.setattr(settings, "background_runs_xread_block_ms", 100)


def relay(admission: RunAdmission) -> AsyncGenerator[str]:
    return stream_run_as_sse(
        admission.stream_id, target=admission.target, run_id=admission.run_id, user_language="en"
    )


async def test_missing_redis_lease_does_not_end_a_silent_supervised_run(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    assert await transport_state(reserved.target, reserved.stream_id) == "running"
    async with asyncio.timeout(3):
        heartbeats = 0
        async for frame in relay(reserved):
            assert not frame.startswith("data:")
            heartbeats += frame == ": heartbeat\n\n"
            if heartbeats == 3:
                await publish_end(redis_client, reserved.stream_id, "completed")
    assert heartbeats == 3
    assert not await has_listeners(redis_client, reserved.stream_id)


async def test_stale_heartbeat_closes_transport_but_keeps_sql_occupied(
    reserved: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(ConversationExecution)
            .where(ConversationExecution.id == reserved.activity_id)
            .values(
                heartbeat_at=datetime.now(UTC)
                - timedelta(seconds=settings.background_runs_active_ttl_seconds + 1),
            )
        )
        await db.commit()
    await publish_chunk(
        redis_client,
        reserved.stream_id,
        json.dumps({"type": "token", "content": "partial", "metadata": None}),
    )
    async with asyncio.timeout(3):
        frames = [frame async for frame in relay(reserved)]
    chunks = [json.loads(frame[6:]) for frame in frames if frame.startswith("data:")]
    assert [chunk["type"] for chunk in chunks] == ["token", "error", "done"]
    assert chunks[-1]["metadata"]["conversation_id"] == str(reserved.target.id)
    assert chunks[-1]["metadata"]["orphaned"] is True
    async with AsyncSession(async_engine) as db:
        busy = await ConversationExecutionRepository(db).active_for_owner(reserved.target.owner_id)
        assert busy is not None and busy.phase == ExecutionPhase.RUNNING
    assert not await has_listeners(redis_client, reserved.stream_id)


async def test_lost_end_marker_after_delivered_done_needs_no_invented_error(
    reserved: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
) -> None:
    await publish_chunk(
        redis_client,
        reserved.stream_id,
        json.dumps({"type": "done", "content": "", "metadata": None}),
    )
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    async with asyncio.timeout(3):
        frames = [frame async for frame in relay(reserved)]
    chunks = [json.loads(frame[6:]) for frame in frames if frame.startswith("data:")]
    assert [chunk["type"] for chunk in chunks] == ["done"]


async def test_a_foreign_generation_is_never_read_as_a_live_target(reserved: RunAdmission) -> None:
    wrong = replace(reserved.target, revision=reserved.target.revision + 1)
    assert await transport_state(wrong, reserved.stream_id) == "unknown"


async def test_sql_probe_failure_is_unknown_and_does_not_release_any_claim(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(
        self: ConversationExecutionRepository, *_args: object, **_kwargs: object
    ) -> None:
        raise ConnectionError("Test SQL read unavailable")

    with monkeypatch.context() as scoped:
        scoped.setattr(ConversationExecutionRepository, "snapshot_for_owner", unavailable)
        assert await transport_state(reserved.target, reserved.stream_id) == "unknown"
    async with AsyncSession(async_engine) as db:
        assert (
            await ConversationExecutionRepository(db).active_for_owner(reserved.target.owner_id)
            is not None
        )
