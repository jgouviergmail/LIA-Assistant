"""One admitted request survives preparation retries and concurrent archive attempts."""

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.core.run_authority import RunAuthority, current_run_authority, run_authority_scope
from src.domains.agents.api.archive_first import archive_user_message_first
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.service import ConversationService
from src.infrastructure.database import session
from src.infrastructure.scheduler import out_of_turn_run as engine
from tests.integration.domains.conversations.test_internal_run_admission import calls as calls
from tests.integration.domains.conversations.test_internal_run_admission import close, request_for

pytestmark = pytest.mark.integration


async def _archive(admission: RunAdmission, content: str = "A retryable request") -> UUID | None:
    return await archive_user_message_first(
        conv_service=ConversationService(),
        conversation_id=admission.target.id,
        user_message=content,
        run_id=admission.run_id,
        is_hitl_resumption=False,
        attachment_meta={},
        stt_kwargs={},
    )


@pytest.mark.parametrize("before_archive", [False, True])
async def test_a_preparation_retry_archives_the_request_exactly_once(
    reserved: RunAdmission,
    calls: list[RunAdmission],
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    before_archive: bool,
) -> None:
    await close(reserved, async_engine)
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    attempts = 0

    async def body(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        nonlocal attempts
        attempts += 1
        if before_archive and attempts == 1:
            raise ConnectionError("Preparation has not archived anything yet")
        authority = current_run_authority()
        assert authority is not None
        if kwargs["archive_user_message"]:
            assert await _archive(authority.admission) is not None
        if attempts == 1:
            raise ConnectionError("Preparation stopped after archive commit")
        yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    monkeypatch.setattr(engine, "_run_acted", AsyncMock(return_value=False))
    result = await engine.stream_instruction(request_for(reserved))
    assert result.outcome is engine.RunOutcome.SUCCESS and result.attempts == 2
    assert result.admission is not None
    async with AsyncSession(async_engine) as db:
        rows = list(
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == result.admission.target.id,
                    ConversationMessage.role == "user",
                )
            )
        )
        assert len(rows) == 1


async def test_two_archive_attempts_for_one_invocation_return_the_same_request(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    with run_authority_scope(RunAuthority(reserved)):
        first, second = await asyncio.gather(_archive(reserved), _archive(reserved))
    assert first is not None and second == first
    async with AsyncSession(async_engine) as db:
        rows = list(
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == reserved.target.id,
                )
            )
        )
        assert [row.id for row in rows] == [first]


async def test_a_new_hitl_invocation_keeps_its_own_request_under_the_same_billing_run(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    with run_authority_scope(RunAuthority(reserved)):
        first = await _archive(reserved)
    await close(reserved, async_engine)
    async with AsyncSession(async_engine) as db:
        resumed = await ConversationExecutionRepository(db).admit(
            reserved.target,
            run_id=reserved.run_id,
            stream_id=str(uuid4()),
            worker_id=uuid4(),
        )
        assert isinstance(resumed, RunAdmission)
        await db.commit()
    try:
        with run_authority_scope(RunAuthority(resumed)):
            second = await _archive(resumed)
        assert first is not None and second is not None and first != second
    finally:
        await close(resumed, async_engine)


@pytest.mark.parametrize("closed", [False, True])
async def test_an_archive_replay_cannot_change_input_or_reuse_closed_authority(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    closed: bool,
) -> None:
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    with run_authority_scope(RunAuthority(reserved)):
        first = await _archive(reserved)
        if closed:
            await close(reserved, async_engine)
        with pytest.raises(ExecutionRevoked):
            await _archive(reserved, "A retryable request" if closed else "Different input")
    async with AsyncSession(async_engine) as db:
        rows = list(
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == reserved.target.id
                )
            )
        )
        assert [row.id for row in rows] == [first]
