"""The actual public AgentService owns admission before entering its graph implementation."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import (
    ConversationBusy,
    ExecutionPhase,
    ExecutionRevoked,
    RunAdmission,
    RunEnd,
)
from src.core.conversation_target import ConversationKind
from src.core.run_authority import current_run_authority
from src.domains.agents.api import stream_gates
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.infrastructure.streaming import run_admission

pytestmark = pytest.mark.integration


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> AgentService:
    """Substitute the model body and unrelated quota precheck, never target/admission SQL."""

    async def allowed(owner: object) -> None:
        return None

    async def body(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        assert authority is not None, "A model body started without admission"
        assert kwargs["target"] == authority.admission.target
        assert kwargs["run_id"] == authority.admission.run_id
        yield ChatStreamChunk(type="done", content="", metadata=None)

    monkeypatch.setattr(stream_gates, "usage_limit_error_chunk", allowed)
    monkeypatch.setattr(stream_gates, "capture_location_fire_and_forget", lambda *_: None)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    return AgentService()


async def consume(
    service: AgentService, admission: RunAdmission, *, supplied: bool
) -> list[ChatStreamChunk]:
    chunks = []
    async for chunk in service.stream_chat_response(
        "A question",
        admission.target.owner_id,
        "test-session",
        target=admission.target,
        admission=admission if supplied else None,
    ):
        chunks.append(chunk)
    return chunks


async def test_supplied_admission_reaches_the_body_and_closes_when_joined(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    service: AgentService,
) -> None:
    chunks = await consume(service, reserved, supplied=True)
    assert chunks[-1].metadata == {
        "conversation_id": str(reserved.target.id),
        "conversation_revision": reserved.target.revision,
        "conversation_kind": reserved.target.kind.value,
        "run_id": reserved.run_id,
        "stream_id": reserved.stream_id,
    }
    async with AsyncSession(async_engine) as db:
        assert (
            await db.scalar(
                select(ConversationExecution.phase).where(
                    ConversationExecution.id == reserved.activity_id,
                )
            )
            == ExecutionPhase.CLOSED
        )


async def test_a_direct_internal_caller_cannot_bypass_account_occupancy(
    reserved: RunAdmission,
    service: AgentService,
) -> None:
    with pytest.raises(ConversationBusy) as error:
        await consume(service, reserved, supplied=False)
    assert error.value.busy.target == reserved.target


async def test_a_direct_internal_caller_gets_one_admission(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    service: AgentService,
) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    await consume(service, reserved, supplied=False)
    async with AsyncSession(async_engine) as db:
        rows = list(
            (
                await db.scalars(
                    select(ConversationExecution).where(
                        ConversationExecution.user_id == reserved.target.owner_id,
                    )
                )
            ).all()
        )
        assert len(rows) == 2 and all(row.phase == ExecutionPhase.CLOSED for row in rows)


async def test_borrowed_authority_stays_owned_by_the_producer(
    reserved: RunAdmission,
    service: AgentService,
) -> None:
    async with run_admission.owned_execution(reserved) as authority:
        await consume(service, reserved, supplied=True)
        assert current_run_authority() is authority and not authority.revoked


async def test_owner_and_target_cannot_be_mixed_with_an_admission(
    reserved: RunAdmission,
    service: AgentService,
) -> None:
    for owner, target in (
        (uuid4(), reserved.target),
        (reserved.target.owner_id, replace(reserved.target, runtime_id=uuid4())),
    ):
        with pytest.raises(ExecutionRevoked):
            async for _ in service.stream_chat_response(
                "A question",
                owner,
                "test-session",
                target=target,
                admission=reserved,
            ):
                pass


@pytest.mark.parametrize("language,fragment", [("de", "Unterhaltung"), ("zh-CN", "对话")])
async def test_legacy_first_use_creates_and_admits_main_in_the_declared_language(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    service: AgentService,
    language: str,
    fragment: str,
) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    async for _ in service.stream_chat_response(
        "First question",
        reserved.target.owner_id,
        "session",
        user_language=language,
    ):
        pass
    async with AsyncSession(async_engine) as db:
        main = await db.scalar(
            select(Conversation).where(
                Conversation.user_id == reserved.target.owner_id,
                Conversation.kind == ConversationKind.MAIN,
            )
        )
        assert main is not None and main.title is not None and fragment in main.title
        activity = await db.scalar(
            select(ConversationExecution).where(
                ConversationExecution.conversation_id == main.id,
            )
        )
        assert activity is not None and activity.phase == ExecutionPhase.CLOSED


async def test_two_first_messages_create_one_main_and_admit_only_one_graph(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    service: AgentService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release = asyncio.Event(), asyncio.Event()
    async with AsyncSession(async_engine) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()

    async def hold_body(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        assert current_run_authority() is not None
        started.set()
        await release.wait()
        yield ChatStreamChunk(type="done", content="", metadata=None)

    monkeypatch.setattr(AgentService, "_stream_with_new_services", hold_body)

    async def ask() -> None:
        async for _ in service.stream_chat_response("First", reserved.target.owner_id, "session"):
            pass

    first = asyncio.create_task(ask())
    try:
        await started.wait()
        with pytest.raises(ConversationBusy):
            await ask()
    finally:
        release.set()
        await first
    async with AsyncSession(async_engine) as db:
        mains = list(
            (
                await db.scalars(
                    select(Conversation).where(
                        Conversation.user_id == reserved.target.owner_id,
                        Conversation.kind == ConversationKind.MAIN,
                    )
                )
            ).all()
        )
        assert len(mains) == 1
        activities = list(
            (
                await db.scalars(
                    select(ConversationExecution).where(
                        ConversationExecution.conversation_id == mains[0].id,
                    )
                )
            ).all()
        )
        assert len(activities) == 1 and activities[0].phase == ExecutionPhase.CLOSED
