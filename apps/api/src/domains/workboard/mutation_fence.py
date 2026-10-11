"""All source mutations serialize account, affected peer pairs and visible ticket in one order."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_not_found_or_unauthorized
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.users.models import User
from src.domains.workboard.board_queries import visible_predicate
from src.domains.workboard.models import WorkboardTicket


async def lock_mutation_ticket(
    db: AsyncSession, actor_id: UUID, ticket_id: UUID, prospective_holder: UUID | None = None
) -> WorkboardTicket:
    current = (
        await db.execute(
            select(WorkboardTicket.owner_user_id, WorkboardTicket.assignee_user_id).where(
                WorkboardTicket.id == ticket_id, visible_predicate(actor_id)
            )
        )
    ).one_or_none()
    if current is None:
        raise_not_found_or_unauthorized("ticket", ticket_id)
    owner, holder = current
    identities = (
        {owner, actor_id}
        | ({holder} if holder else set())
        | ({prospective_holder} if prospective_holder else set())
    )
    await db.execute(
        select(User.id).where(User.id.in_(identities)).order_by(User.id).with_for_update()
    )
    pairs = sorted(
        {canonical_pair(owner, identity) for identity in identities if identity != owner}
    )
    for lo, hi in pairs:
        await db.execute(
            select(PeerConnection.id)
            .where(PeerConnection.user_a_id == lo, PeerConnection.user_b_id == hi)
            .with_for_update()
        )
    ticket = await db.scalar(
        select(WorkboardTicket)
        .where(WorkboardTicket.id == ticket_id, visible_predicate(actor_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if ticket is None or ticket.owner_user_id != owner or ticket.assignee_user_id != holder:
        raise_not_found_or_unauthorized("ticket", ticket_id)
    return ticket
