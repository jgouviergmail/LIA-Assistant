"""Directional blocks sever source sharing silently; lifting one restores no connection."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_block import execute_peer_block, prepare_peer_block
from src.domains.agents.application.peer_block_schemas import PeerBlockInput
from src.domains.peers.models import PeerBlock, PeerConnection, PeerDomainShare, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["block", "pending", "unblock", "already_blocked", "stale"])
async def test_directional_block_exact_scope(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(id=uuid4(), email=f"block-{uuid4()}@example.com", full_name="Alice", is_active=True)
    async_session.add(peer)
    await async_session.flush()
    peer_id = peer.id
    lo, hi = canonical_pair(owner, peer_id)
    initial = (
        "removed"
        if scenario in {"unblock", "already_blocked"}
        else "pending" if scenario == "pending" else "accepted"
    )
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peer_id,
        status=initial,
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.flush()
    identity = pair.id
    if scenario in {"unblock", "already_blocked"}:
        async_session.add(PeerBlock(blocker_id=owner, blocked_id=peer_id))
    else:
        async_session.add_all(
            [
                PeerDomainShare(
                    connection_id=identity,
                    owner_user_id=value,
                    domain="calendar",
                    level="availability",
                )
                for value in (lo, hi)
            ]
        )
    await async_session.commit()
    draft = await prepare_peer_block(
        async_session, owner, PeerBlockInput(peer_id=peer_id, blocked=scenario != "unblock")
    )
    assert (
        await async_session.scalar(
            select(PeerConnection.status).where(PeerConnection.id == identity)
        )
        == initial
    )
    if scenario == "stale":
        await async_session.execute(
            update(PeerDomainShare)
            .where(
                PeerDomainShare.connection_id == identity, PeerDomainShare.owner_user_id == peer_id
            )
            .values(level="details")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario == "stale":
        with pytest.raises(ResourceConflictError):
            await execute_peer_block(async_session, owner, draft, receipt)
        assert not receipt.committed
        return
    await execute_peer_block(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.no_op == (scenario == "already_blocked")
    assert bool(
        await async_session.scalar(
            select(PeerBlock.id).where(
                PeerBlock.blocker_id == owner, PeerBlock.blocked_id == peer_id
            )
        )
    ) == (scenario != "unblock")
    assert (
        await async_session.scalar(
            select(PeerConnection.status).where(PeerConnection.id == identity)
        )
        == "removed"
    )
    assert not (
        await async_session.execute(
            select(PeerDomainShare.id).where(PeerDomainShare.connection_id == identity)
        )
    ).all()


@pytest.mark.parametrize(
    "scenario",
    [
        "expired",
        "native_off",
        "peers_off",
        "late_off",
        "lost_ack",
        "committed_lost_ack",
        "false_source",
        "restore_on_unblock",
        "restore_grant_on_unblock",
        "unknown_peer",
        "other_block",
    ],
)
async def test_block_authority_and_degraded_boundaries(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(
        id=uuid4(),
        email=f"block-boundary-{uuid4()}@example.com",
        full_name="Private identity",
        is_active=True,
        discovery_enabled=True,
    )
    async_session.add(peer)
    await async_session.flush()
    peer_id = peer.id
    lo, hi = canonical_pair(owner, peer_id)
    removed = scenario in {"restore_on_unblock", "restore_grant_on_unblock", "other_block"}
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peer_id,
        status="removed" if removed else "accepted",
        requested_at=datetime.now(UTC),
    )
    if scenario != "unknown_peer":
        async_session.add(pair)
        await async_session.flush()
    identity = pair.id
    if removed:
        async_session.add(PeerBlock(blocker_id=owner, blocked_id=peer_id))
    if scenario == "other_block":
        async_session.add(PeerBlock(blocker_id=peer_id, blocked_id=owner))
    await async_session.commit()
    request = PeerBlockInput(peer_id=peer_id, blocked=not removed)
    if scenario == "unknown_peer":
        with pytest.raises(ResourceNotFoundError):
            await prepare_peer_block(async_session, owner, request)
        assert await async_session.scalar(select(PeerBlock.id)) is None
        return
    draft = await prepare_peer_block(async_session, owner, request)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "peers_off":
        monkeypatch.setattr(settings, "peers_enabled", False)
    if scenario in {"late_off", "false_source", "restore_on_unblock", "restore_grant_on_unblock"}:
        from src.domains.peers.service import PeersService

        source = PeersService.unblock_peer if removed else PeersService.block_peer

        async def mutate(service, *args):
            result = await source(service, *args)
            if scenario == "restore_on_unblock":
                await service.db.execute(
                    update(PeerConnection)
                    .where(PeerConnection.id == identity)
                    .values(status="accepted")
                    .execution_options(synchronize_session=False)
                )
            elif scenario == "restore_grant_on_unblock":
                service.db.add(
                    PeerDomainShare(
                        connection_id=identity,
                        owner_user_id=owner,
                        domain="calendar",
                        level="details",
                    )
                )
                await service.db.flush()
            else:
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        monkeypatch.setattr(
            PeersService,
            "unblock_peer" if removed else "block_peer",
            AsyncMock(return_value=None) if scenario == "false_source" else mutate,
        )
    if scenario.endswith("lost_ack"):
        commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await commit()
            raise OperationalError("commit", {}, RuntimeError("Lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario == "other_block":
        await execute_peer_block(async_session, owner, draft, receipt)
        assert receipt.committed
        assert (
            await async_session.scalar(
                select(PeerBlock.id).where(
                    PeerBlock.blocker_id == peer_id, PeerBlock.blocked_id == owner
                )
            )
            is not None
        )
        assert (
            await async_session.scalar(
                select(PeerBlock.id).where(
                    PeerBlock.blocker_id == owner, PeerBlock.blocked_id == peer_id
                )
            )
            is None
        )
        return
    expected = {
        "expired": CommandRejected,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
        "false_source": ValueError,
        "restore_on_unblock": ValueError,
        "restore_grant_on_unblock": ValueError,
    }.get(scenario, AuthorizationError)
    with pytest.raises(expected):
        await execute_peer_block(async_session, owner, draft, receipt)
    assert not receipt.committed
    await async_session.rollback()
    actual = await async_session.scalar(
        select(PeerBlock.id).where(PeerBlock.blocker_id == owner, PeerBlock.blocked_id == peer_id)
    )
    assert (actual is not None) == (
        scenario in {"committed_lost_ack", "restore_on_unblock", "restore_grant_on_unblock"}
    )
    assert await async_session.scalar(
        select(PeerConnection.status).where(PeerConnection.id == identity)
    ) == ("removed" if removed or scenario == "committed_lost_ack" else "accepted")
