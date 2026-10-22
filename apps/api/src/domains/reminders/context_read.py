"""Bounded pending intentions and their exact filtered count in one SQL snapshot."""

from dataclasses import dataclass
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.core.recurrence import RecurrenceSpec
from src.domains.reminders.models import Reminder
from src.domains.reminders.queries import pending_reminders


class ReminderContextItem(BaseModel):
    """One pending reminder: its intention, recurrence, next firing and clock."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    content: str
    recurrence: RecurrenceSpec
    trigger_at: AwareDatetime
    user_timezone: str
    created_at: AwareDatetime


@dataclass(frozen=True)
class ReminderContextPage:
    """One page of pending reminders and the exact total of the selection."""

    items: tuple[ReminderContextItem, ...]
    total: int


async def read_context_page(
    db: AsyncSession,
    owner: UUID,
    *,
    start: AwareDatetime,
    end: AwareDatetime,
    limit: int,
    after_id: UUID | None,
    reminder_id: UUID | None,
    query: str | None,
) -> ReminderContextPage:
    """Read one page of an owner's pending reminders firing in a window.

    Args:
        db: The session to read with.
        owner: The account.
        start: The window's start.
        end: The window's end.
        limit: The page size; one more row reveals a next page.
        after_id: The last reminder of the previous page.
        reminder_id: One reminder to read, for a detail read.
        query: Words the intention must contain, if any.

    Returns:
        The page and its total.

    Raises:
        ResourceNotFoundError: The cursor's reminder is no longer pending.
    """
    fields = tuple(ReminderContextItem.model_fields)
    selection = (
        pending_reminders(owner)
        .with_only_columns(*(getattr(Reminder, field) for field in fields))
        .where(Reminder.trigger_at >= start, Reminder.trigger_at < end)
    )
    if reminder_id is not None:
        selection = selection.where(Reminder.id == reminder_id)
    if query is not None:
        selection = selection.where(Reminder.content.icontains(query, autoescape=True))
    source = selection.cte("context_reminders")
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
        raise ResourceNotFoundError("reminder context cursor", after_id)
    return ReminderContextPage(
        total=rows[0]["total"],
        items=tuple(
            ReminderContextItem.model_validate({field: row[field] for field in fields})
            for row in rows
            if row["id"] is not None
        ),
    )
