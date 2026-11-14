"""Two voice requests share real durable admission and Redis supersession markers."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.conversation_execution import ExecutionPhase, RunAdmission, RunEnd
from src.core.run_authority import RunAuthority, current_run_authority
from src.domains.agents.api import internal_admission, stream_gates
from src.domains.agents.api.hitl_pending import pending_run_id
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.voice_sessions.session import VoiceSession
from src.infrastructure.async_utils import cancel_and_join
from src.infrastructure.scheduler import voice_delegation as bridge
from src.infrastructure.scheduler.out_of_turn_run import RunContext
from src.infrastructure.scheduler.voice_delegation import (
    DelegationOutcome,
    DelegationRequest,
    delegate,
)
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.conversation_executions import reserved as reserved

pytestmark = pytest.mark.integration


async def test_two_requests_join_the_old_writer_before_the_newest_runs(
    redis_client: Redis,
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No elapsed lease, fake database admission, or skipped service can prove this race."""
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    session = VoiceSession.phone(
        call_id=uuid4(),
        mode="delegated",
        user_id=reserved.target.owner_id,
        conversation_id=reserved.target.owner_id,
        language="en",
        timezone="UTC",
    )
    context = RunContext(
        user=object(), language="en", timezone="UTC", display_name="Test", display_mode="cards"
    )
    started = asyncio.Event()
    closing = asyncio.Event()
    joined = asyncio.Event()
    admissions: list[RunAdmission] = []

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def allowed(owner: object) -> None:
        return None

    async def body(
        _self: AgentService, prompt: str, *args: object, **kwargs: object
    ) -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        assert authority is not None
        admissions.append(authority.admission)
        if prompt == "first":
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                closing.set()
                await joined.wait()
        else:
            assert joined.is_set(), "A replacement entered while the prior writer was alive"
            yield ChatStreamChunk(type="token", content="done second")
            yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(internal_admission, "get_db_context", database)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    monkeypatch.setattr(stream_gates, "usage_limit_error_chunk", allowed)
    monkeypatch.setattr(stream_gates, "capture_location_fire_and_forget", lambda *_: None)
    monkeypatch.setattr(bridge, "SUPERSEDE_POLL_SECONDS", 0.02)
    monkeypatch.setattr(settings, "voice_delegation_lease_wait_seconds", 5)
    request = DelegationRequest(
        session=session,
        request_id="first",
        request="first",
        spoken_text=None,
        wait_seconds=10,
    )
    first = asyncio.create_task(delegate(request, context=context))
    second: asyncio.Task[bridge.DelegationResult] | None = None
    try:
        await asyncio.wait_for(started.wait(), 5)
        second = asyncio.create_task(
            delegate(replace(request, request_id="second", request="second"), context=context)
        )
        await asyncio.wait_for(closing.wait(), 5)
        async with AsyncSession(async_engine) as db:
            busy = await ConversationExecutionRepository(db).snapshot_for_owner(session.user_id)
            assert busy is not None and busy.stream_id == admissions[0].stream_id
        assert len(admissions) == 1
        joined.set()
        first_result, second_result = await asyncio.wait_for(asyncio.gather(first, second), 10)
        assert first_result.outcome is DelegationOutcome.SUPERSEDED
        assert second_result.outcome is DelegationOutcome.ANSWERED
        assert second_result.text == "done second"
        assert len(admissions) == 2 and admissions[0].activity_id != admissions[1].activity_id
        assert admissions[0].target == admissions[1].target
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(session.user_id) is None
            )
            phases = list(
                await db.scalars(
                    select(ConversationExecution.phase).where(
                        ConversationExecution.user_id == session.user_id,
                    )
                )
            )
            assert len(phases) == 3 and all(phase is ExecutionPhase.CLOSED for phase in phases)
    finally:
        joined.set()
        await cancel_and_join(first)
        if second is not None:
            await cancel_and_join(second)
        await redis_client.delete(bridge.newest_request_key(session.key))


