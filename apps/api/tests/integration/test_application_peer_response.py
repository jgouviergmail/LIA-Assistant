"""Only an incoming request's addressee can approve an exact source response."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_response import (
    execute_peer_response,
    prepare_peer_response,
)
from src.domains.agents.application.peer_response_schemas import PeerResponseInput
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["accept", "decline", "own_request", "stale"])
async def test_response_source_ownership_and_exact_state(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(
        id=uuid4(), email=f"response-{uuid4()}@example.com", full_name="Alice", is_active=True
    )
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(owner, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=owner if scenario == "own_request" else peer.id,
        status="pending",
        context_message="Incoming note",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.commit()
    notice = AsyncMock(return_value=None)
    monkeypatch.setattr("src.domains.agents.application.peer_response.dispatch_peer_events", notice)
    request = PeerResponseInput(connection_id=pair.id, accept=scenario != "decline")
    if scenario == "own_request":
        with pytest.raises(AuthorizationError):
            await prepare_peer_response(async_session, owner, request)
        notice.assert_not_awaited()
        return
    draft = await prepare_peer_response(async_session, owner, request)
    assert pair.status == "pending"
    notice.assert_not_awaited()
    if scenario == "stale":
        await async_session.execute(
            update(PeerConnection)
            .where(PeerConnection.id == pair.id)
            .values(context_message="Changed request")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario == "stale":
        with pytest.raises(ResourceConflictError):
            await execute_peer_response(async_session, owner, draft, receipt)
        assert not receipt.committed
        notice.assert_not_awaited()
    else:
        await execute_peer_response(async_session, owner, draft, receipt)
        assert receipt.committed
        await async_session.refresh(pair)
        assert pair.status == ("accepted" if scenario == "accept" else "declined")
        notice.assert_awaited_once()


@pytest.mark.parametrize(
    "scenario",
    [
        "expired",
        "native_off",
        "peers_off",
        "late_off",
        "lost_ack",
        "committed_lost_ack",
        "notification_failure",
        "already_declined",
        "false_source",
        "foreign_request",
    ],
)
async def test_response_authority_and_commit_boundary(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peers = [
        User(
            id=uuid4(),
            email=f"response-boundary-{uuid4()}@example.com",
            full_name="Alice",
            is_active=True,
        )
        for _ in range(2)
    ]
    async_session.add_all(peers)
    await async_session.flush()
    lo, hi = canonical_pair(peers[1].id if scenario == "foreign_request" else owner, peers[0].id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peers[0].id,
        status="pending",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.commit()
    identity = pair.id
    request = PeerResponseInput(connection_id=identity, accept=True)
    notice = AsyncMock(
        side_effect=RuntimeError("Controlled") if scenario == "notification_failure" else None
    )
    monkeypatch.setattr("src.domains.agents.application.peer_response.dispatch_peer_events", notice)
    if scenario == "foreign_request":
        from src.core.exceptions import ResourceNotFoundError

        with pytest.raises(ResourceNotFoundError):
            await prepare_peer_response(async_session, owner, request)
        notice.assert_not_awaited()
        return
    draft = await prepare_peer_response(async_session, owner, request)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "peers_off":
        monkeypatch.setattr(settings, "peers_enabled", False)
    if scenario == "already_declined":
        await async_session.execute(
            update(PeerConnection)
            .where(PeerConnection.id == identity)
            .values(status="declined")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    if scenario in {"late_off", "false_source"}:
        from src.domains.peers.schemas import ConnectionStateView
        from src.domains.peers.service import PeersService

        source = PeersService.respond_request

        async def change(service, *args, **kwargs):
            if scenario == "false_source":
                return ConnectionStateView(id=identity, status="accepted")
            result = await source(service, *args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(PeersService, "respond_request", change)
    if scenario.endswith("lost_ack"):
        commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await commit()
            raise OperationalError("commit", {}, RuntimeError("Lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario == "notification_failure":
        await execute_peer_response(async_session, owner, draft, receipt)
        assert (
            receipt.committed and receipt.values["peer_response"]["notification_status"] == "failed"
        )
        notice.assert_awaited_once()
    else:
        expected = {
            "expired": CommandRejected,
            "lost_ack": CommandRejected,
            "committed_lost_ack": CommandRejected,
            "already_declined": ResourceConflictError,
            "false_source": ValueError,
        }.get(scenario, AuthorizationError)
        with pytest.raises(expected):
            await execute_peer_response(async_session, owner, draft, receipt)
        assert not receipt.committed
        notice.assert_not_awaited()
        await async_session.rollback()
    actual = await async_session.scalar(
        select(PeerConnection.status).where(PeerConnection.id == identity)
    )
    assert actual == (
        "accepted"
        if scenario in {"committed_lost_ack", "notification_failure"}
        else "declined" if scenario == "already_declined" else "pending"
    )
