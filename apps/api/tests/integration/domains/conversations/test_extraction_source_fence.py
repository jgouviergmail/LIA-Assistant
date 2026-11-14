"""Deferred learning keeps its immutable source after the graph authority ends."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.run_authority import current_run_authority, run_authority_scope
from src.domains.agents.context.extraction_revision import with_current_extraction_revision
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.users.extraction_consent import (
    ExtractionKind,
    snapshot_extraction_consent,
    snapshot_extraction_revision,
)
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget
from tests.fixtures.learning_sources import Sources, source_authority
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


async def test_turn_still_captures_learning_revision_when_three_record_preferences_are_off(
    async_engine: AsyncEngine, sources: Sources, monkeypatch: pytest.MonkeyPatch
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db

    monkeypatch.setattr("src.domains.agents.context.extraction_revision.get_db_context", session)
    context = LiaRuntimeContext.for_conversation(
        target=sources.annex, memory_enabled=False, journals_enabled=False, psyche_enabled=False
    )
    captured = await with_current_extraction_revision(context)
    assert captured.extraction_revision == 0
    assert captured.conversation_id == context.conversation_id
    assert (
        not captured.memory_enabled
        and not captured.journals_enabled
        and not captured.psyche_enabled
    )


async def _snapshot(
    db: AsyncSession, owner: UUID, kind: ExtractionKind | None, *, lock: bool
) -> int | None:
    if kind is None:
        return await snapshot_extraction_revision(db, owner, expected_revision=0, lock=lock)
    return await snapshot_extraction_consent(db, owner, kind, expected_revision=0, lock=lock)


@pytest.mark.parametrize("kind", [*ExtractionKind, None])
@pytest.mark.parametrize("retire_source", [True, False])
async def test_result_returning_after_reset_only_loses_its_own_source(
    async_engine: AsyncEngine,
    sources: Sources,
    kind: ExtractionKind | None,
    retire_source: bool,
) -> None:
    """The final SQL write gate must recheck after the provider/embedding wait."""
    target = sources.annex
    started, release = asyncio.Event(), asyncio.Event()

    async def extraction() -> int | None:
        assert current_run_authority() is None
        async with AsyncSession(async_engine) as db:
            assert await _snapshot(db, target.owner_id, kind, lock=False) == 0
            await db.commit()
        started.set()
        await release.wait()
        async with AsyncSession(async_engine) as db:
            return await _snapshot(db, target.owner_id, kind, lock=True)

    with run_authority_scope(source_authority(target)):
        task = safe_fire_and_forget(extraction(), independent_of_graph=True)
    try:
        await asyncio.wait_for(started.wait(), 10)
        reset = target if retire_source else sources.main
        async with AsyncSession(async_engine) as db:
            await ConversationLifecycle(db).request_reset(
                reset.owner_id, reset.id, operation_id=uuid4(), expected_revision=0
            )
            assert (
                await db.scalar(select(User.extraction_revision).where(User.id == target.owner_id))
                == 0
            ), "A discussion reset must not invalidate learning from every other discussion"
        release.set()
        assert await task == (None if retire_source else 0)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_final_source_lock_serializes_with_retirement(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    """A check then a write share the transaction the reset cannot pass."""
    target = sources.annex
    async with AsyncSession(async_engine) as writer:
        with run_authority_scope(source_authority(target)):
            assert await _snapshot(writer, target.owner_id, ExtractionKind.MEMORY, lock=True) == 0

        async def reset() -> None:
            async with AsyncSession(async_engine) as db:
                await ConversationLifecycle(db).request_reset(
                    target.owner_id, target.id, operation_id=uuid4(), expected_revision=0
                )

        task = asyncio.create_task(reset())
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 0.1)
            await writer.commit()
            await asyncio.wait_for(task, 10)
        finally:
            await writer.rollback()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
