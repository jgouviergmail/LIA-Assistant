"""A real FK writer cannot enter the approved deletion scope while its parent is locked."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.agents.application.interest_bulk_removal import (
    execute_interest_bulk_removal,
    prepare_interest_bulk_removal,
)
from src.domains.agents.application.interest_bulk_schemas import InterestBulkDeleteRequest
from src.domains.interests.models import UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_future_interest_is_blocked_then_survives_confirmed_global_erasure(
    async_engine: AsyncEngine,
) -> None:
    owner = uuid4()
    tasks: list[asyncio.Task[None]] = []
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"bulk-interest-lock-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
                is_verified=True,
            )
        )
        await seed.commit()
        seed.add(
            UserInterest(
                user_id=owner,
                topic="Confirmed topic",
                category="science",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            draft = await prepare_interest_bulk_removal(
                db, owner, InterestBulkDeleteRequest(scope="all_owned")
            )
            parent_pid = await db.scalar(select(func.pg_backend_pid()))
            child_pids: list[int] = []
            started = asyncio.Event()
            original = InterestRepository.delete_all_for_user

            async def insert_later() -> None:
                async with AsyncSession(async_engine) as child:
                    child_pids.append(await child.scalar(select(func.pg_backend_pid())))
                    assert child_pids[0] != parent_pid
                    started.set()
                    child.add(
                        UserInterest(
                            user_id=owner,
                            topic="Future topic",
                            category="science",
                            last_mentioned_at=datetime.now(UTC),
                        )
                    )
                    await child.commit()

            async def probe(repository: InterestRepository, actor_id):
                pending = asyncio.create_task(insert_later())
                tasks.append(pending)
                await asyncio.wait_for(started.wait(), timeout=2)
                blockers = []
                for _ in range(25):
                    await asyncio.sleep(0.02)
                    blockers = await db.scalar(select(func.pg_blocking_pids(child_pids[0])))
                    if parent_pid in blockers:
                        break
                assert parent_pid in blockers and not pending.done()
                return await original(repository, actor_id)

            with patch.object(InterestRepository, "delete_all_for_user", probe):
                receipt = PreferenceWriteReceipt()
                await execute_interest_bulk_removal(db, owner, draft, receipt)
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
            assert receipt.committed
            assert list(
                await db.scalars(select(UserInterest.topic).where(UserInterest.user_id == owner))
            ) == ["Future topic"]
    finally:
        for pending in tasks:
            if not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
