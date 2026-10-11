"""Invitation preparation is inert and crossing acceptance is explicitly approved."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_request import execute_peer_request, prepare_peer_request
from src.domains.agents.application.peer_request_schemas import PeerRequestInput
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["new", "crossing", "outgoing", "stale"])
async def test_peer_request_exact_source_state_and_crossing_outcome(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    notify = AsyncMock(return_value=None)
    monkeypatch.setattr("src.domains.agents.application.peer_request.dispatch_peer_events", notify)
    owner = test_user.id
    peer = User(
        id=uuid4(),
        email=f"invite-{uuid4()}@example.com",
        hashed_password="controlled",
        full_name="Alice",
        discovery_enabled=True,
        is_active=True,
    )
    async_session.add(peer)
    await async_session.flush()
    if scenario in {"crossing", "outgoing"}:
        lo, hi = canonical_pair(owner, peer.id)
        async_session.add(
            PeerConnection(
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=peer.id if scenario == "crossing" else owner,
                status="pending",
                requested_at=datetime.now(UTC),
            )
        )
    await async_session.commit()
    draft = await prepare_peer_request(
        async_session, owner, PeerRequestInput(peer_id=peer.id, context_message="Bonjour")
    )
    assert draft.after["peer_request"]["status"] == (
        "accepted" if scenario == "crossing" else "pending"
    )
    if scenario in {"new", "stale"}:
        assert await async_session.scalar(select(PeerConnection.id)) is None
    if scenario == "stale":
        lo, hi = canonical_pair(owner, peer.id)
        async_session.add(
            PeerConnection(
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=peer.id,
                status="pending",
                requested_at=datetime.now(UTC),
            )
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario == "stale":
        with pytest.raises(ResourceConflictError):
            await execute_peer_request(async_session, owner, draft, receipt)
        assert not receipt.committed
    else:
        await execute_peer_request(async_session, owner, draft, receipt)
        assert receipt.committed and receipt.no_op == (scenario == "outgoing")
    row = await async_session.scalar(select(PeerConnection))
    assert row is not None and row.status == ("accepted" if scenario == "crossing" else "pending")
    assert notify.await_count == int(scenario in {"new", "crossing"})


@pytest.mark.parametrize(
    "scenario",
    [
        "expired",
        "target_off",
        "late_off",
        "lost_ack",
        "committed_lost_ack",
        "notification_failure",
        "renamed",
        "already_accepted",
        "false_source",
    ],
)
async def test_invitation_authority_and_ack_before_notifications(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(
        id=uuid4(),
        email=f"boundary-{uuid4()}@example.com",
        full_name="Alice",
        discovery_enabled=True,
        is_active=True,
    )
    async_session.add(peer)
    await async_session.commit()
    draft = await prepare_peer_request(
        async_session, owner, PeerRequestInput(peer_id=peer.id, context_message="Bonjour")
    )
    notify = AsyncMock(
        side_effect=(
            RuntimeError("Controlled failure") if scenario == "notification_failure" else None
        )
    )
    monkeypatch.setattr("src.domains.agents.application.peer_request.dispatch_peer_events", notify)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "target_off":
        await async_session.execute(
            update(User)
            .where(User.id == peer.id)
            .values(discovery_enabled=False)
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    if scenario == "renamed":
        await async_session.execute(
            update(User)
            .where(User.id == peer.id)
            .values(full_name="Alice renamed")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    if scenario == "already_accepted":
        lo, hi = canonical_pair(owner, peer.id)
        async_session.add(
            PeerConnection(
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=peer.id,
                status="accepted",
                requested_at=datetime.now(UTC),
            )
        )
        await async_session.commit()
    if scenario == "false_source":
        from src.domains.peers.schemas import ConnectionStateView
        from src.domains.peers.service import PeersService

        monkeypatch.setattr(
            PeersService,
            "request_connection",
            AsyncMock(return_value=ConnectionStateView(id=uuid4(), status="pending")),
        )
    if scenario == "late_off":
        from src.domains.peers.service import PeersService

        source = PeersService.request_connection

        async def withdraw(service, *args, **kwargs):
            result = await source(service, *args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(PeersService, "request_connection", withdraw)
    if scenario.endswith("lost_ack"):
        commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await commit()
            raise OperationalError("commit", {}, RuntimeError("Lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario == "notification_failure":
        await execute_peer_request(async_session, owner, draft, receipt)
        assert (
            receipt.committed and receipt.values["peer_request"]["notification_status"] == "failed"
        )
        notify.assert_awaited_once()
    else:
        expected_error = {
            "late_off": AuthorizationError,
            "renamed": ResourceConflictError,
            "already_accepted": ResourceConflictError,
            "false_source": ValueError,
        }.get(scenario, CommandRejected)
        with pytest.raises(expected_error):
            await execute_peer_request(async_session, owner, draft, receipt)
        assert not receipt.committed
        notify.assert_not_awaited()
        await async_session.rollback()
    assert (await async_session.scalar(select(PeerConnection.id)) is not None) == (
        scenario in {"committed_lost_ack", "notification_failure", "already_accepted"}
    )
