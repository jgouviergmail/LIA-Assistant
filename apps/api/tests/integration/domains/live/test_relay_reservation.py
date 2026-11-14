"""An actual deferred task owns its discussion and Redis record until its final publication."""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionKind, ExecutionPhase, RunAdmission
from src.core.exceptions import ResourceConflictError
from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_LIVE_SUMMARY,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)
from src.domains.chat.repository import ChatRepository
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.reservation_models import ConversationReservationWork
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.conversations.service import ConversationService
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from src.domains.voice_sessions.session import VoiceSession
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure.scheduler import voice_session_closing as closing_service
from src.infrastructure.scheduler.voice_reservation import schedule_session_relay
from src.infrastructure.streaming.reservation_work import finish_work
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


async def test_a_relay_cancelled_before_its_first_instruction_leaves_no_orphan_work(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.reservation_work.get_db_context", connection)
    async with connection() as db:
        admission = await ConversationExecutionRepository(db).admit(
            sources.annex,
            run_id=uuid4().hex,
            stream_id=uuid4().hex,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admission, RunAdmission)
        parent = await ConversationReservationRepository(db).begin_closing(
            admission, worker_id=uuid4()
        )
    tasks: list[asyncio.Task[None]] = []

    def cancel_before_start(
        coroutine: Coroutine[object, object, None], *, name: str
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine, name=name)
        tasks.append(task)
        task.cancel()
        return task

    async def body(bound: VoiceSession) -> None:
        pytest.fail("The cancelled relay must never start its body")

    monkeypatch.setattr(
        "src.infrastructure.scheduler.voice_reservation.safe_fire_and_forget", cancel_before_start
    )
    session = VoiceSession.browser(
        session_id=admission.stream_id,
        run_id=admission.run_id,
        mode="direct",
        user_id=sources.annex.owner_id,
        conversation_id=sources.annex.id,
        language="en",
        timezone="UTC",
        reservation=parent,
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await schedule_session_relay(session, body, name="cancel-before-start")
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)
    async with connection() as fresh:
        repo = ConversationReservationRepository(fresh)
        assert await repo.outstanding_workers(admission) == frozenset({parent.worker_id})
        await repo.finish(parent)
        assert await repo.is_closed(admission)


async def test_the_real_relay_holds_its_source_through_the_last_archive(
    async_engine: AsyncEngine,
    redis_client: Redis,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.reservation_work.get_db_context", connection)
    store = LiveSessionStore(redis_client)
    session_id = uuid4().hex
    target = sources.annex
    async with connection() as db:
        admitted = await ConversationExecutionRepository(db).admit(
            target,
            run_id=f"live_session_{session_id}",
            stream_id=session_id,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admitted, RunAdmission)
        closing = await ConversationReservationRepository(db).begin_closing(
            admitted, worker_id=uuid4()
        )
    now = datetime.now(UTC)
    record = LiveSessionRecord(
        session_id=session_id,
        user_id=target.owner_id,
        provider="gemini",
        model="fixture",
        run_id=admitted.run_id,
        started_at=now,
        expires_at=now + timedelta(minutes=10),
        token=uuid4().hex,
        lia_conversation_id=target.id,
        lia_conversation_revision=target.revision,
        lia_activity_id=admitted.activity_id,
    )
    assert await store.claim(record, ttl_seconds=60)
    session = VoiceSession.browser(
        session_id=session_id,
        run_id=record.run_id,
        mode="direct",
        user_id=target.owner_id,
        conversation_id=target.id,
        language="en",
        timezone="UTC",
        reservation=closing,
    )
    entered, proceed, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    published: list[str] = []

    async def relay(bound: VoiceSession) -> None:
        assert bound.reservation is not None and bound.reservation.id != closing.id
        task = asyncio.current_task()
        assert task is not None
        task.add_done_callback(lambda _: settled.set())
        entered.set()
        await proceed.wait()
        async with connection() as db:
            row = await ConversationService().archive_message(
                bound.publication, "assistant", "Synthetic relay result", {}, db
            )
            published.append(str(row.id))

    await schedule_session_relay(session, relay, name="native_live_relay_test")
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await finish_work(closing)
        assert await store.get(target.owner_id) is not None
        async with AsyncSession(async_engine) as db:
            busy = await ConversationExecutionRepository(db).active_for_owner(
                target.owner_id, kind=ExecutionKind.LIVE
            )
            assert busy is not None and busy.phase == ExecutionPhase.DRAINING
            await db.rollback()
            with pytest.raises(ResourceConflictError):
                await ConversationLifecycle(db).request_reset(
                    target.owner_id,
                    target.id,
                    operation_id=uuid4(),
                    expected_revision=target.revision,
                )
    finally:
        proceed.set()
        await asyncio.wait_for(settled.wait(), 10)
    assert len(published) == 1
    assert await store.get(target.owner_id) is None
    async with connection() as db:
        assert (
            await ConversationExecutionRepository(db).active_for_owner(
                target.owner_id, kind=ExecutionKind.LIVE
            )
            is None
        )
        messages = (
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.conversation_id == target.id,
                )
            )
        ).all()
        assert [row.content for row in messages] == ["Synthetic relay result"]


