"""Internal turns share durable admission, strict questions and non-replayable spend."""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionPhase, RunAdmission, RunEnd
from src.core.run_authority import current_run_authority
from src.domains.agents.api import internal_admission, stream_gates
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.agents.utils import HITLStore
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.infrastructure.proactive.discussion_attention import attention_hold
from src.infrastructure.scheduler import out_of_turn_run as engine
from src.infrastructure.streaming import run_admission

pytestmark = pytest.mark.integration


def request_for(admission: RunAdmission) -> engine.StreamRequest:
    """An ordinary internal request resolves Main, even if an annex exists."""
    return engine.StreamRequest(
        user_id=admission.target.owner_id,
        prompt="A controlled integration turn",
        session_id="internal-admission-contract",
        language="en",
        timezone="UTC",
        display_name="Test",
        display_mode="cards",
        timeout_seconds=20,
        max_attempts=2,
        retry_delay_seconds=0,
        run_id=str(uuid4()),
    )


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, async_engine: AsyncEngine) -> list[RunAdmission]:
    """Substitute the provider body and SQL composition, never admission or Redis."""
    seen: list[RunAdmission] = []

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def allowed(owner: object) -> None:
        return None

    async def body(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        assert authority is not None
        assert kwargs["target"] == authority.admission.target
        assert kwargs["run_id"] == authority.admission.run_id
        seen.append(authority.admission)
        yield ChatStreamChunk(type="token", content="A completed answer")
        yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(internal_admission, "get_db_context", session)
    monkeypatch.setattr(stream_gates, "usage_limit_error_chunk", allowed)
    monkeypatch.setattr(stream_gates, "capture_location_fire_and_forget", lambda *_: None)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    return seen


async def close(admission: RunAdmission, db_engine: AsyncEngine) -> None:
    """Close only the fixture's unused reservation."""
    async with AsyncSession(db_engine) as db:
        await ConversationExecutionRepository(db).close_owned(admission, end=RunEnd.NORMAL)
        await db.commit()


async def test_proactive_attention_holds_for_an_annex_even_without_main(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as db:
        assert (
            await attention_hold(db, reserved.target.owner_id, now=datetime.now(UTC))
            == "turn_streaming"
        )


async def test_an_annex_occupies_internal_main_without_spending_an_attempt(
    reserved: RunAdmission, calls: list[RunAdmission]
) -> None:
    announced: list[bool] = []

    async def announce() -> None:
        announced.append(True)

    result = await engine.stream_instruction(request_for(reserved), before_run=announce)
    assert result.outcome.value == "busy"
    assert result.attempts == 0
    assert calls == []
    assert announced == []


async def test_unknown_paid_outcome_is_not_replayed_as_another_turn(
    reserved: RunAdmission,
    calls: list[RunAdmission],
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await close(reserved, async_engine)
    attempted: list[RunAdmission] = []

    async def lost_answer(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        await run_admission.authorize_external_work()
        authority = current_run_authority()
        assert authority is not None
        attempted.append(authority.admission)
        raise ConnectionError("Provider accepted the request, response lost")
        yield ChatStreamChunk(type="done", content="")  # pragma: no cover

    monkeypatch.setattr(AgentService, "_stream_with_new_services", lost_answer)
    result = await engine.stream_instruction(request_for(reserved))
    assert result.outcome is engine.RunOutcome.FAILED
    assert result.attempts == 1
    assert len(attempted) == 1
    async with AsyncSession(async_engine) as db:
        phases = list(
            await db.scalars(
                select(ConversationExecution.phase).where(
                    ConversationExecution.user_id == reserved.target.owner_id
                )
            )
        )
    assert phases == [ExecutionPhase.CLOSED, ExecutionPhase.CLOSED]


async def test_failure_before_external_work_retries_under_one_admission(
    reserved: RunAdmission,
    calls: list[RunAdmission],
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await close(reserved, async_engine)
    attempted: list[RunAdmission] = []

    async def transient(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        assert authority is not None
        attempted.append(authority.admission)
        if len(attempted) == 1:
            raise ConnectionError("Before any provider call")
        yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(AgentService, "_stream_with_new_services", transient)
    result = await engine.stream_instruction(replace(request_for(reserved), run_id=None))
    assert result.outcome is engine.RunOutcome.SUCCESS
    assert result.attempts == 2
    assert len(attempted) == 2 and attempted[0] == attempted[1]


@pytest.mark.parametrize("started", [False, True])
async def test_only_a_quota_refusal_before_work_may_requeue_the_whole_instruction(
    reserved: RunAdmission,
    calls: list[RunAdmission],
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    started: bool,
) -> None:
    await close(reserved, async_engine)

    async def blocked(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        if started:
            await run_admission.authorize_external_work()
        yield ChatStreamChunk(
            type="error", content="Limit reached", metadata={"error_code": "usage_limit_exceeded"}
        )

    monkeypatch.setattr(AgentService, "_stream_with_new_services", blocked)
    result = await engine.stream_instruction(request_for(reserved))
    assert result.outcome is (
        engine.RunOutcome.FAILED if started else engine.RunOutcome.QUOTA_BLOCKED
    )
    assert result.error_code == "usage_limit_exceeded"
    assert result.attempts == 1


@pytest.mark.parametrize("answering", [False, True])
async def test_pending_question_is_checked_on_the_rotated_runtime_after_admission(
    reserved: RunAdmission,
    calls: list[RunAdmission],
    async_engine: AsyncEngine,
    answering: bool,
) -> None:
    await close(reserved, async_engine)
    first = await engine.stream_instruction(request_for(reserved))
    assert first.outcome is engine.RunOutcome.SUCCESS
    target = calls[-1].target
    target = replace(target, runtime_id=uuid4(), revision=target.revision + 1)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == target.id)
            .values(
                runtime_id=target.runtime_id,
                revision=target.revision,
            )
        )
        await db.commit()
    calls.clear()
    async with run_admission.execution_for_turn(
        target.owner_id, target=target, admission=None, run_id=str(uuid4()), language="en"
    ) as authority:
        redis = await run_admission.get_redis_cache()
        store = HITLStore(redis_client=redis, ttl_seconds=120)
        await store.save_interrupt(
            str(target.runtime_id),
            {"run_id": authority.admission.run_id, "action_requests": [{"type": "clarification"}]},
        )
    try:
        result = await engine.stream_instruction(
            replace(request_for(reserved), resume_pending=answering)
        )
        if answering:
            assert result.outcome is engine.RunOutcome.SUCCESS and result.attempts == 1
            assert len(calls) == 1 and calls[0].target == target
            assert calls[0].run_id == authority.admission.run_id
            assert calls[0].activity_id != authority.admission.activity_id
            assert result.admission == calls[0]
        else:
            assert result.outcome.value == "pending_question"
            assert result.attempts == 0 and calls == []
        assert await store.get_pending(str(target.runtime_id)) is not None
    finally:
        await store.clear_interrupt_for_run(
            str(target.runtime_id),
            authority.admission.run_id,
            activity_id=authority.admission.activity_id,
        )
