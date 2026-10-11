"""Independent GUI creation cannot bypass the native owner cap fence."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.workboard_create import (
    execute_workboard_creation,
    prepare_workboard_creation,
)
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateInput
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_source_gui_creation_waits_for_native_fence(async_engine, monkeypatch):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    owner = uuid4()
    async with AsyncSession(async_engine) as seed:
        seed.add(
            User(
                id=owner,
                email=f"board-create-fence-{owner}@example.com",
                full_name="Owner",
                is_active=True,
            )
        )
        await seed.commit()
    source_create = WorkboardService.create
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def probe(service, actor, payload, **kwargs):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    other_actor = await writer.get(User, owner)
                    with pytest.raises(DBAPIError) as waiting:
                        await source_create(
                            WorkboardService(writer),
                            other_actor,
                            TicketCreate(title="Concurrent GUI creation"),
                        )
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_create(service, actor, payload, **kwargs)

            monkeypatch.setattr(WorkboardService, "create", probe)
            draft = await prepare_workboard_creation(
                db, owner, WorkboardCreateInput(title="Approved native creation")
            )
            receipt = PreferenceWriteReceipt()
            await execute_workboard_creation(db, owner, draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