async def test_replacement_during_real_admission_closes_without_starting_a_graph(
    redis_client: Redis,
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The marker changes after SQL admission commits, before the graph can spend."""
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    session = VoiceSession.phone(
        call_id=uuid4(),
        mode="delegated",
        user_id=reserved.target.owner_id,
        conversation_id=reserved.target.id,
        language="en",
        timezone="UTC",
    )
    started: list[str] = []
    authorities: list[RunAuthority] = []

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def replace_after_admission(runtime_id: str) -> str | None:
        authority = current_run_authority()
        assert authority is not None
        authorities.append(authority)
        async with AsyncSession(async_engine) as db:
            occupied = await ConversationExecutionRepository(db).active_for_owner(session.user_id)
            assert occupied is not None
            assert occupied.phase is ExecutionPhase.RUNNING
        await redis_client.set(bridge.newest_request_key(session.key), "replacement")
        return await pending_run_id(runtime_id)

    async def body(
        _self: AgentService, prompt: str, *args: object, **kwargs: object
    ) -> AsyncGenerator[ChatStreamChunk]:
        started.append(prompt)
        yield ChatStreamChunk(type="token", content="unwanted answer")
        yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(internal_admission, "get_db_context", database)
    monkeypatch.setattr(internal_admission, "pending_run_id", replace_after_admission)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    request = DelegationRequest(
        session=session,
        request_id="original",
        request="original",
        spoken_text=None,
        wait_seconds=10,
    )
    context = RunContext(
        user=object(), language="en", timezone="UTC", display_name="Test", display_mode="cards"
    )
    try:
        result = await delegate(request, context=context)
        assert result.outcome is DelegationOutcome.SUPERSEDED
        assert started == []
        assert len(authorities) == 1
        assert authorities[0].revoked
        assert not authorities[0].external_work_started
        async with AsyncSession(async_engine) as db:
            executions = list(
                await db.scalars(
                    select(ConversationExecution).where(
                        ConversationExecution.user_id == session.user_id
                    )
                )
            )
            assert len(executions) == 2
            assert all(execution.phase is ExecutionPhase.CLOSED for execution in executions)
    finally:
        await redis_client.delete(bridge.newest_request_key(session.key))


@pytest.mark.parametrize("error_type", [ConnectionError, TimeoutError])
async def test_failed_supervision_keeps_sql_occupied_until_the_graph_has_joined(
    redis_client: Redis,
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    """An unavailable marker cannot release admission beside a living writer."""
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    started = asyncio.Event()
    closing = asyncio.Event()
    joined = asyncio.Event()
    original_get = redis_client.get

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def redis() -> Redis:
        return redis_client

    async def read_marker(key: str) -> object:
        if started.is_set():
            raise error_type("Marker polling unavailable")
        return await original_get(key)

    async def allowed(owner: object) -> None:
        return None

    async def body(
        _self: AgentService, prompt: str, *args: object, **kwargs: object
    ) -> AsyncGenerator[ChatStreamChunk]:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closing.set()
            await joined.wait()
        yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(internal_admission, "get_db_context", database)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    monkeypatch.setattr(stream_gates, "usage_limit_error_chunk", allowed)
    monkeypatch.setattr(stream_gates, "capture_location_fire_and_forget", lambda *_: None)
    monkeypatch.setattr(bridge, "get_redis_cache", redis)
    monkeypatch.setattr(redis_client, "get", read_marker)
    monkeypatch.setattr(bridge, "SUPERSEDE_POLL_SECONDS", 0.01)
    session = VoiceSession.phone(
        call_id=uuid4(),
        mode="delegated",
        user_id=reserved.target.owner_id,
        conversation_id=reserved.target.id,
        language="en",
        timezone="UTC",
    )
    request = DelegationRequest(
        session=session, request_id="original", request="first", spoken_text=None, wait_seconds=10
    )
    context = RunContext(
        user=object(), language="en", timezone="UTC", display_name="Test", display_mode="cards"
    )
    caller = asyncio.create_task(delegate(request, context=context))
    try:
        await asyncio.wait_for(closing.wait(), 5)
        assert not caller.done()
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(session.user_id)
                is not None
            )
        joined.set()
        result = await asyncio.wait_for(caller, 5)
        assert result.outcome is DelegationOutcome.FAILED
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(session.user_id) is None
            )
            phases = list(
                await db.scalars(
                    select(ConversationExecution.phase).where(
                        ConversationExecution.user_id == session.user_id
                    )
                )
            )
            assert len(phases) == 2 and all(phase is ExecutionPhase.CLOSED for phase in phases)
    finally:
        joined.set()
        await cancel_and_join(caller)
        await redis_client.delete(bridge.newest_request_key(session.key))
