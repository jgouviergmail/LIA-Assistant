"""A ticket handed to a person from the ticket screen never waits for its own notice.

Measured in production on 2026-10-21: handing a ticket to a peer from the screen
hung for good, and every later write of the account queued behind it. The update
holds the accounts' ``users`` rows FOR UPDATE (the mutation fence, ADR-335) and
announced the handover inside that transaction; the announcement claims its act
in ``agent_effects`` on a connection of its own (ADR-263), whose foreign key needs
a share lock on the recipient's row — the request waited for a claim that waited
for the request, a cycle PostgreSQL cannot see. The notice now leaves after the
commit, as the chat's own path always did.

The claim is the REAL one, on its own connection: only the push is replaced.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import src.infrastructure.proactive.notification_sink  # noqa: F401 — installs the notifier
from src.core.config import settings
from src.domains.agents.effects.models import AgentEffect
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.models import User
from src.domains.workboard.router import update_ticket
from src.domains.workboard.schemas import TicketCreate, TicketUpdate
from src.domains.workboard.service import WorkboardService

pytestmark = pytest.mark.integration

#: Generous for a write that takes milliseconds; the defect waited for ever.
HANDOVER_BOUND_SECONDS = 20


async def _seed(engine: AsyncEngine, committed: list[UUID]) -> tuple[UUID, UUID, UUID]:
    owner_id, peer_id = uuid4(), uuid4()
    async with AsyncSession(engine, expire_on_commit=False) as seed:
        owner = User(id=owner_id, email=f"handover-owner-{owner_id}@example.test", is_active=True)
        peer = User(id=peer_id, email=f"handover-peer-{peer_id}@example.test", is_active=True)
        seed.add_all([owner, peer])
        await seed.flush()
        committed.extend([owner_id, peer_id])
        lo, hi = canonical_pair(owner_id, peer_id)
        seed.add(
            PeerConnection(
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=owner_id,
                status=PeerConnectionStatus.ACCEPTED.value,
            )
        )
        ticket = await WorkboardService(seed).create(owner, TicketCreate(title="Handover"))
        await seed.commit()
        return owner_id, peer_id, ticket.id


async def test_a_screen_handover_to_a_peer_commits_then_claims_its_notice(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "workboard_enabled", True)
    monkeypatch.setattr(settings, "peers_enabled", True)
    push = AsyncMock(return_value=SimpleNamespace(success=True))
    monkeypatch.setattr(
        "src.infrastructure.proactive.notification.NotificationDispatcher.dispatch", push
    )
    owner_id, peer_id, ticket_id = await _seed(async_engine, committed_user_ids)

    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        actor = await db.get(User, owner_id)
        assert actor is not None
        row = await asyncio.wait_for(
            update_ticket(ticket_id, TicketUpdate(assignee_user_id=peer_id), actor, db),
            timeout=HANDOVER_BOUND_SECONDS,
        )

    assert row.assignee_user_id == peer_id
    push.assert_awaited_once()
    async with AsyncSession(async_engine) as check:
        claimed = (
            (await check.execute(select(AgentEffect.id).where(AgentEffect.user_id == peer_id)))
            .scalars()
            .all()
        )
    # The peer's register holds the notice: claimed on its own connection,
    # once the handover had committed and released the accounts' rows.
    assert len(claimed) == 1
