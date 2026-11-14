"""The real Live service archives into its reserved discussion on real PostgreSQL/Redis."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionKind, RunAdmission
from src.core.conversation_selection import ConversationSelection
from src.core.exceptions import ResourceConflictError
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.live.errors import LiveRefusedError
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers import LiveSetupInputs, setup_inputs_to_dict
from src.domains.live.schemas import LiveTurnRequest
from src.domains.live.service import LiveService
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from src.domains.users.models import User
from src.infrastructure.streaming.live_binding import (
    bind_record,
    delegated_target,
    prepare_live_retirement,
)
from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def work_sessions(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every real work settlement uses the same disposable SQL target."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.reservation_work.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.streaming.live_binding.get_db_context", session)


@pytest.mark.parametrize("legacy", [False, True])
async def test_voice_only_archive_uses_the_bound_target_or_binds_legacy_main_once(
    async_engine: AsyncEngine,
    redis_client: Redis,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
) -> None:
    target = sources.main if legacy else sources.annex
    session_id = uuid4().hex
    store = LiveSessionStore(redis_client)
    now = datetime.now(UTC)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        admission: RunAdmission | None = None
        if not legacy:
            admitted = await ConversationExecutionRepository(db).admit(
                target,
                run_id=f"live_session_{session_id}",
                stream_id=session_id,
                worker_id=uuid4(),
                kind=ExecutionKind.LIVE,
            )
            assert isinstance(admitted, RunAdmission)
            admission = admitted
        user = await db.get(User, target.owner_id)
        assert user is not None
        await db.commit()
        record = LiveSessionRecord(
            session_id=session_id,
            user_id=user.id,
            provider="gemini",
            model="fixture",
            run_id=f"live_session_{session_id}",
            started_at=now,
            expires_at=now + timedelta(minutes=10),
            token=uuid4().hex,
            setup_inputs=setup_inputs_to_dict(
                LiveSetupInputs(
                    model="fixture",
                    voice="fixture",
                    thinking_level=None,
                    system_instruction="Synthetic test setup",
                    tool_declaration=None,
                    preferences=LivePreferences(),
                    trigger_tokens=100,
                    target_tokens=50,
                )
            ),
            lia_activity_id=admission.activity_id if admission else None,
            lia_conversation_id=target.id if admission else None,
            lia_conversation_revision=target.revision if admission else None,
        )
        assert await store.claim(record, ttl_seconds=60)
        await prepare_live_retirement(user.id)
        async with AsyncSession(async_engine) as resetting:
            with pytest.raises(ResourceConflictError):
                await ConversationLifecycle(resetting).request_reset(
                    target.owner_id,
                    target.id,
                    operation_id=uuid4(),
                    expected_revision=target.revision,
                )
        service = LiveService(db)

        async def get_store() -> LiveSessionStore:
            return store

        monkeypatch.setattr(service, "_store", get_store)
        result = await service.archive_turn(
            user,
            session_id,
            LiveTurnRequest(
                user_text="Synthetic request",
                assistant_text="Synthetic answer",
                started_at=now,
                ended_at=now + timedelta(seconds=1),
            ),
            language="en",
        )
        assert result.user_message_id is not None and result.assistant_message_id is not None
        rows = (
            await db.scalars(
                select(ConversationMessage).where(
                    ConversationMessage.id.in_(
                        (result.user_message_id, result.assistant_message_id)
                    )
                )
            )
        ).all()
        assert len(rows) == 2
        assert {row.conversation_id for row in rows} == {target.id}
        kept = await store.get(user.id)
        assert kept is not None and kept.lia_conversation_id == target.id
        assert kept.lia_conversation_revision == target.revision
        assert kept.lia_activity_id is not None
        await db.commit()
        if legacy:
            # A second worker read the old record before the first binding
            # committed. It must adopt that SAME binding, never quarantine it.
            rebound, same = await bind_record(db, store, record, language="en")
            assert rebound.lia_activity_id == kept.lia_activity_id == same.activity_id
        assert await delegated_target(user.id, session_id, ConversationSelection()) == target
        other = sources.annex if legacy else sources.main
        with pytest.raises(ResourceConflictError):
            await delegated_target(
                user.id,
                session_id,
                ConversationSelection(
                    conversation_id=other.id,
                    conversation_revision=other.revision,
                ),
            )
        with pytest.raises(LiveRefusedError) as missing:
            await delegated_target(uuid4(), session_id, ConversationSelection())
        assert missing.value.status_code == 404


async def test_explicitly_closed_sql_reservation_releases_its_stale_redis_record(
    async_engine: AsyncEngine,
    redis_client: Redis,
    sources: Sources,
) -> None:
    """A lost Redis cleanup acknowledgment must not block the next start forever."""
    store = LiveSessionStore(redis_client)
    session_id = uuid4().hex
    now = datetime.now(UTC)
    async with AsyncSession(async_engine) as db:
        admission = await ConversationExecutionRepository(db).admit(
            sources.annex,
            run_id=uuid4().hex,
            stream_id=session_id,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admission, RunAdmission)
        repo = ConversationReservationRepository(db)
        closing = await repo.begin_closing(admission, worker_id=uuid4())
        assert await repo.finish(closing)
        await db.commit()
    record = LiveSessionRecord(
        session_id=session_id,
        user_id=sources.annex.owner_id,
        provider="gemini",
        model="fixture",
        run_id=admission.run_id,
        started_at=now,
        expires_at=now + timedelta(minutes=10),
        token=uuid4().hex,
        setup_inputs={},
        lia_activity_id=admission.activity_id,
        lia_conversation_id=sources.annex.id,
        lia_conversation_revision=sources.annex.revision,
    )
    assert await store.claim(record, ttl_seconds=60)
    await prepare_live_retirement(record.user_id)
    assert await store.get(record.user_id) is None
