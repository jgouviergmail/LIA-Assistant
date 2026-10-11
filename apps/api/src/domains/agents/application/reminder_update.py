"""Reminder edits freeze the complete source result and its first armed clock."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.reminder_operations import (
    commit_reminder_change,
    lock_reminder_for_command,
    reminder_snapshot,
)
from src.domains.agents.application.reminder_spec import REMINDER_UPDATE_OPERATION
from src.domains.agents.application.reminder_update_schemas import (
    ReminderConfigurationValues,
    ReminderUpdatePatch,
    ReminderUpdateRequest,
    ReminderUpdateValues,
)
from src.domains.reminders.models import ReminderStatus
from src.domains.reminders.schemas import ReminderUpdate
from src.domains.reminders.service import ReminderService, preview_reminder_update
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_reminder_update(
    db: AsyncSession,
    actor_id: UUID,
    request: ReminderUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = ReminderUpdateRequest.model_validate(
        request.model_dump(mode="json", exclude_unset=True)
    )
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    timezone = actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
    row = await ReminderService(db).get_by_id(validated.reminder_id, actor_id)
    if row.status != ReminderStatus.PENDING.value:
        raise ResourceConflictError("reminder", reason="reminder_not_pending")
    changes = ReminderUpdate.model_validate(
        validated.changes.model_dump(mode="json", exclude_unset=True)
    )
    previous = ReminderUpdateValues(
        expected=reminder_snapshot(row),
        requested_timezone=timezone,
        changes=validated.changes,
        configuration=ReminderConfigurationValues.of(
            preview_reminder_update(row, ReminderUpdate(), timezone)
        ),
    )
    configuration = ReminderConfigurationValues.of(preview_reminder_update(row, changes, timezone))
    if validated.changes.changes_schedule and configuration.trigger_at <= datetime.now(UTC):
        raise ValueError("A changed reminder schedule requires a future first occurrence")
    desired = previous.model_copy(update={"configuration": configuration})
    before, after = ReminderUpdatePatch(reminder_configuration=previous), ReminderUpdatePatch(
        reminder_configuration=desired
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        REMINDER_UPDATE_OPERATION,
        after,
        before.model_dump(mode="json", exclude_unset=True),
        after.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def execute_reminder_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = ReminderUpdatePatch.model_validate(draft.intent).reminder_configuration
    previous = ReminderUpdatePatch.model_validate(draft.before).reminder_configuration
    if (
        desired.expected != previous.expected
        or desired.changes != previous.changes
        or desired.requested_timezone != previous.requested_timezone
    ):
        raise ValueError("A reminder edit cannot replace its confirmed comparison data")
    row = await lock_reminder_for_command(db, actor_id, draft, previous.expected)
    actor = await load_actor(db, actor_id)
    if (actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE) != desired.requested_timezone:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    changes = ReminderUpdate.model_validate(
        desired.changes.model_dump(mode="json", exclude_unset=True)
    )
    actual = ReminderConfigurationValues.of(
        preview_reminder_update(row, changes, desired.requested_timezone)
    )
    unchanged = ReminderConfigurationValues.of(
        preview_reminder_update(row, ReminderUpdate(), desired.requested_timezone)
    )
    if unchanged != previous.configuration or actual != desired.configuration:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    if desired.changes.changes_schedule and actual.trigger_at <= datetime.now(UTC):
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    if previous.configuration == desired.configuration:
        receipt.committed, receipt.no_op = True, True
        return
    updated = await ReminderService(db).update_reminder(
        row.id, actor_id, changes, desired.requested_timezone
    )
    written = ReminderConfigurationValues.of(
        preview_reminder_update(updated, ReminderUpdate(), desired.requested_timezone)
    )
    if written != desired.configuration:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"})
    await commit_reminder_change(
        db,
        actor_id,
        draft,
        receipt,
        future_trigger_at=(
            desired.configuration.trigger_at if desired.changes.changes_schedule else None
        ),
    )
