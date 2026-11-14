"""Physical account writers remain visible until all owned disk work has joined."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from scripts.data import recover_file_writes
from src.core.exceptions import BaseAPIException
from src.domains.users.account_cleanup import refuse_account_writers
from src.domains.users.file_writer_models import AccountFileWriter
from src.domains.users.file_writers import account_file_write
from src.domains.users.models import User
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def test_inactive_account_refuses_cleanup_until_its_file_writer_finishes(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as caller:
        async with account_file_write(caller, owner):
            # A nested skill of a plugin shares its caller's durable act.
            async with account_file_write(caller, owner):
                assert not caller.in_transaction()
                async with AsyncSession(async_engine) as observer:
                    rows = list(
                        await observer.scalars(
                            select(AccountFileWriter).where(AccountFileWriter.user_id == owner)
                        )
                    )
                    assert len(rows) == 1
                    await observer.execute(
                        update(User).where(User.id == owner).values(is_active=False)
                    )
                    await observer.commit()
                    with pytest.raises(BaseAPIException):
                        await refuse_account_writers(observer, owner)
        async with AsyncSession(async_engine) as observer:
            await refuse_account_writers(observer, owner)
            assert (
                await observer.scalar(
                    select(AccountFileWriter.id).where(AccountFileWriter.user_id == owner)
                )
                is None
            )
        with pytest.raises(BaseAPIException):
            async with account_file_write(caller, owner):
                pytest.fail("Inactive account started a filesystem write")


async def test_cancelled_writer_settles_only_after_its_cleanup_joins(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    started, finishing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def work() -> None:
        async with AsyncSession(async_engine) as db:
            async with account_file_write(db, owner):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    finishing.set()
                    await release.wait()

    task = asyncio.create_task(work())
    try:
        await asyncio.wait_for(started.wait(), 10)
        task.cancel()
        await asyncio.wait_for(finishing.wait(), 10)
        async with AsyncSession(async_engine) as db:
            assert (
                await db.scalar(
                    select(AccountFileWriter.id).where(AccountFileWriter.user_id == owner)
                )
                is not None
            )
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with AsyncSession(async_engine) as db:
            assert (
                await db.scalar(
                    select(AccountFileWriter.id).where(AccountFileWriter.user_id == owner)
                )
                is None
            )
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_child_task_owns_a_distinct_writer_and_survives_parent_exit(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    started, release = asyncio.Event(), asyncio.Event()

    async def child() -> None:
        async with AsyncSession(async_engine) as db:
            async with account_file_write(db, owner):
                started.set()
                await release.wait()

    async with AsyncSession(async_engine) as db:
        task: asyncio.Task[None] | None = None
        try:
            async with account_file_write(db, owner):
                task = asyncio.create_task(child())
                await asyncio.wait_for(started.wait(), 10)
                assert (
                    len(
                        list(
                            await db.scalars(
                                select(AccountFileWriter.id).where(
                                    AccountFileWriter.user_id == owner
                                )
                            )
                        )
                    )
                    == 2
                )
                await db.commit()
            assert (
                len(
                    list(
                        await db.scalars(
                            select(AccountFileWriter.id).where(AccountFileWriter.user_id == owner)
                        )
                    )
                )
                == 1
            )
        finally:
            release.set()
            if task is not None:
                await task


async def test_recovery_reports_and_retires_only_the_attested_boot(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    owner = await commit_owner(async_engine, committed_user_ids)
    stopped, running = uuid4(), uuid4()
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                AccountFileWriter(user_id=owner, worker_id=stopped),
                AccountFileWriter(user_id=owner, worker_id=running),
            ]
        )
        await db.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(recover_file_writes, "get_db_context", session)
    inspected = await recover_file_writes._recover("inspect", stopped)
    assert inspected.writer_count == 1
    retired = await recover_file_writes._recover("retire", stopped)
    assert retired.writer_count == 1
    assert (await recover_file_writes._recover("inspect", stopped)).writer_count == 0
    assert (await recover_file_writes._recover("inspect", running)).writer_count == 1
