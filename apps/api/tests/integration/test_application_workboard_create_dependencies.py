"""Parent and peer identity remain source-owned prerequisites of an approved creation."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceConflictError
from src.domains.agents.application.workboard_create import (
    execute_workboard_creation,
    prepare_workboard_creation,
)
from src.domains.agents.application.workboard_create_schemas import WorkboardCreateInput
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import TicketCreate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "peer",
        "parent",
        "stale_parent",
        "removed_pair",
        "peers_off",
        "inactive_peer",
        "foreign_parent",
    ],
)
async def test_creation_dependency_scope(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "workboard_enabled", True)
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(
        id=uuid4(),
        email=f"create-dependency-{uuid4()}@example.com",
        full_name="Alice",
        is_active=True,
    )
    async_session.add(peer)
    await async_session.flush()
    peer_id = peer.id
    lo, hi = canonical_pair(owner, peer_id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=owner,
        status="accepted",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.flush()
    pair_id = pair.id
    parent_id = None
    if scenario in {"parent", "stale_parent", "foreign_parent"}:
        parent = await WorkboardService(async_session).create(
            peer if scenario == "foreign_parent" else test_user, TicketCreate(title="Parent")
        )
        parent_id = parent.id
    await async_session.commit()
    initial_count = await async_session.scalar(select(func.count(WorkboardTicket.id)))
    request = WorkboardCreateInput(
        title="Approved child or peer ticket",
        parent_id=parent_id,
        assignee_user_id=peer_id if parent_id is None else None,
    )
    if scenario == "foreign_parent":
        with pytest.raises(BaseAPIException):
            await prepare_workboard_creation(async_session, owner, request)
        return
    draft = await prepare_workboard_creation(async_session, owner, request)
    if scenario == "stale_parent":
        await async_session.execute(
            update(WorkboardTicket)
            .where(WorkboardTicket.id == parent_id)
            .values(title="Changed parent")
            .execution_options(synchronize_session=False)
        )
    if scenario == "removed_pair":
        await async_session.execute(
            update(PeerConnection)
            .where(PeerConnection.id == pair_id)
            .values(status="removed")
            .execution_options(synchronize_session=False)
        )
    if scenario == "inactive_peer":
        await async_session.execute(
            update(User)
            .where(User.id == peer_id)
            .values(is_active=False)
            .execution_options(synchronize_session=False)
        )
    await async_session.commit()
    if scenario == "peers_off":
        monkeypatch.setattr(settings, "peers_enabled", False)
    receipt = PreferenceWriteReceipt()
    if scenario in {"peer", "parent"}:
        await execute_workboard_creation(async_session, owner, draft, receipt)
        assert receipt.committed
        created = await async_session.get(WorkboardTicket, draft.command_id)
        assert created.parent_id == parent_id
        assert created.assignee_user_id == (peer_id if scenario == "peer" else None)
    else:
        with pytest.raises((BaseAPIException, ResourceConflictError)):
            await execute_workboard_creation(async_session, owner, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    assert await async_session.scalar(
        select(func.count(WorkboardTicket.id))
    ) == initial_count + int(receipt.committed)
