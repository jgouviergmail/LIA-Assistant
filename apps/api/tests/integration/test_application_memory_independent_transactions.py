"""Real commits and distinct PostgreSQL connections prove lock boundaries."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.agents.application.memory_bulk_removal import (
    execute_memory_bulk_removal,
    prepare_memory_bulk_removal,
)
from src.domains.agents.application.memory_bulk_schemas import MemoryBulkDeleteRequest
from src.domains.agents.application.memory_create_schemas import MemoryCreateConfiguration
from src.domains.agents.application.memory_creation import (
    execute_memory_creation,
    prepare_memory_creation,
)
from src.domains.agents.application.memory_update import (
    execute_memory_update,
    prepare_memory_update,
)
from src.domains.agents.application.memory_update_schemas import (
    MemoryUpdateChanges,
    MemoryUpdateRequest,
)
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def committed_actor(async_engine: AsyncEngine) -> AsyncIterator[UUID]:
    identity = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=identity,
                email=f"memory-lock-{identity}@example.test",
                full_name="Disposable memory actor",
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
        )
        await seed.commit()
    try:
        yield identity
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == identity))
            await cleanup.commit()


async def assert_independent_lock_control(
    db: AsyncSession, engine: AsyncEngine, actor_id: UUID
) -> None:
    """A positive control prevents same-connection probes from falsely passing."""
    parent_pid = await db.scalar(select(func.pg_backend_pid()))
    await db.scalar(select(User.id).where(User.id == actor_id).with_for_update())
    async with AsyncSession(engine) as observer:
        assert await observer.scalar(select(func.pg_backend_pid())) != parent_pid
        with pytest.raises(DBAPIError) as refused:
            await observer.scalar(
                select(User.id).where(User.id == actor_id).with_for_update(nowait=True)
            )
        assert getattr(refused.value.orig, "sqlstate", None) == "55P03"
    await db.rollback()


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_paid_preparation_has_no_user_lock_on_distinct_connections(
    async_engine: AsyncEngine,
    committed_actor: UUID,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id, memory_id = committed_actor, uuid4()
    calls: list[str] = []
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        await assert_independent_lock_control(db, async_engine, actor_id)
        if operation == "update":
            db.add(
                Memory(
                    id=memory_id,
                    user_id=actor_id,
                    content="Original fact",
                    category="personal",
                    char_count=13,
                )
            )
            await db.commit()
            draft = await prepare_memory_update(
                db,
                actor_id,
                MemoryUpdateRequest(
                    memory_id=memory_id, changes=MemoryUpdateChanges(content="Revised fact")
                ),
            )
        else:
            draft = await prepare_memory_creation(
                db, actor_id, MemoryCreateConfiguration(content="Created fact", category="personal")
            )
        parent_pid = await db.scalar(select(func.pg_backend_pid()))

        async def provider(text: str) -> None:
            async with AsyncSession(async_engine) as observer:
                assert await observer.scalar(select(func.pg_backend_pid())) != parent_pid
                assert (
                    await observer.scalar(
                        select(User.id).where(User.id == actor_id).with_for_update(nowait=True)
                    )
                    == actor_id
                )
                await observer.rollback()
            calls.append(text)
            return None

        receipt = PreferenceWriteReceipt()
        with (
            patch(
                "src.domains.agents.application.memory_creation_embeddings.enforce_usage_limit",
                AsyncMock(),
            ),
            patch(
                "src.domains.agents.application.memory_creation_embeddings._generate_document_embedding",
                provider,
            ),
        ):
            execute = execute_memory_creation if operation == "create" else execute_memory_update
            await execute(db, actor_id, draft, receipt)
        assert receipt.committed and len(calls) == 1


async def test_unconfirmed_insert_waits_for_bulk_commit_then_survives(
    async_engine: AsyncEngine, committed_actor: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = committed_actor
    child_pids: list[int] = []
    tasks: list[asyncio.Task[None]] = []
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        await assert_independent_lock_control(db, async_engine, actor_id)
        db.add(
            Memory(
                user_id=actor_id, content="Confirmed old fact", category="personal", char_count=18
            )
        )
        await db.commit()
        draft = await prepare_memory_bulk_removal(db, actor_id, MemoryBulkDeleteRequest())
        parent_pid = await db.scalar(select(func.pg_backend_pid()))
        started = asyncio.Event()
        source_delete = MemoryRepository.delete_all_for_user

        async def insert_later() -> None:
            async with AsyncSession(async_engine) as child:
                child_pids.append(await child.scalar(select(func.pg_backend_pid())))
                assert child_pids[0] != parent_pid
                started.set()
                child.add(
                    Memory(
                        user_id=actor_id,
                        content="Future unconfirmed fact",
                        category="personal",
                        char_count=23,
                    )
                )
                await child.commit()

        async def probe_then_delete(
            repository: MemoryRepository, user_id: UUID, preserve_pinned: bool = False
        ) -> int:
            task = asyncio.create_task(insert_later())
            tasks.append(task)
            await asyncio.wait_for(started.wait(), timeout=2)
            blockers: list[int] = []
            for _ in range(25):
                await asyncio.sleep(0.02)
                blockers = await db.scalar(select(func.pg_blocking_pids(child_pids[0])))
                if parent_pid in blockers:
                    break
            assert parent_pid in blockers and not task.done()
            return await source_delete(repository, user_id, preserve_pinned)

        try:
            monkeypatch.setattr(MemoryRepository, "delete_all_for_user", probe_then_delete)
            receipt = PreferenceWriteReceipt()
            await execute_memory_bulk_removal(db, actor_id, draft, receipt)
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
            assert receipt.committed
            remaining = list(
                await db.scalars(select(Memory.content).where(Memory.user_id == actor_id))
            )
            assert remaining == ["Future unconfirmed fact"]
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
