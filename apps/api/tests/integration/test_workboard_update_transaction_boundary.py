"""Native updates fence real GUI writes and dispatch notifications only after acknowledged commit."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.workboard_update import (
    execute_workboard_update,
    prepare_workboard_update,
)
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdateInput
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import CommentCreate, TicketCreate, TicketUpdate
from src.domains.workboard.service import WorkboardService
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("writer_kind", ["update", "move", "comment", "delete"])
async def test_gui_writers_wait_for_native_update(async_engine, monkeypatch, writer_kind):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    owner = uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        actor = User(id=owner, email=f"update-fence-{owner}@example.test", is_active=True)
        seed.add(actor)
        await seed.flush()
        ticket = await WorkboardService(seed).create(actor, TicketCreate(title="Committed target"))
        identity = ticket.id
        await seed.commit()
    source_update = WorkboardService.update
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            await assert_independent_lock_control(db, async_engine, owner)
            draft = await prepare_workboard_update(
                db, owner, WorkboardUpdateInput(ticket_id=identity, priority="high")
            )
            pid = await db.scalar(select(func.pg_backend_pid()))

            async def probe(service, actor, ticket_id, changes):
                async with AsyncSession(async_engine) as writer:
                    assert await writer.scalar(select(func.pg_backend_pid())) != pid
                    await writer.execute(text("SET LOCAL lock_timeout = '100ms'"))
                    own_actor = await writer.get(User, owner)
                    own_service = WorkboardService(writer)
                    with pytest.raises(DBAPIError) as waiting:
                        if writer_kind == "update":
                            await source_update(
                                own_service, own_actor, identity, TicketUpdate(title="GUI title")
                            )
                        elif writer_kind == "move":
                            await own_service.move(own_actor, identity, "done", 0)
                        elif writer_kind == "comment":
                            await own_service.comment(
                                own_actor, identity, CommentCreate(body="GUI comment")
                            )
                        else:
                            await own_service.delete(own_actor, identity)
                    assert getattr(waiting.value.orig, "sqlstate", None) == "55P03"
                    await writer.rollback()
                return await source_update(service, actor, ticket_id, changes)

            monkeypatch.setattr(WorkboardService, "update", probe)
            receipt = PreferenceWriteReceipt()
            await execute_workboard_update(db, owner, draft, receipt)
            assert receipt.committed
            assert (
                await db.scalar(
                    select(WorkboardTicket.priority).where(WorkboardTicket.id == identity)
                )
                == "high"
            )
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == owner))
            await cleanup.commit()


@pytest.mark.parametrize("delivery", ["success", "sql_failure", "revoked"])
async def test_assignment_notification_is_after_commit_and_owns_its_session(
    async_engine, monkeypatch, delivery
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner, peer = uuid4(), uuid4()
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        actor = User(id=owner, email=f"notice-owner-{owner}@example.test", is_active=True)
        recipient = User(id=peer, email=f"notice-peer-{peer}@example.test", is_active=True)
        seed.add_all([actor, recipient])
        await seed.flush()
        lo, hi = canonical_pair(owner, peer)
        seed.add(
            PeerConnection(
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=owner,
                status=PeerConnectionStatus.ACCEPTED.value,
            )
        )
        ticket = await WorkboardService(seed).create(
            actor, TicketCreate(title="Committed handover")
        )
        identity = ticket.id
        await seed.commit()
    calls = []

    @asynccontextmanager
    async def own_session():
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            yield session
            await session.commit()

    monkeypatch.setattr(
        "src.domains.agents.application.workboard_update.get_db_context", own_session
    )

    async def sink(*, db, **values):
        calls.append(values["target_id"])
        async with AsyncSession(async_engine) as reader:
            assert (
                await reader.scalar(
                    select(WorkboardTicket.assignee_user_id).where(WorkboardTicket.id == identity)
                )
                == peer
            )
            await assert_independent_lock_control(reader, async_engine, owner)
        if delivery == "sql_failure":
            await db.execute(text("SELECT * FROM native_notice_deliberately_missing_relation"))
        return True

    monkeypatch.setattr("src.domains.shared.proactive_sink.send_proactive_notification", sink)
    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            draft = await prepare_workboard_update(
                db, owner, WorkboardUpdateInput(ticket_id=identity, assignee_user_id=peer)
            )
            assert not calls
            if delivery == "revoked":
                from src.domains.workboard.assignment_notifications import (
                    dispatch_assignment_notices as source_dispatch,
                )

                async def revoke_before_dispatch(db, notices):
                    actor = await db.get(User, owner)
                    await WorkboardService(db).update(actor, identity, TicketUpdate(assignee="me"))
                    await db.commit()
                    return await source_dispatch(db, notices)

                monkeypatch.setattr(
                    "src.domains.agents.application.workboard_update.dispatch_assignment_notices",
                    revoke_before_dispatch,
                )
            receipt = PreferenceWriteReceipt()
            await execute_workboard_update(db, owner, draft, receipt)
            assert receipt.committed
            assert receipt.values["workboard_update"]["notification_status"] == (
                "delivered" if delivery == "success" else "failed"
            )
            assert len(calls) == (0 if delivery == "revoked" else 1)
            assert await db.scalar(select(func.count(WorkboardTicket.id))) == 1
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_([owner, peer])))
            await cleanup.commit()
