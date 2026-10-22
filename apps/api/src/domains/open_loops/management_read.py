"""One source snapshot supplies a bounded page and complete owned commitment count."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.exceptions import ResourceNotFoundError
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.open_loops.schemas import OpenLoopResponse


@dataclass(frozen=True)
class OpenLoopPage:
    rows: list[OpenLoopResponse]
    total: int


def _context_filters(
    query: str | None,
    loop_id: UUID | None,
    start: datetime | None,
    end: datetime | None,
    future: bool,
) -> list[ColumnElement[bool]]:
    result: list[ColumnElement[bool]] = []
    if query is not None:
        result.append(
            or_(
                OpenLoop.subject.icontains(query, autoescape=True),
                OpenLoop.counterparty.icontains(query, autoescape=True),
            )
        )
    if loop_id is not None:
        result.append(OpenLoop.id == loop_id)
    column = OpenLoop.due_hint if future else OpenLoop.created_at
    if start is not None:
        result.append(column >= start)
    if end is not None:
        result.append(column < end)
    return result


async def read_open_loop_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    status: OpenLoopStatus | None,
    limit: int,
    after_id: UUID | None,
    query: str | None = None,
    loop_id: UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    future: bool = False,
) -> OpenLoopPage:
    fields = tuple(OpenLoopResponse.model_fields)
    owned = (OpenLoop.user_id == actor_id,)
    filtered = (*owned, OpenLoop.status == status.value) if status is not None else owned
    filtered = (*filtered, *_context_filters(query, loop_id, start, end, future))
    anchor = select(OpenLoop.created_at).where(*owned, OpenLoop.id == after_id).scalar_subquery()
    selection = select(*(getattr(OpenLoop, name) for name in fields)).where(*filtered)
    if after_id is not None:
        selection = selection.where(
            tuple_(OpenLoop.created_at, OpenLoop.id) < tuple_(anchor, literal(after_id))
        )
    page = (
        selection.order_by(OpenLoop.created_at.desc(), OpenLoop.id.desc())
        .limit(limit + 1)
        .subquery()
    )
    metadata = select(
        select(func.count())
        .select_from(OpenLoop)
        .where(*filtered)
        .scalar_subquery()
        .label("total"),
        anchor.label("anchor_time"),
    ).subquery()
    statement = (
        select(*page.c, metadata.c.total, metadata.c.anchor_time)
        .select_from(metadata)
        .outerjoin(page, literal(True))
        .order_by(page.c.created_at.desc(), page.c.id.desc())
    )
    rows = (await db.execute(statement)).mappings().all()
    if after_id is not None and rows[0]["anchor_time"] is None:
        raise ResourceNotFoundError("commitment cursor", str(after_id))
    items = [
        OpenLoopResponse.model_validate({field: row[field] for field in fields})
        for row in rows
        if row["id"] is not None
    ]
    return OpenLoopPage(rows=items, total=rows[0]["total"])
