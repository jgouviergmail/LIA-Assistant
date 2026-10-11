"""An independent GUI creator cannot cross the native source account quota fence."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.space_create import (
    execute_space_creation,
    prepare_space_creation,
)
from src.domains.agents.application.space_create_schemas import SpaceCreateInput
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_source_gui_creator_waits_for_confirmed_native_quota_fence(async_engine, monkeypatch):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(User(id=owner, email=f"space-create-fence-{owner}@example.test", is_active=True))
        await seed.commit()
    source_create = RAGSpaceService.create_space
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def probe(service, actor_id, name, description=None, **kwargs):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    with pytest.raises(DBAPIError) as waiting:
                        await source_create(
                            RAGSpaceService(writer), owner, "Concurrent GUI creation"
                        )
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_create(service, actor_id, name, description, **kwargs)

            monkeypatch.setattr(RAGSpaceService, "create_space", probe)
            draft = await prepare_space_creation(
                db, owner, SpaceCreateInput(name="Approved native creation")
            )
            receipt = PreferenceWriteReceipt()
            await execute_space_creation(db, owner, draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
