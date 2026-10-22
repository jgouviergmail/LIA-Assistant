"""A bounded projection of current ready minutes, using the owner's native text search."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.core.meeting_reports import MeetingReport
from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.search import minutes_search_predicate, normalize_minutes_query


class MeetingContextItem(BaseModel):
    """One meeting with ready minutes: its start, record date and current report."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    started_at: AwareDatetime
    created_at: AwareDatetime
    report: MeetingReport


@dataclass(frozen=True)
class MeetingContextPage:
    """One page of meetings with ready minutes and the exact total of the selection."""

    items: tuple[MeetingContextItem, ...]
    total: int


async def read_context_page(
    db: AsyncSession,
    owner: UUID,
    *,
    start: datetime,
    end: datetime,
    limit: int,
    after_id: UUID | None,
    meeting_id: UUID | None,
    query: str | None,
) -> MeetingContextPage:
    """Read one page of an owner's ready minutes in a window, optionally searched.

    Args:
        db: The session to read with.
        owner: The account.
        start: The window's start.
        end: The window's end.
        limit: The page size; one more row reveals a next page.
        after_id: The last meeting of the previous page.
        meeting_id: One meeting to read, for a detail read.
        query: Words to search the minutes for, if any.

    Returns:
        The page and its total.

    Raises:
        ResourceNotFoundError: The cursor's meeting no longer qualifies.
    """
    selection = select(
        Meeting.id, Meeting.started_at, Meeting.created_at, Meeting.report_current.label("report")
    ).where(
        Meeting.user_id == owner,
        Meeting.status == MeetingStatus.READY,
        Meeting.report_current.is_not(None),
        Meeting.started_at >= start,
        Meeting.started_at < end,
    )
    if meeting_id is not None:
        selection = selection.where(Meeting.id == meeting_id)
    needle = normalize_minutes_query((query or "").strip())
    if needle:
        selection = selection.where(minutes_search_predicate(needle, include_location=False))
    source = selection.cte("context_minutes")
    page_select = select(source)
    if after_id is not None:
        page_select = page_select.where(source.c.id > after_id)
    page = page_select.order_by(source.c.id).limit(limit + 1).subquery()
    metadata = select(
        select(func.count()).select_from(source).scalar_subquery().label("total"),
        select(source.c.id).where(source.c.id == after_id).scalar_subquery().label("anchor"),
    ).subquery()
    rows = (
        (
            await db.execute(
                select(*page.c, metadata.c.total, metadata.c.anchor)
                .select_from(metadata)
                .outerjoin(page, literal(True))
                .order_by(page.c.id)
            )
        )
        .mappings()
        .all()
    )
    if after_id is not None and rows[0]["anchor"] is None:
        raise ResourceNotFoundError("minutes context cursor", after_id)
    fields = tuple(MeetingContextItem.model_fields)
    return MeetingContextPage(
        total=rows[0]["total"],
        items=tuple(
            MeetingContextItem.model_validate({field: row[field] for field in fields})
            for row in rows
            if row["id"] is not None
        ),
    )
