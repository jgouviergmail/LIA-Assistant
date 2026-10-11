"""GUI and native creation share account/pair/parent locks before checking their caps."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.schemas import TicketCreate


async def lock_creation_scope(db: AsyncSession, actor_id: UUID, request: TicketCreate) -> None:
    peer_id = request.assignee_user_id or actor_id
    await lock_peer_pair(db, actor_id, peer_id)
    if peer_id != actor_id:
        lo, hi = canonical_pair(actor_id, peer_id)
        await db.execute(
            select(PeerConnection.id)
            .where(PeerConnection.user_a_id == lo, PeerConnection.user_b_id == hi)
            .with_for_update()
        )
    if request.parent_id is not None:
        await db.execute(
            select(WorkboardTicket.id)
            .where(
                WorkboardTicket.id == request.parent_id, WorkboardTicket.owner_user_id == actor_id
            )
            .with_for_update()
        )
