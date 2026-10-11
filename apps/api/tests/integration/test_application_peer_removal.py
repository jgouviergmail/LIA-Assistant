"""Severance approves a selected pair and both share directions, never private peer work."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

import src.domains.workboard.release_adapter  # noqa: F401 — real source release seam
from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_removal import execute_peer_removal, prepare_peer_removal
from src.domains.agents.application.peer_removal_schemas import PeerRemovalInput
from src.domains.peers.models import PeerConnection, PeerDomainShare, canonical_pair
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workboard.models import WorkboardTicket
from tests.integration.domains.workboard.test_peer_lifecycle_db import _ticket

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["remove", "work_added", "stale_share", "stale_pair", "pending", "foreign"]
)
async def test_severance_exact_scope_and_source_release(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peers = [
        User(id=uuid4(), email=f"remove-{uuid4()}@example.com", full_name="Alice", is_active=True)
        for _ in range(2)
    ]
    async_session.add_all(peers)
    await async_session.flush()
    lo, hi = canonical_pair(peers[1].id if scenario == "foreign" else owner, peers[0].id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peers[0].id,
        status="pending" if scenario == "pending" else "accepted",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.flush()
    identity = pair.id
    async_session.add_all(
        [
            PeerDomainShare(
                connection_id=identity, owner_user_id=value, domain="calendar", level="availability"
            )
            for value in (lo, hi)
        ]
    )
    tickets = [
        _ticket(test_user, peers[0], "Owner shared work"),
        _ticket(peers[0], test_user, "Private peer work"),
        _ticket(test_user, None, "Owner unshared work"),
    ]
    if scenario != "foreign":
        async_session.add_all(tickets)
    await async_session.commit()
    notify = AsyncMock(return_value=None)
    monkeypatch.setattr("src.domains.agents.application.peer_removal.dispatch_peer_events", notify)
    if scenario in {"pending", "foreign"}:
        with pytest.raises(ResourceNotFoundError):
            await prepare_peer_removal(
                async_session, owner, PeerRemovalInput(connection_id=identity)
            )
        notify.assert_not_awaited()
        return
    draft = await prepare_peer_removal(
        async_session, owner, PeerRemovalInput(connection_id=identity)
    )
    assert "Private peer work" not in str(draft.model_dump())
    assert (
        await async_session.scalar(
            select(PeerConnection.status).where(PeerConnection.id == identity)
        )
        == "accepted"
    )
    notify.assert_not_awaited()
    if scenario == "work_added":
        async_session.add(_ticket(test_user, peers[0], "New shared work under approved policy"))
        await async_session.commit()
    if scenario == "stale_share":
        await async_session.execute(
            update(PeerDomainShare)
            .where(
                PeerDomainShare.connection_id == identity,
                PeerDomainShare.owner_user_id == peers[0].id,
            )
            .values(level="details")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    if scenario == "stale_pair":
        await async_session.execute(
            update(PeerConnection)
            .where(PeerConnection.id == identity)
            .values(status="removed")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    if scenario.startswith("stale"):
        with pytest.raises(ResourceConflictError):
            await execute_peer_removal(async_session, owner, draft, receipt)
        assert not receipt.committed
        notify.assert_not_awaited()
        return
    await execute_peer_removal(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.values["peer_removal"]["own_tickets_released"] == (
        2 if scenario == "work_added" else 1
    )
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
    held = (await async_session.execute(select(WorkboardTicket.assignee_user_id))).scalars().all()
    assert held == [None] * (4 if scenario == "work_added" else 3)
    notify.assert_awaited_once()


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
        "notification_sql_failure",
        "release_failure",
        "false_source",
        "remaining_share",
    ],
)
async def test_severance_degraded_boundaries(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(
        id=uuid4(), email=f"remove-ack-{uuid4()}@example.com", full_name="Alice", is_active=True
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
    await async_session.flush()
    identity = pair.id
    async_session.add(
        PeerDomainShare(
            connection_id=identity, owner_user_id=owner, domain="calendar", level="details"
        )
    )
    ticket = _ticket(test_user, peer, "Controlled shared work")
    async_session.add(ticket)
    await async_session.commit()
    ticket_id = ticket.id
    peer_id = peer.id
    draft = await prepare_peer_removal(
        async_session, owner, PeerRemovalInput(connection_id=identity)
    )
    notify = AsyncMock(
        side_effect=RuntimeError("Controlled") if scenario == "notification_failure" else None
    )
    if scenario == "notification_sql_failure":
        from sqlalchemy import text

        async def fail_notification(events, db):
            await db.execute(text("SELECT 1 / 0"))

        notify = AsyncMock(side_effect=fail_notification)
    monkeypatch.setattr("src.domains.agents.application.peer_removal.dispatch_peer_events", notify)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "peers_off":
        monkeypatch.setattr(settings, "peers_enabled", False)
    if scenario in {"late_off", "false_source", "remaining_share"}:
        from src.domains.peers.schemas import ConnectionStateView
        from src.domains.peers.service import PeersService

        source = PeersService.remove_connection

        async def change(service, *args):
            if scenario == "false_source":
                return ConnectionStateView(id=identity, status="removed")
            result = await source(service, *args)
            if scenario == "remaining_share":
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

        monkeypatch.setattr(PeersService, "remove_connection", change)
    if scenario == "release_failure":
        from src.domains.workboard.service import WorkboardService

        source = WorkboardService.release_pair

        async def fail_release(service, *args):
            await source(service, *args)
            raise RuntimeError("Controlled release failure")

        monkeypatch.setattr(WorkboardService, "release_pair", fail_release)
    if scenario.endswith("lost_ack"):
        commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await commit()
            raise OperationalError("commit", {}, RuntimeError("Lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario in {"notification_failure", "notification_sql_failure", "release_failure"}:
        await execute_peer_removal(async_session, owner, draft, receipt)
        assert receipt.committed
        assert receipt.values["peer_removal"]["notification_status"] == (
            "attempted" if scenario == "release_failure" else "failed"
        )
        if scenario == "release_failure":
            assert receipt.values["peer_removal"]["own_tickets_released"] is None
        notify.assert_awaited_once()
    else:
        expected = {
            "expired": CommandRejected,
            "lost_ack": CommandRejected,
            "committed_lost_ack": CommandRejected,
            "false_source": ValueError,
            "remaining_share": ValueError,
        }.get(scenario, AuthorizationError)
        with pytest.raises(expected):
            await execute_peer_removal(async_session, owner, draft, receipt)
        assert not receipt.committed
        notify.assert_not_awaited()
        await async_session.rollback()
    saved = scenario in {
        "committed_lost_ack",
        "notification_failure",
        "notification_sql_failure",
        "release_failure",
    }
    assert await async_session.scalar(
        select(PeerConnection.status).where(PeerConnection.id == identity)
    ) == ("removed" if saved else "accepted")
    assert bool(
        await async_session.scalar(
            select(PeerDomainShare.id).where(PeerDomainShare.connection_id == identity)
        )
    ) == (not saved)
    holder = await async_session.scalar(
        select(WorkboardTicket.assignee_user_id).where(WorkboardTicket.id == ticket_id)
    )
    assert holder == (None if saved and scenario != "release_failure" else peer_id)
