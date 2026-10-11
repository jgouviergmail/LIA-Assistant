"""Bounded public history and complete filtered count come from one SQL observation."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.exceptions import ResourceNotFoundError
from src.domains.psyche.models import PsycheHistory
from src.domains.psyche.schemas import PsycheHistoryEntry


def psyche_history_filters(
    actor_id: UUID, snapshot_type: str | None, cutoff: datetime | None
) -> tuple[ColumnElement[bool], ...]:
    filters: tuple[ColumnElement[bool], ...] = (PsycheHistory.user_id == actor_id,)
    if snapshot_type:
        filters = (*filters, PsycheHistory.snapshot_type == snapshot_type)
    if cutoff is not None:
        filters = (*filters, PsycheHistory.created_at >= cutoff)
    return filters


@dataclass(frozen=True)
class PsycheHistoryPage:
    rows: list[PsycheHistoryEntry]
    total: int


async def read_psyche_history_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    limit: int,
    after_id: UUID | None,
    snapshot_type: str | None,
    cutoff: datetime | None,
    as_of: datetime,
) -> PsycheHistoryPage:
    fields = tuple(PsycheHistoryEntry.model_fields)
    filtered = (
        *psyche_history_filters(actor_id, snapshot_type, cutoff),
        PsycheHistory.created_at <= as_of,
    )
    anchor = (
        select(PsycheHistory.created_at)
        .where(*filtered, PsycheHistory.id == after_id)
        .scalar_subquery()
    )
    selection = select(*(getattr(PsycheHistory, name) for name in fields)).where(*filtered)
    if after_id is not None:
        selection = selection.where(
            tuple_(PsycheHistory.created_at, PsycheHistory.id) < tuple_(anchor, literal(after_id))
        )
    page = (
        selection.order_by(PsycheHistory.created_at.desc(), PsycheHistory.id.desc())
        .limit(limit + 1)
        .subquery()
    )
    metadata = select(
        select(func.count())
        .select_from(PsycheHistory)
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
        raise ResourceNotFoundError("psyche history cursor", after_id)
    items = [
        PsycheHistoryEntry.model_validate({field: row[field] for field in fields})
        for row in rows
        if row["id"] is not None
    ]
    return PsycheHistoryPage(rows=items, total=rows[0]["total"])
