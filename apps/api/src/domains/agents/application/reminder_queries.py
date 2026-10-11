"""Reuse the source management projection with stable owned pagination."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.i18n import normalize_language
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.reminder_read_schemas import ReminderProjection, ReminderRead
from src.domains.reminders.models import ReminderStatus
from src.domains.reminders.read_models import ReminderDetail
from src.domains.reminders.service import ReminderService


async def read_reminders(
    db: AsyncSession, actor_id: UUID, request: ReminderRead
) -> ReminderProjection:
    selected = ReminderRead.model_validate(request.model_dump())
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    source = ReminderService(db)
    if selected.reminder_id is not None:
        row = await source.get_by_id(selected.reminder_id, actor_id)
        if row.status != ReminderStatus.PENDING.value:
            raise ResourceConflictError("reminder", reason="reminder_not_pending")
        page, total = [row], 1
    else:
        page = await source.repository.page_pending_by_id(
            actor_id, after_id=selected.after_id, limit=selected.limit
        )
        total = await source.repository.count_pending_for_user(actor_id)
    has_more = len(page) > selected.limit
    rows = page[: selected.limit]
    result = ReminderProjection(
        reminders=[ReminderDetail.of(row, normalize_language(actor.language)) for row in rows],
        returned_count=len(rows),
        total_available=total,
        truncated=has_more,
        next_cursor=rows[-1].id if has_more else None,
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return result
