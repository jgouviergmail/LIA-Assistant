"""A waiting message leaves as the person's turn when the account is released (ADR-384).

Real PostgreSQL, Redis, admission, producer, service and archive; only the graph
body and the quota pre-check are substituted.
"""

import asyncio
from collections.abc import AsyncGenerator
from uuid import UUID

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.conversation_execution import ExecutionPhase, RunAdmission, RunEnd
from src.core.run_authority import current_run_authority
from src.domains.agents.api import stream_gates, waiting_departure
from src.domains.agents.api.archive_first import archive_user_message_first
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.agents.utils.hitl_store import HITLStore
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.service import ConversationService
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from src.infrastructure.database import session
from src.infrastructure.streaming import run_admission

pytestmark = pytest.mark.integration


@pytest.fixture
def graph(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Every session on the test database; a graph body that archives, then answers."""
    monkeypatch.setattr(
        session, "AsyncSessionLocal", async_sessionmaker(async_engine, expire_on_commit=False)
    )
    behaviour = {"fail_before_archive": False}

    async def allowed(owner: object) -> None:
        return None

    async def body(
        _service: object, user_message: str, *args: object, **kwargs: object
    ) -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        assert authority is not None
        if behaviour["fail_before_archive"]:
            raise ConnectionError("the graph failed before the archive")
        await archive_user_message_first(
            conv_service=ConversationService(),
            conversation_id=authority.admission.target.id,
            user_message=user_message,
            run_id=authority.admission.run_id,
            is_hitl_resumption=False,
            attachment_meta={},
            stt_kwargs={},
        )
        yield ChatStreamChunk(type="token", content="Noted.")
        yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(stream_gates, "usage_limit_error_chunk", allowed)
    monkeypatch.setattr(stream_gates, "capture_location_fire_and_forget", lambda *_: None)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    return behaviour


async def keep(engine: AsyncEngine, admission: RunAdmission, text: str) -> WaitingMessage:
    async with AsyncSession(engine, expire_on_commit=False) as db:
        row, _ = await WaitingMessageRepository(db).keep(
            admission.target, text, rendering={"viewport_width": 390}, status=WaitingStatus.WAITING
        )
        await db.commit()
        return row


async def release(admission: RunAdmission, end: RunEnd) -> None:
    async with run_admission.owned_execution(admission) as authority:
        authority.end = end


async def archived(engine: AsyncEngine, conversation_id: UUID) -> list[str]:
    async with AsyncSession(engine) as db:
        return list(
            await db.scalars(
                select(ConversationMessage.content)
                .where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.role == "user",
                )
                .order_by(ConversationMessage.created_at)
            )
        )


async def waiting(engine: AsyncEngine, row_id: UUID) -> WaitingMessage | None:
    async with AsyncSession(engine) as db:
        return await db.get(WaitingMessage, row_id)


async def executions(engine: AsyncEngine, owner_id: UUID) -> list[ConversationExecution]:
    async with AsyncSession(engine) as db:
        return list(
            await db.scalars(
                select(ConversationExecution)
                .where(ConversationExecution.user_id == owner_id)
                .order_by(ConversationExecution.fence)
            )
        )


async def settled(engine: AsyncEngine, owner_id: UUID, count: int) -> list[ConversationExecution]:
    """Wait until ``count`` executions exist and all are closed."""
    async with asyncio.timeout(15):
        while True:
            rows = await executions(engine, owner_id)
            if len(rows) >= count and all(row.phase == ExecutionPhase.CLOSED for row in rows):
                return rows
            await asyncio.sleep(0.05)


async def test_after_a_normal_end_the_waiting_message_leaves_as_the_persons_turn(
    reserved: RunAdmission, async_engine: AsyncEngine, graph: dict[str, bool]
) -> None:
    owner = reserved.target.owner_id
    row = await keep(async_engine, reserved, "And add the bakery")
    await release(reserved, RunEnd.NORMAL)
    first, departed = await settled(async_engine, owner, 2)
    assert first.stream_id == reserved.stream_id and first.end_state == RunEnd.NORMAL
    assert departed.conversation_id == reserved.target.id
    assert departed.relayed and departed.cancellable
    assert departed.end_state == RunEnd.NORMAL
    assert await archived(async_engine, reserved.target.id) == ["And add the bakery"]
    assert await waiting(async_engine, row.id) is None


async def test_after_an_interrupted_end_the_message_is_held_and_nothing_leaves(
    reserved: RunAdmission, async_engine: AsyncEngine, graph: dict[str, bool]
) -> None:
    owner = reserved.target.owner_id
    row = await keep(async_engine, reserved, "And add the bakery")
    await release(reserved, RunEnd.INTERRUPTED)
    await waiting_departure.depart_after_release(owner, RunEnd.INTERRUPTED)
    assert len(await settled(async_engine, owner, 1)) == 1
    held = await waiting(async_engine, row.id)
    assert held is not None and held.status == WaitingStatus.HELD
    assert await archived(async_engine, reserved.target.id) == []


async def test_a_message_the_person_asked_to_send_leaves_whatever_the_end(
    reserved: RunAdmission, async_engine: AsyncEngine, graph: dict[str, bool]
) -> None:
    owner = reserved.target.owner_id
    row = await keep(async_engine, reserved, "Send it anyway")
    async with AsyncSession(async_engine) as db:
        assert await WaitingMessageRepository(db).request_send(owner, reserved.target.id)
        await db.commit()
    await release(reserved, RunEnd.INTERRUPTED)
    await settled(async_engine, owner, 2)
    assert await archived(async_engine, reserved.target.id) == ["Send it anyway"]
    assert await waiting(async_engine, row.id) is None


async def test_a_pending_question_keeps_the_message_waiting(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    graph: dict[str, bool],
    redis_client: Redis,
) -> None:
    owner = reserved.target.owner_id
    row = await keep(async_engine, reserved, "Written before the question")
    async with run_admission.owned_execution(reserved) as authority:
        await HITLStore(redis_client, settings.hitl_pending_data_ttl_seconds).save_interrupt(
            str(reserved.target.runtime_id),
            {"run_id": reserved.run_id, "action_requests": [{"type": "clarification"}]},
        )
        authority.end = RunEnd.NORMAL
    await waiting_departure.depart_after_release(owner, RunEnd.NORMAL)
    assert len(await settled(async_engine, owner, 1)) == 1
    still = await waiting(async_engine, row.id)
    assert still is not None and still.status == WaitingStatus.WAITING
    assert await archived(async_engine, reserved.target.id) == []


async def test_a_departure_that_fails_before_its_archive_is_held_not_resent(
    reserved: RunAdmission, async_engine: AsyncEngine, graph: dict[str, bool]
) -> None:
    owner = reserved.target.owner_id
    graph["fail_before_archive"] = True
    row = await keep(async_engine, reserved, "Never archived")
    await release(reserved, RunEnd.NORMAL)
    first, departed = await settled(async_engine, owner, 2)
    assert departed.end_state == RunEnd.INTERRUPTED
    held = await waiting(async_engine, row.id)
    assert held is not None and held.status == WaitingStatus.HELD and held.stream_id is None
    assert await archived(async_engine, reserved.target.id) == []
    await waiting_departure.depart_after_release(owner, RunEnd.NORMAL)
    assert len(await executions(async_engine, owner)) == 2
