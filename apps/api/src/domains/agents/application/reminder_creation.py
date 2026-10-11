"""Exact reminder confirmation cannot silently move its approved first occurrence."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.reminder_create_schemas import (
    ReminderCreatePatch,
    ReminderCreateRequest,
    ReminderCreationValues,
    ReminderRecurrence,
)
from src.domains.agents.application.reminder_spec import REMINDER_CREATE_OPERATION
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import ReminderService, resolve_reminder_creation
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_reminder_creation(
    db: AsyncSession,
    actor_id: UUID,
    request: ReminderCreateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = ReminderCreateRequest.model_validate(request.model_dump(mode="json"))
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    timezone = actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
    arming = resolve_reminder_creation(validated, timezone)
    if arming.trigger_at <= datetime.now(UTC):
        raise ValueError("A new reminder requires a future first occurrence")
    identity = command_id or uuid4()
    patch = ReminderCreatePatch(
        reminder_to_create=ReminderCreationValues(
            id=identity,
            user_timezone=timezone,
            trigger_at=arming.trigger_at,
            recurrence=ReminderRecurrence.model_validate(arming.recurrence.model_dump(mode="json")),
            configuration=validated,
        )
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        REMINDER_CREATE_OPERATION,
        patch,
        {"reminder_to_create": None},
        patch.model_dump(mode="json", exclude_unset=True),
        command_id=identity,
    )


async def execute_reminder_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    proposal = ReminderCreatePatch.model_validate(draft.intent).reminder_to_create
    if proposal.id != draft.command_id or draft.before != {"reminder_to_create": None}:
        raise ValueError("Creation must retain its confirmed identity")
    await require_application_tools(db)
    actor: User | None = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    current = authorize_actor(actor)
    if (current.timezone or DEFAULT_USER_DISPLAY_TIMEZONE) != proposal.user_timezone:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    source_data = ReminderCreate.model_validate(proposal.configuration.model_dump(mode="json"))
    arming = resolve_reminder_creation(source_data, proposal.user_timezone)
    if arming.trigger_at != proposal.trigger_at or arming.trigger_at <= datetime.now(UTC):
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    await _require_current_creation(db, actor_id, draft, proposal)
    created = await ReminderService(db).create_reminder(
        actor_id,
        source_data,
        proposal.user_timezone,
        reminder_id=proposal.id,
    )
    if created.trigger_at != proposal.trigger_at or created.recurrence_spec.model_dump(
        mode="json"
    ) != proposal.recurrence.model_dump(mode="json"):
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    await _require_current_creation(db, actor_id, draft, proposal)
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True


async def _require_current_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    proposal: ReminderCreationValues,
) -> None:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if (actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE) != proposal.user_timezone:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    now = datetime.now(UTC)
    if now >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    if proposal.trigger_at <= now:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
