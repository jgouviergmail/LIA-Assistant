"""A real Live opening reserves its source before the simulated vendor is reached."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionKind, ExecutionPhase
from src.core.conversation_selection import ConversationSelection
from src.core.exceptions import ResourceConflictError
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.live.binding import opening_work
from src.domains.live.errors import LiveRefusedError
from src.domains.live.preferences import LivePreferences
from src.domains.live.providers import LiveCredential, LiveSetupInputs
from src.domains.live.providers.gemini import GeminiLiveProvider
from src.domains.live.service import LiveService
from src.domains.users.models import User
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def native_work_sessions(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace connection composition alone, preserving every SQL admission and settlement."""

    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.infrastructure.streaming.reservation_work.get_db_context", connection)


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("outcome", ["ok", "refused", "unknown", "cancelled"])
async def test_opening_owns_its_source_and_vendor_failures_have_distinct_settlements(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
    legacy: bool,
    outcome: Literal["ok", "refused", "unknown", "cancelled"],
) -> None:
    target = sources.main if legacy else sources.annex
    selection = (
        ConversationSelection()
        if legacy
        else ConversationSelection(
            conversation_id=target.id,
            conversation_revision=target.revision,
        )
    )
    calls = 0
    provider = GeminiLiveProvider()

    async def mint(
        api_key: str,
        inputs: LiveSetupInputs,
        *,
        expires_at: datetime,
        connect_deadline_at: datetime,
    ) -> LiveCredential:
        nonlocal calls
        calls += 1
        async with AsyncSession(async_engine) as inspector:
            assert (
                await inspector.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND state = 'idle in transaction'"
                    )
                )
                == 0
            )
            busy = await ConversationExecutionRepository(inspector).active_for_owner(
                target.owner_id,
                kind=ExecutionKind.LIVE,
            )
            assert busy is not None and busy.target == target
        if outcome == "unknown":
            raise httpx.ReadTimeout("Synthetic unanswered mint")
        if outcome == "cancelled":
            raise asyncio.CancelledError
        if outcome == "refused":
            raise httpx.ConnectError("Synthetic connection refusal")
        return LiveCredential("synthetic-credential", expires_at, connect_deadline_at)

    async def undo() -> None:
        """No Redis record was claimed by this provider-boundary test."""

    monkeypatch.setattr(provider, "mint", mint)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        user = await db.get(User, target.owner_id)
        assert user is not None
        await db.commit()
        service = LiveService(db)

        async def open_and_mint() -> None:
            async with opening_work(
                service,
                user,
                selection,
                session_id=uuid4().hex,
                run_id=uuid4().hex,
                language="en",
            ) as work:
                assert work.admission.target == target
                credential = await service._mint(
                    provider,
                    "synthetic-key",
                    LiveSetupInputs(
                        model="gemini-3.8-live",
                        voice="Kore",
                        thinking_level=None,
                        system_instruction="Synthetic setup",
                        tool_declaration=None,
                        preferences=LivePreferences(),
                        trigger_tokens=100,
                        target_tokens=50,
                    ),
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                    language="en",
                    on_failure=undo,
                )
                assert credential.credential == "synthetic-credential"

        if outcome == "ok":
            await open_and_mint()
        else:
            error_type = asyncio.CancelledError if outcome == "cancelled" else LiveRefusedError
            with pytest.raises(error_type):
                await open_and_mint()
    assert calls == 1
    async with AsyncSession(async_engine) as fresh:
        repo = ConversationReservationRepository(fresh)
        admission = await repo.active_admission(target.owner_id)
        if outcome == "refused":
            assert admission is None
            return
        assert admission is not None and admission.target == target
        busy = await ConversationExecutionRepository(fresh).active_for_owner(
            target.owner_id,
            kind=ExecutionKind.LIVE,
        )
        assert busy is not None
        assert busy.phase == (
            ExecutionPhase.RUNNING if outcome == "ok" else ExecutionPhase.RECOVERING
        )
        assert bool(await repo.outstanding_workers(admission)) == (outcome != "ok")


async def test_a_completed_reset_refuses_the_old_opening_before_any_provider_work(
    async_engine: AsyncEngine,
    sources: Sources,
) -> None:
    target = sources.annex
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        user = await db.get(User, target.owner_id)
        assert user is not None
        await ConversationLifecycle(db).request_reset(
            target.owner_id,
            target.id,
            operation_id=uuid4(),
            expected_revision=target.revision,
        )
        with pytest.raises(ResourceConflictError):
            async with opening_work(
                LiveService(db),
                user,
                ConversationSelection(
                    conversation_id=target.id,
                    conversation_revision=target.revision,
                ),
                session_id=uuid4().hex,
                run_id=uuid4().hex,
                language="en",
            ):
                pytest.fail("A stale opening reached the provider boundary")
