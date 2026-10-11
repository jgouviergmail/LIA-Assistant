"""Owned source shares change only after exact approval, preserving the reverse direction."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_share import execute_peer_share, prepare_peer_share
from src.domains.agents.application.peer_share_schemas import PeerShareInput
from src.domains.peers.models import PeerConnection, PeerDomainShare, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["grant", "revoke", "no_op", "stale", "other_direction"])
async def test_share_exact_owned_scope(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(id=uuid4(), email=f"share-{uuid4()}@example.com", full_name="Alice", is_active=True)
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(owner, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peer.id,
        status="accepted",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.flush()
    identity = pair.id
    theirs = PeerDomainShare(
        connection_id=identity, owner_user_id=peer.id, domain="calendar", level="details"
    )
    async_session.add(theirs)
    if scenario != "grant":
        async_session.add(
            PeerDomainShare(
                connection_id=identity, owner_user_id=owner, domain="calendar", level="availability"
            )
        )
    await async_session.commit()
    target = None if scenario == "revoke" else "availability"
    draft = await prepare_peer_share(
        async_session,
        owner,
        PeerShareInput(connection_id=identity, domain="calendar", level=target),
    )
    assert draft.before["peer_share"]["level"] == (None if scenario == "grant" else "availability")
    if scenario in {"stale", "other_direction"}:
        await async_session.execute(
            update(PeerDomainShare)
            .where(
                PeerDomainShare.connection_id == identity,
                PeerDomainShare.owner_user_id == (owner if scenario == "stale" else peer.id),
            )
            .values(level="details" if scenario == "stale" else "availability")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario == "stale":
        with pytest.raises(ResourceConflictError):
            await execute_peer_share(async_session, owner, draft, receipt)
        assert not receipt.committed
    else:
        await execute_peer_share(async_session, owner, draft, receipt)
        assert receipt.committed and receipt.no_op == (scenario in {"no_op", "other_direction"})
    rows = (
        await async_session.execute(
            select(PeerDomainShare.owner_user_id, PeerDomainShare.level).where(
                PeerDomainShare.connection_id == identity
            )
        )
    ).all()
    actual = dict(rows)
    assert actual[peer.id] == ("availability" if scenario == "other_direction" else "details")
    assert actual.get(owner) == ("details" if scenario == "stale" else target)


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
    ],
)
async def test_share_authority_and_ack(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(
        id=uuid4(), email=f"share-ack-{uuid4()}@example.com", full_name="Alice", is_active=True
    )
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(owner, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peer.id,
        status="accepted",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.commit()
    identity = pair.id
    draft = await prepare_peer_share(
        async_session, owner, PeerShareInput(connection_id=identity, domain="task", level="titles")
    )
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "peers_off":
        monkeypatch.setattr(settings, "peers_enabled", False)
    if scenario in {"false_source", "late_off"}:
        from src.domains.peers.service import PeersService

        source = PeersService.set_share

        async def withdraw(service, *args):
            await source(service, *args)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(
            PeersService,
            "set_share",
            AsyncMock(return_value=None) if scenario == "false_source" else withdraw,
        )
    if scenario.endswith("lost_ack"):
        commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await commit()
            raise OperationalError("commit", {}, RuntimeError("Lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    expected = {
        "expired": CommandRejected,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
        "false_source": ValueError,
    }.get(scenario, AuthorizationError)
    with pytest.raises(expected):
        await execute_peer_share(async_session, owner, draft, receipt)
    assert not receipt.committed
    await async_session.rollback()
    actual = await async_session.scalar(
        select(PeerDomainShare.level).where(
            PeerDomainShare.connection_id == identity, PeerDomainShare.owner_user_id == owner
        )
    )
    assert actual == ("titles" if scenario == "committed_lost_ack" else None)
