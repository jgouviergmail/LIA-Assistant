"""Source detail reads share current visibility and optional paging/freshness boundaries."""

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.workboard.board_queries import visible_predicate
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent


async def count_visible(db: AsyncSession, ticket_ids: list[UUID], user_id: UUID) -> int:
    """Recheck a bounded observed page through the source visibility predicate."""
    if not ticket_ids:
        return 0
    return int(
        await db.scalar(
            select(func.count(WorkboardTicket.id)).where(
                WorkboardTicket.id.in_(ticket_ids), visible_predicate(user_id)
            )
        )
        or 0
    )


async def read_visible(db: AsyncSession, ticket_id: UUID, user_id: UUID) -> WorkboardTicket | None:
    """Observe current authority without trusting an already loaded row."""
    stmt = (
        select(WorkboardTicket)
        .where(WorkboardTicket.id == ticket_id, visible_predicate(user_id))
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _read_page[Row](
    db: AsyncSession, statement: Select[tuple[Row]], limit: int | None, offset: int
) -> list[Row]:
    if limit is not None:
        statement = statement.limit(limit).offset(offset)
    return list((await db.scalars(statement.execution_options(populate_existing=True))).all())


async def read_children(
    db: AsyncSession, ticket_id: UUID, *, limit: int | None, offset: int
) -> list[WorkboardTicket]:
    statement = (
        select(WorkboardTicket)
        .where(WorkboardTicket.parent_id == ticket_id)
        .order_by(WorkboardTicket.position.asc(), WorkboardTicket.id.asc())
    )
    return await _read_page(db, statement, limit, offset)


async def read_comments(
    db: AsyncSession, ticket_id: UUID, *, limit: int | None, offset: int
) -> list[WorkboardComment]:
    statement = (
        select(WorkboardComment)
        .where(WorkboardComment.ticket_id == ticket_id)
        .order_by(WorkboardComment.created_at.asc(), WorkboardComment.id.asc())
    )
    return await _read_page(db, statement, limit, offset)


async def read_events(
    db: AsyncSession, ticket_id: UUID, *, limit: int | None, offset: int
) -> list[WorkboardTicketEvent]:
    statement = (
        select(WorkboardTicketEvent)
        .where(WorkboardTicketEvent.ticket_id == ticket_id)
        .order_by(WorkboardTicketEvent.created_at.asc(), WorkboardTicketEvent.id.asc())
    )
    return await _read_page(db, statement, limit, offset)
