"""A debrief chooses identity only after the same account fence as grouping changes."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.relations.debrief.service import RelationDebriefService
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_paid_builder_does_not_choose_identity_while_grouping_owns_the_account(
    async_engine, monkeypatch
):
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"debrief-fence-{owner}@example.test",
                full_name="Disposable",
                is_active=True,
            )
        )
        await seed.commit()
    try:
        async with AsyncSession(async_engine) as manager:
            await assert_independent_lock_control(manager, async_engine, owner)
            await manager.scalar(select(User.id).where(User.id == owner).with_for_update())
            async with AsyncSession(async_engine) as writer:
                assert await writer.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                    select(func.pg_backend_pid())
                )
                await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))

                @asynccontextmanager
                async def session():
                    yield writer

                monkeypatch.setattr("src.domains.relations.debrief.service.get_db_context", session)
                service = RelationDebriefService(owner)
                monkeypatch.setattr(service, "_enabled", AsyncMock(return_value=True))
                identity = AsyncMock(return_value="alice")
                generation = AsyncMock(
                    side_effect=AssertionError("No provider may be invoked by this fence probe")
                )
                monkeypatch.setattr(service, "_identity_key", identity)
                monkeypatch.setattr(service, "_run_build", generation)
                with pytest.raises(DBAPIError) as blocked:
                    await service.build("Alice", force=True)
                assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
                identity.assert_not_awaited()
                generation.assert_not_awaited()
                await writer.rollback()
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
