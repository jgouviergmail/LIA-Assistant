"""Fresh bilateral peer visibility for autonomous personal-context reads."""

from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, func, or_, select

from src.domains.peers.constants import PEER_UNKNOWN_DISPLAY_NAME
from src.domains.peers.models import PeerBlock, PeerConnection, PeerConnectionStatus
from src.domains.users.models import User


def counterpart(owner: UUID) -> ColumnElement[UUID]:
    """Return the SQL expression naming the other account of a connection.

    Args:
        owner: The account reading.

    Returns:
        The connection's other user id.
    """
    return case(
        (PeerConnection.user_a_id == owner, PeerConnection.user_b_id),
        else_=PeerConnection.user_a_id,
    )


def readable_connection(owner: UUID) -> ColumnElement[bool]:
    """Return the condition of a connection the owner may read now, from both sides.

    Accepted, unblocked in either direction, and with an active, named counterpart.

    Args:
        owner: The account reading.

    Returns:
        The condition, joined to the counterpart's user row.
    """
    peer = counterpart(owner)
    blocked = (
        select(PeerBlock.id)
        .where(
            or_(
                and_(PeerBlock.blocker_id == owner, PeerBlock.blocked_id == peer),
                and_(PeerBlock.blocker_id == peer, PeerBlock.blocked_id == owner),
            )
        )
        .correlate(PeerConnection)
    )
    return and_(
        or_(PeerConnection.user_a_id == owner, PeerConnection.user_b_id == owner),
        PeerConnection.status == PeerConnectionStatus.ACCEPTED.value,
        ~blocked.exists(),
        User.is_active.is_(True),
        User.deleted_at.is_(None),
        func.btrim(User.full_name) != "",
        func.btrim(User.full_name) != PEER_UNKNOWN_DISPLAY_NAME,
    )
