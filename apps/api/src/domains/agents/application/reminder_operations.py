"""Reminder commands share source row locking and a final permission/expiry fence."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.reminder_create_schemas import ReminderRecurrence
from src.domains.agents.application.reminder_removal_schemas import ReminderSnapshot
from src.domains.agents.effects.digest import payload_digest
from src.domains.reminders.models import Reminder, ReminderStatus
from src.domains.reminders.service import ReminderService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt


def reminder_snapshot(row: Reminder) -> ReminderSnapshot:
    """Operational retries and private original wording do not become preview data."""
    public = ReminderSnapshot(
        id=row.id,
        content=row.content,
        trigger_at=row.trigger_at,
        user_timezone=row.user_timezone,
        recurrence=ReminderRecurrence.model_validate(row.recurrence_spec.model_dump(mode="json")),
        created_at=row.created_at,
        card_selection=None,
        configuration_digest="0" * 64,
    )
    return public.model_copy(
        update={
            "configuration_digest": payload_digest(
                public.model_dump(mode="json", exclude={"configuration_digest", "card_selection"})
            )
        }
    )


async def lock_reminder_for_command(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    expected: ReminderSnapshot,
) -> Reminder:
    await require_application_tools(db)
    actor: User | None = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    authorize_actor(actor)
    try:
        row = await ReminderService(db).get_by_id(expected.id, actor_id, for_update=True)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"}) from exc
    if row.status != ReminderStatus.PENDING.value or reminder_snapshot(row) != expected.model_copy(
        update={"card_selection": None}
    ):
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    return row


async def commit_reminder_change(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
    *,
    future_trigger_at: datetime | None = None,
) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    now = datetime.now(UTC)
    if now >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    if future_trigger_at is not None and future_trigger_at <= now:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
