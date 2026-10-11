"""Independent PostgreSQL connections prove appraisal writes wait on the owner before flushing."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.psyche.models import PsycheState
from src.domains.psyche.repository import PsycheStateRepository
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_appraisal_owner_fence_prevents_child_lock_inversion(
    async_engine: AsyncEngine,
) -> None:
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"psyche-lock-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
            )
        )
        await seed.commit()
        seed.add(PsycheState(user_id=owner))
        await seed.commit()
    try:
        async with AsyncSession(async_engine) as manager:
            await assert_independent_lock_control(manager, async_engine, owner)
            await manager.scalar(select(User.id).where(User.id == owner).with_for_update())
            async with AsyncSession(async_engine) as writer:
                assert await writer.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                    select(func.pg_backend_pid())
                )
                state = await writer.scalar(select(PsycheState).where(PsycheState.user_id == owner))
                assert state is not None
                state.mood_pleasure = 0.9
                with writer.no_autoflush:
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(DBAPIError) as blocked:
                    await PsycheStateRepository(writer).update(state)
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
            managed = await manager.scalar(
                select(PsycheState).where(PsycheState.user_id == owner).with_for_update(nowait=True)
            )
            assert managed is not None and managed.mood_pleasure == 0.0
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
