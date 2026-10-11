"""Independent source writers cannot change a subtree under native deletion consent."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.workboard_delete import (
    execute_workboard_delete,
    prepare_workboard_delete,
)
from src.domains.agents.application.workboard_delete_schemas import WorkboardDeleteInput
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.schemas import CommentCreate, TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("writer_kind", ["delete", "comment", "child"])
async def test_source_writers_wait_for_native_deletion(async_engine, monkeypatch, writer_kind):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    owner = uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        actor = User(id=owner, email=f"delete-fence-{owner}@example.test", is_active=True)
        seed.add(actor)
        await seed.flush()
        ticket = await WorkboardService(seed).create(actor, TicketCreate(title="Committed parent"))
        child = await WorkboardService(seed).create(
            actor, TicketCreate(title="Committed child", parent_id=ticket.id)
        )
        identity, child_id = ticket.id, child.id
        await seed.commit()
    source_delete = WorkboardService.delete
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def probe(service, actor, ticket_id):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    own_actor = await writer.get(User, owner)
                    with pytest.raises(DBAPIError) as waiting:
                        own_service = WorkboardService(writer)
                        if writer_kind == "delete":
                            await source_delete(own_service, own_actor, child_id)
                        elif writer_kind == "comment":
                            await own_service.comment(
                                own_actor, child_id, CommentCreate(body="GUI writer")
                            )
                        else:
                            await own_service.create(
                                own_actor, TicketCreate(title="GUI child", parent_id=identity)
                            )
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_delete(service, actor, ticket_id)

            monkeypatch.setattr(WorkboardService, "delete", probe)
            draft = await prepare_workboard_delete(
                db, owner, WorkboardDeleteInput(ticket_id=identity)
            )
            receipt = PreferenceWriteReceipt()
            await execute_workboard_delete(db, owner, draft, receipt)
            assert receipt.committed and receipt.values["workboard_delete"]["removed"] == 2
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
