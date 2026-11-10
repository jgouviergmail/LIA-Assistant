"""Current membership authority shared by peer admission and final delivery."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.models import PeerConnectionStatus
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.repository import PeersRepository
from src.domains.users.models import User


async def lock_message_authority(
    db: AsyncSession, sender: UUID, connection_id: UUID, recipient: UUID
) -> tuple[User, User] | None:
    """Lock canonical parents, then pair; return two active accepted counterparts.

    The caller owns this SQL transaction and must commit before external I/O.
    A model-selected connection cannot confer membership or override a block.
    """
    await lock_peer_pair(db, sender, recipient)
    repo = PeersRepository(db)
    connection = await repo.get_by_id(connection_id, for_update=True)
    if (
        connection is None
        or connection.status != PeerConnectionStatus.ACCEPTED.value
        or {connection.user_a_id, connection.user_b_id} != {sender, recipient}
        or await repo.has_block_between(sender, recipient)
    ):
        return None
    people = {
        person.id: person
        for person in (
            await db.scalars(
                select(User).where(
                    User.id.in_([sender, recipient]),
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        ).all()
    }
    if len(people) != 2:
        return None
    return people[sender], people[recipient]