@pytest.mark.parametrize(
    ("closing_first", "lost_ack"), [(True, False), (False, False), (True, True)]
)
async def test_standby_recap_and_spend_reach_the_same_card_in_both_orders(
    async_engine: AsyncEngine,
    redis_client: Redis,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
    closing_first: bool,
    lost_ack: bool,
) -> None:
    """Ending Live can overtake a paid standby relay without losing its recap or bill."""

    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.reservation_work.get_db_context", connection)
    monkeypatch.setattr(closing_service, "get_db_context", connection)
    monkeypatch.setattr(closing_service, "record_decision", AsyncMock())
    monkeypatch.setattr(closing_service, "_notify_relay", AsyncMock())

    target = sources.annex
    session_id = uuid4().hex
    async with connection() as db:
        admission = await ConversationExecutionRepository(db).admit(
            target,
            run_id=f"live_session_{session_id}",
            stream_id=session_id,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admission, RunAdmission)
        standby = await ConversationReservationRepository(db).begin(
            admission, worker_id=uuid4(), purpose="request"
        )

    store = LiveSessionStore(redis_client)
    now = datetime.now(UTC)
    record = LiveSessionRecord(
        session_id=session_id,
        user_id=target.owner_id,
        provider="gemini",
        model="fixture",
        run_id=admission.run_id,
        started_at=now,
        expires_at=now + timedelta(minutes=10),
        token=uuid4().hex,
        lia_conversation_id=target.id,
        lia_conversation_revision=target.revision,
        lia_activity_id=admission.activity_id,
    )
    assert await store.claim(record, ttl_seconds=60)
    entered, release, joined = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls: list[str] = []

    async def paid_result(bound: VoiceSession, transcript: VoiceTranscript) -> tuple[str, str]:
        assert bound.conversation_id == target.id
        calls.extend(transcript.lines())
        task = asyncio.current_task()
        assert task is not None
        task.add_done_callback(lambda _: joined.set())
        entered.set()
        await release.wait()
        async with connection() as db:
            await ChatRepository(db).create_or_update_token_summary(
                run_id=admission.run_id,
                user_id=target.owner_id,
                session_id=session_id,
                conversation_id=target.id,
                summary_data={
                    FIELD_TOKENS_IN: 12,
                    FIELD_TOKENS_OUT: 3,
                    FIELD_TOKENS_CACHE: 0,
                    FIELD_COST_EUR: 0.25,
                },
            )
        return "busy", "Synthetic standby recap"

    monkeypatch.setattr(closing_service, "relay_direct_transcript", paid_result)
    writes: list[bool] = []
    if lost_ack:
        original_commit = closing_service._commit_standby_result

        async def commit_with_lost_ack(bound: VoiceSession, recap: str | None) -> bool:
            accepted = await original_commit(bound, recap)
            writes.append(accepted)
            if len(writes) == 1:
                raise OperationalError(None, None, ConnectionError("Synthetic lost commit reply"))
            return accepted

        monkeypatch.setattr(closing_service, "_commit_standby_result", commit_with_lost_ack)
    session = VoiceSession.browser(
        session_id=session_id,
        run_id=admission.run_id,
        mode="direct",
        user_id=target.owner_id,
        conversation_id=target.id,
        language="en",
        timezone="UTC",
        reservation=standby,
    )
    await closing_service.schedule_standby_relay(
        session,
        VoiceTranscript.from_rows([("user", "Synthetic standby words")]),
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await finish_work(standby)
        if not closing_first:
            release.set()
            await asyncio.wait_for(joined.wait(), 10)
            async with connection() as db:
                encrypted = await db.scalar(
                    select(ConversationReservationWork.standby_recap).where(
                        ConversationReservationWork.activity_id == admission.activity_id,
                        ConversationReservationWork.purpose == "relay",
                    )
                )
                assert encrypted and "Synthetic standby recap" not in encrypted
        async with connection() as db:
            closing = await ConversationReservationRepository(db).begin_closing(
                admission, worker_id=uuid4()
            )
        async with connection() as db:
            closed = await closing_service.close_voice_session(
                db,
                session=replace(session, reservation=closing),
                memory_enabled=False,
                outcome="ended",
                duration_seconds=20,
                extensions=0,
                standbys=1,
                standby_relays=await store.relays(record),
            )
        await finish_work(closing)
    finally:
        release.set()
        await asyncio.wait_for(joined.wait(), 10)

    assert calls == ["user: Synthetic standby words"]
    if lost_ack:
        assert writes == [True, False]
    assert await store.get(target.owner_id) is None
    async with connection() as db:
        card = await db.get(ConversationMessage, closed.summary_message_id)
        assert card is not None and card.conversation_id == target.id
        metadata = card.message_metadata or {}
        figures = metadata[FIELD_LIVE_SUMMARY]
        assert figures["standby_recaps"] == ["Synthetic standby recap"]
        assert metadata[FIELD_COST_EUR] == 0.25
        assert metadata[FIELD_TOKENS_IN] == 12 and metadata[FIELD_TOKENS_OUT] == 3
        work = await db.scalar(
            select(ConversationReservationWork).where(
                ConversationReservationWork.activity_id == admission.activity_id,
                ConversationReservationWork.purpose == "relay",
            )
        )
        assert work is not None and work.standby_relay_settled and work.standby_recap is None
