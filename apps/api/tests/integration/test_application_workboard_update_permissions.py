"""Native authority follows the real source owner/holder rules and current peer visibility."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.domains.agents.application.workboard_update import (
    execute_workboard_update,
    prepare_workboard_update,
)
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdateInput
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "holder_words",
        "holder_follow",
        "owner_recovery",
        "unconnected",
        "inactive",
        "gui_null",
        "native_null",
    ],
)
async def test_native_source_ownership_and_peer_prerequisites(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = User(id=uuid4(), email=f"mutation-owner-{uuid4()}@example.test", is_active=True)
    async_session.add(owner)
    await async_session.flush()
    owner_id, holder_id = owner.id, test_user.id
    if scenario not in {"unconnected"}:
        lo, hi = canonical_pair(owner_id, holder_id)
        async_session.add(
            PeerConnection(
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=owner_id,
                status=PeerConnectionStatus.ACCEPTED.value,
            )
        )
        await async_session.flush()
    ticket = await WorkboardService(async_session).create(
        owner,
        TicketCreate(
            title="Owner's literal words",
            assignee_user_id=None if scenario in {"unconnected", "inactive"} else holder_id,
        ),
    )
    identity = ticket.id
    if scenario == "inactive":
        test_user.is_active = False
    await async_session.commit()
    if scenario == "holder_words":
        with pytest.raises(ValidationError):
            await prepare_workboard_update(
                async_session,
                holder_id,
                WorkboardUpdateInput(ticket_id=identity, title="Unpermitted rewrite"),
            )
        await async_session.rollback()
        assert (
            await async_session.scalar(
                select(WorkboardTicket.title).where(WorkboardTicket.id == identity)
            )
            == "Owner's literal words"
        )
        return
    if scenario in {"unconnected", "inactive"}:
        with pytest.raises(ResourceNotFoundError):
            await prepare_workboard_update(
                async_session,
                owner_id,
                WorkboardUpdateInput(ticket_id=identity, assignee_user_id=holder_id),
            )
        return
    if scenario == "gui_null":
        from src.domains.workboard.schemas import TicketUpdate

        holder = await async_session.get(User, holder_id)
        await WorkboardService(async_session, assignment_notices=[]).update(
            holder, identity, TicketUpdate.model_validate({"assignee_user_id": None})
        )
        await async_session.commit()
        assert (
            await async_session.scalar(
                select(WorkboardTicket.assignee_user_id).where(WorkboardTicket.id == identity)
            )
            is None
        )
        return
    if scenario == "owner_recovery":
        monkeypatch.setattr(settings, "peers_enabled", False)
        actor_id = owner_id
        payload = WorkboardUpdateInput(ticket_id=identity, assignee="me")
    else:
        actor_id = holder_id
        payload = (
            WorkboardUpdateInput.model_validate({"ticket_id": identity, "assignee_user_id": None})
            if scenario == "native_null"
            else WorkboardUpdateInput(ticket_id=identity, follow=True)
        )
    monkeypatch.setattr(
        "src.domains.agents.application.workboard_update._notify_update", AsyncMock()
    )
    draft = await prepare_workboard_update(async_session, actor_id, payload)
    receipt = PreferenceWriteReceipt()
    await execute_workboard_update(async_session, actor_id, draft, receipt)
    assert receipt.committed
    actual = await async_session.get(WorkboardTicket, identity, populate_existing=True)
    if scenario in {"owner_recovery", "native_null"}:
        assert actual.assignee_user_id is None and actual.effective_assignee_id == owner_id
    else:
        assert actual.follow_assignee and not actual.follow_owner
