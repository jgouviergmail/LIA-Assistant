"""One SQL snapshot joins only owned topics and returns complete count plus a bounded page."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Result, and_, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.core.exceptions import ResourceNotFoundError
from src.domains.interests.history_queries import interest_history_count_statement
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.schemas import InterestNotificationHistoryItem


@dataclass(frozen=True)
class InterestHistoryPage:
    rows: list[InterestNotificationHistoryItem]
    total: int


async def read_interest_history_page(
    db: AsyncSession, actor_id: UUID, *, limit: int, after_id: UUID | None
) -> InterestHistoryPage:
    anchor = aliased(InterestNotification)
    anchor_time = (
        select(anchor.created_at)
        .where(anchor.user_id == actor_id, anchor.id == after_id)
        .scalar_subquery()
    )
    selection = select(
        InterestNotification.id,
        InterestNotification.created_at,
        InterestNotification.content,
        InterestNotification.source,
        InterestNotification.interest_id,
        InterestNotification.user_feedback,
    ).where(InterestNotification.user_id == actor_id)
    if after_id is not None:
        selection = selection.where(
            tuple_(InterestNotification.created_at, InterestNotification.id)
            < tuple_(anchor_time, literal(after_id))
        )
    page = (
        selection.order_by(InterestNotification.created_at.desc(), InterestNotification.id.desc())
        .limit(limit + 1)
        .subquery()
    )
    metadata = select(
        interest_history_count_statement(actor_id).scalar_subquery().label("total")
    ).subquery()
    statement = (
        select(
            page.c.id,
            page.c.created_at,
            page.c.content,
            page.c.source,
            UserInterest.topic,
            page.c.user_feedback,
            metadata.c.total,
            anchor_time,
        )
        .select_from(metadata)
        .outerjoin(page, literal(True))
        .outerjoin(
            UserInterest,
            and_(UserInterest.id == page.c.interest_id, UserInterest.user_id == actor_id),
        )
        .order_by(page.c.created_at.desc(), page.c.id.desc())
    )
    result: Result[
        tuple[
            UUID | None,
            datetime | None,
            str | None,
            str | None,
            str | None,
            str | None,
            int,
            datetime | None,
        ]
    ] = await db.execute(statement)
    rows = result.all()
    if after_id is not None and rows[0][7] is None:
        raise ResourceNotFoundError("interest notification cursor", str(after_id))
    items = [
        InterestNotificationHistoryItem.model_validate(
            {
                "id": row[0],
                "created_at": row[1],
                "content": row[2],
                "source": row[3],
                "topic": row[4],
                "user_feedback": row[5],
            }
        )
        for row in rows
        if row[0] is not None
    ]
    return InterestHistoryPage(rows=items, total=rows[0][6])
