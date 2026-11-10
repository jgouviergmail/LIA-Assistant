"""Delivered peer history: one visibility rule and only the reader's own words."""

from uuid import UUID

from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.peers.constants import (
    PEER_MESSAGE_DIRECTION_RECEIVED,
    PEER_MESSAGE_DIRECTION_SENT,
    PEER_UNKNOWN_DISPLAY_NAME,
)
from src.domains.peers.models import PeerBlock, PeerMessage, PeerMessageStatus
from src.domains.peers.schemas import RelayedMessageItem
from src.domains.shared.display_queries import display_name_key, read_display_page
from src.domains.shared.display_query import DisplayQuery
from src.domains.users.models import User


def delivered_with_peer(
    user_id: UUID,
) -> tuple[ColumnElement[UUID], tuple[ColumnElement[bool], ...]]:
    """Shared visibility for counts, relationship activity and hub pages.

    Args:
        user_id: The reader; the User table must join the returned counterpart.

    Returns:
        Counterpart identity and complete owner/delivery/block/name predicates.
    """
    counterpart = case(
        (PeerMessage.sender_id == user_id, PeerMessage.recipient_id),
        else_=PeerMessage.sender_id,
    )
    blocked = select(PeerBlock.blocked_id).where(PeerBlock.blocker_id == user_id)
    return counterpart, (
        or_(PeerMessage.sender_id == user_id, PeerMessage.recipient_id == user_id),
        PeerMessage.status == PeerMessageStatus.DELIVERED.value,
        PeerMessage.delivered_at.is_not(None),
        counterpart.not_in(blocked),
        func.btrim(User.full_name) != "",
        func.btrim(User.full_name) != PEER_UNKNOWN_DISPLAY_NAME,
    )


class PeerHistoryRepository(BaseRepository[PeerMessage]):
    """Display-only relay reader; no delivery or provider work occurs here."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, PeerMessage)

    async def page(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
        criteria: DisplayQuery,
    ) -> tuple[list[RelayedMessageItem], int]:
        """Filter before pagination without exposing the other participant's text.

        Args:
            user_id: Authenticated reader.
            limit: Page size.
            offset: Matching rows to skip.
            criteria: Literal fragment, ordering and upper delivery instant.

        Returns:
            The page and its exact matching total from one statement.
        """
        counterpart, predicates = delivered_with_peer(user_id)
        sent = PeerMessage.sender_id == user_id
        statement = (
            select(
                PeerMessage.id,
                func.btrim(User.full_name).label("peer_display_name"),
                case(
                    (sent, PEER_MESSAGE_DIRECTION_SENT), else_=PEER_MESSAGE_DIRECTION_RECEIVED
                ).label("direction"),
                case((sent, PeerMessage.content), else_=PeerMessage.delivered_text).label(
                    "content"
                ),
                PeerMessage.delivered_at.label("occurred_at"),
            )
            .join(User, User.id == counterpart)
            .where(*predicates)
        )
        if criteria.as_of is not None:
            statement = statement.where(PeerMessage.delivered_at <= criteria.as_of)
        direction = (
            PeerMessage.delivered_at.asc()
            if criteria.sort == "oldest"
            else PeerMessage.delivered_at.desc()
        )
        return await read_display_page(
            self.db,
            statement.order_by(direction, PeerMessage.id.asc()),
            decode=lambda row: RelayedMessageItem.model_validate(
                {**row._mapping, "id": str(row.id)}
            ),
            query=criteria.q,
            text_of=lambda row: (row.peer_display_name, row.content),
            limit=limit,
            offset=offset,
            name_key=(
                (lambda row: display_name_key(row.peer_display_name, row.id))
                if criteria.sort == "name"
                else None
            ),
        )
