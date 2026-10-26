"""Bounded accepted-person directory for private consumers, without address/shares."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.constants import PEER_UNKNOWN_DISPLAY_NAME
from src.domains.peers.models import PeerBlock, PeerConnection, PeerConnectionStatus
from src.domains.peers.schemas import PeerConnectionProfile
from src.domains.users.models import User


@dataclass(frozen=True)
class ConnectedPeoplePage:
    items: tuple[PeerConnectionProfile, ...]
    next_cursor: UUID | None


async def page_connected_people(
    db: AsyncSession, owner: UUID, *, after: UUID | None, limit: int = 12
) -> ConnectedPeoplePage:
    if not 1 <= limit <= 12:
        raise ValueError("connected_people_page_limit")
    peer = case(
        (PeerConnection.user_a_id == owner, PeerConnection.user_b_id),
        else_=PeerConnection.user_a_id,
    )
    blocked = exists().where(
        or_(
            and_(PeerBlock.blocker_id == owner, PeerBlock.blocked_id == User.id),
            and_(PeerBlock.blocked_id == owner, PeerBlock.blocker_id == User.id),
        )
    )
    query = (
        select(PeerConnection.id, PeerConnection.responded_at, User.id, User.full_name)
        .join(User, User.id == peer)
        .where(
            PeerConnection.status == PeerConnectionStatus.ACCEPTED.value,
            or_(PeerConnection.user_a_id == owner, PeerConnection.user_b_id == owner),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            func.length(func.trim(User.full_name)) > 0,
            func.trim(User.full_name) != PEER_UNKNOWN_DISPLAY_NAME,
            ~blocked,
        )
        .order_by(PeerConnection.id.desc())
        .limit(limit + 1)
    )
    if after is not None:
        query = query.where(PeerConnection.id < after)
    rows = (await db.execute(query)).all()
    items = tuple(
        PeerConnectionProfile(
            connection_id=connection_id,
            peer_id=peer_id,
            peer_display_name=name.strip(),
            connected_since=responded_at,
        )
        for connection_id, responded_at, peer_id, name in rows[:limit]
    )
    return ConnectedPeoplePage(items, items[-1].connection_id if len(rows) > limit else None)
