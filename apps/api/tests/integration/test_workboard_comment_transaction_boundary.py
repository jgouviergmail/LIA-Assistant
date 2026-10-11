"""Independent GUI comments must wait under the native account/ticket fence."""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.workboard_comment import (
    execute_workboard_comment,
    prepare_workboard_comment,
)
from src.domains.agents.application.workboard_comment_schemas import WorkboardCommentInput
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.schemas import CommentCreate, TicketCreate
from src.domains.workboard.service import WorkboardService
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


async def test_source_comment_waits_for_the_native_fence(async_engine, monkeypatch):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    owner = uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        actor = User(id=owner, email=f"comment-fence-{owner}@example.test", is_active=True)
        seed.add(actor)
        await seed.flush()
        ticket = await WorkboardService(seed).create(actor, TicketCreate(title="Committed target"))
        identity = ticket.id
        await seed.commit()
    source_comment = WorkboardService.comment
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def probe(service, actor, ticket_id, payload, **kwargs):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    own_actor = await writer.get(User, owner)
                    with pytest.raises(DBAPIError) as waiting:
                        await source_comment(
                            WorkboardService(writer),
                            own_actor,
                            ticket_id,
                            CommentCreate(body="GUI writer"),
                        )
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_comment(service, actor, ticket_id, payload, **kwargs)

            monkeypatch.setattr(WorkboardService, "comment", probe)
            draft = await prepare_workboard_comment(
                db, owner, WorkboardCommentInput(ticket_id=identity, body="Approved native comment")
            )
            receipt = PreferenceWriteReceipt()
            await execute_workboard_comment(db, owner, draft, receipt)
            assert receipt.committed
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()
