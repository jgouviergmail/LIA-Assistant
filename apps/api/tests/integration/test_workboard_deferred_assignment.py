"""Source assignment can be collected without network or implicit commit before approval."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.workboard.assignment_notifications import dispatch_assignment_notices
from src.domains.workboard.models import WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.schemas import TicketCreate, TicketUpdate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


async def test_assignment_collects_source_notice_and_dispatches_after_commit(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    peer = User(
        id=uuid4(),
        email=f"deferred-peer-{uuid4()}@example.test",
        full_name="Deferred peer",
        is_active=True,
    )
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(test_user.id, peer.id)
    async_session.add(
        PeerConnection(
            user_a_id=lo,
            user_b_id=hi,
            requested_by_id=test_user.id,
            status=PeerConnectionStatus.ACCEPTED.value,
        )
    )
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Confirmed handover")
    )
    identity, peer_id = ticket.id, peer.id
    await async_session.commit()
    sink = AsyncMock(return_value=True)
    monkeypatch.setattr("src.domains.shared.proactive_sink.send_proactive_notification", sink)
    notices = []
    await WorkboardService(async_session, assignment_notices=notices).update(
        test_user, identity, TicketUpdate(assignee_user_id=peer_id)
    )
    sink.assert_not_awaited()
    assert len(notices) == 1 and notices[0].recipient_id == peer_id
    assert notices[0].ticket_id == identity
    assert await async_session.get(WorkboardTicketEvent, notices[0].event_id) is not None
    await async_session.commit()
    assert (
        await async_session.scalar(
            select(WorkboardTicket.assignee_user_id).where(WorkboardTicket.id == identity)
        )
        == peer_id
    )
    await dispatch_assignment_notices(async_session, notices)
    sink.assert_awaited_once()
    assert sink.await_args.kwargs["target_id"] == str(identity)
    assert str(notices[0].event_id) in sink.await_args.kwargs["run_id"]


async def test_preview_rollback_keeps_source_ticket_and_events(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    ticket = await WorkboardService(async_session).create(
        test_user, TicketCreate(title="Original source title")
    )
    identity = ticket.id
    await async_session.commit()
    from src.domains.workboard.mutation_preview import preview_ticket_mutation

    result = await preview_ticket_mutation(
        async_session,
        test_user.id,
        identity,
        TicketUpdate(title="Previewed title", priority="high"),
    )
    assert result.ticket["title"] == "Previewed title" and result.ticket["priority"] == "high"
    await async_session.commit()
    actual = await async_session.get(WorkboardTicket, identity, populate_existing=True)
    assert actual.title == "Original source title" and actual.priority == "medium"
    events = list(
        (
            await async_session.scalars(
                select(WorkboardTicketEvent).where(WorkboardTicketEvent.ticket_id == identity)
            )
        ).all()
    )
    assert len(events) == 1 and events[0].kind == "created"
