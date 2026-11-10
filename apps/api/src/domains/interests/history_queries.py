"""The source audit count has one query authority for the UI and native snapshots."""

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.schemas import InterestNotificationHistoryItem
from src.domains.shared.display_queries import display_name_key, read_display_page
from src.domains.shared.display_query import DisplayQuery


def interest_history_count_statement(user_id: UUID) -> Select[tuple[int]]:
    return (
        select(func.count())
        .select_from(InterestNotification)
        .where(InterestNotification.user_id == user_id)
    )


class InterestHistoryRepository(BaseRepository[InterestNotification]):
    """Thin history projection, with topics joined only inside their owner's scope."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, InterestNotification)

    async def page(
        self,
        user_id: UUID,
        *,
        limit: int,
        offset: int,
        criteria: DisplayQuery,
    ) -> tuple[list[InterestNotificationHistoryItem], int]:
        """Read a filtered page and its exact total from the same owned statement.

        Args:
            user_id: Authenticated reader.
            limit: Page size.
            offset: Matching rows to skip.
            criteria: Display fragment, ordering and upper creation instant.

        Returns:
            Thin display rows and the exact matching total.
        """
        statement = (
            select(
                InterestNotification.id,
                InterestNotification.created_at,
                InterestNotification.content,
                InterestNotification.source,
                InterestNotification.user_feedback,
                UserInterest.topic,
            )
            .outerjoin(
                UserInterest,
                (UserInterest.id == InterestNotification.interest_id)
                & (UserInterest.user_id == user_id),
            )
            .where(InterestNotification.user_id == user_id)
        )
        if criteria.as_of is not None:
            statement = statement.where(InterestNotification.created_at <= criteria.as_of)
        direction = (
            InterestNotification.created_at.asc()
            if criteria.sort == "oldest"
            else InterestNotification.created_at.desc()
        )
        return await read_display_page(
            self.db,
            statement.order_by(direction, InterestNotification.id.asc()),
            decode=lambda row: InterestNotificationHistoryItem.model_validate(row._mapping),
            query=criteria.q,
            text_of=lambda row: (row.topic, row.content),
            limit=limit,
            offset=offset,
            name_key=(
                (lambda row: display_name_key(row.topic, row.id))
                if criteria.sort == "name"
                else None
            ),
        )
