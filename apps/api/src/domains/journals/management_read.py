"""One SQL observation binds the public page and full filtered journal count."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.exceptions import ResourceNotFoundError
from src.domains.journals.models import JournalEntry, JournalEntryStatus, JournalTheme
from src.domains.journals.schemas import JournalEntryResponse


@dataclass(frozen=True)
class JournalPage:
    rows: list[JournalEntryResponse]
    total: int


def _context_filters(
    query: str | None,
    entry_id: UUID | None,
    recorded_start: datetime | None,
    recorded_end: datetime | None,
) -> list[ColumnElement[bool]]:
    """Additive owner filters; default management pages keep their exact scope."""
    filters: list[ColumnElement[bool]] = []
    if query is not None:
        filters.append(
            or_(
                JournalEntry.title.icontains(query, autoescape=True),
                JournalEntry.content.icontains(query, autoescape=True),
            )
        )
    if entry_id is not None:
        filters.append(JournalEntry.id == entry_id)
    if recorded_start is not None:
        filters.append(JournalEntry.created_at >= recorded_start)
    if recorded_end is not None:
        filters.append(JournalEntry.created_at < recorded_end)
    return filters


async def read_journal_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    theme: JournalTheme | None,
    status: JournalEntryStatus | None,
    limit: int,
    after_id: UUID | None,
    query: str | None = None,
    entry_id: UUID | None = None,
    recorded_start: datetime | None = None,
    recorded_end: datetime | None = None,
) -> JournalPage:
    fields = tuple(JournalEntryResponse.model_fields)
    filters = [JournalEntry.user_id == actor_id]
    if theme is not None:
        filters.append(JournalEntry.theme == theme.value)
    if status is not None:
        filters.append(JournalEntry.status == status.value)
    filters.extend(_context_filters(query, entry_id, recorded_start, recorded_end))
    anchor = (
        select(JournalEntry.created_at)
        .where(*filters, JournalEntry.id == after_id)
        .scalar_subquery()
    )
    selection = select(*(getattr(JournalEntry, name) for name in fields)).where(*filters)
    if after_id is not None:
        selection = selection.where(
            tuple_(JournalEntry.created_at, JournalEntry.id) < tuple_(anchor, literal(after_id))
        )
    page = (
        selection.order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc())
        .limit(limit + 1)
        .subquery()
    )
    metadata = select(
        select(func.count())
        .select_from(JournalEntry)
        .where(*filters)
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
        raise ResourceNotFoundError("journal cursor", after_id)
    return JournalPage(
        rows=[
            JournalEntryResponse.model_validate({field: row[field] for field in fields})
            for row in rows
            if row["id"] is not None
        ],
        total=rows[0]["total"],
    )
