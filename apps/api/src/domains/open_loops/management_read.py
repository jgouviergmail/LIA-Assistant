"""One source snapshot supplies a bounded page and complete owned commitment count."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.open_loops.schemas import OpenLoopResponse


@dataclass(frozen=True)
class OpenLoopPage:
    rows: list[OpenLoopResponse]
    total: int


async def read_open_loop_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    status: OpenLoopStatus | None,
    limit: int,
    after_id: UUID | None,
) -> OpenLoopPage:
    fields = tuple(OpenLoopResponse.model_fields)
    owned = (OpenLoop.user_id == actor_id,)
    filtered = (*owned, OpenLoop.status == status.value) if status is not None else owned
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
