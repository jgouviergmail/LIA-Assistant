"""Independent GUI metadata, toggle and deletion writers wait on the native owner fence."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.space_update import execute_space_update, prepare_space_update
from src.domains.agents.application.space_update_schemas import SpaceUpdateInput
from src.domains.rag_spaces.models import RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("writer_kind", ["metadata", "toggle", "delete"])
async def test_gui_writers_cannot_cross_confirmed_space_fence(
    async_engine, monkeypatch, writer_kind
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    owner, identity = uuid4(), uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(User(id=owner, email=f"space-update-fence-{owner}@example.test", is_active=True))
        await seed.flush()
        seed.add(RAGSpace(id=identity, user_id=owner, name="Original personal space"))
        await seed.commit()
    source_update = RAGSpaceService.update_space
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def probe(service, *args, **kwargs):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    gui = RAGSpaceService(writer)
                    with pytest.raises(DBAPIError) as waiting:
                        if writer_kind == "metadata":
                            await source_update(gui, identity, owner, name="Concurrent GUI rename")
                        elif writer_kind == "toggle":
                            await gui.toggle_space(identity, owner)
                        else:
                            await gui.delete_space(identity, owner)
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_update(service, *args, **kwargs)

            monkeypatch.setattr(RAGSpaceService, "update_space", probe)
            draft = await prepare_space_update(
                db, owner, SpaceUpdateInput(space_id=identity, name="Confirmed rename")
            )
            receipt = PreferenceWriteReceipt()
            await execute_space_update(db, owner, draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
