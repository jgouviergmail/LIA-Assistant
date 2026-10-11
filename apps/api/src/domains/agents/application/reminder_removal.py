"""Remove only the exact pending reminder approved through native HITL."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.reminder_card_selection import (
    capture_reminder_selection,
    reminder_card_scope,
)
from src.domains.agents.application.reminder_operations import (
    commit_reminder_change,
    lock_reminder_for_command,
    reminder_snapshot,
)
from src.domains.agents.application.reminder_removal_schemas import (
    ReminderDeletePatch,
    ReminderDeleteRequest,
)
from src.domains.agents.application.reminder_spec import REMINDER_DELETE_OPERATION
from src.domains.reminders.models import ReminderStatus
from src.domains.reminders.service import ReminderService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_reminder_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: ReminderDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = ReminderDeleteRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await ReminderService(db).get_by_id(validated.reminder_id, actor_id)
    if row.status != ReminderStatus.PENDING.value:
        raise ResourceConflictError("reminder", reason="reminder_not_pending")
    snapshot = reminder_snapshot(row).model_copy(
        update={"card_selection": capture_reminder_selection(actor_id, row.id)}
    )
    patch = ReminderDeletePatch(reminder_to_delete=snapshot)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        REMINDER_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"reminder_to_delete": None},
        command_id=command_id,
    )


async def execute_reminder_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    proposal = ReminderDeletePatch.model_validate(draft.intent)
    if proposal.model_dump(mode="json") != draft.before or draft.after != {
        "reminder_to_delete": None
    }:
        raise ValueError("Deletion must retain the confirmed selection")
    async with reminder_card_scope(
        actor_id, proposal.reminder_to_delete.id, proposal.reminder_to_delete.card_selection
    ):
        row = await lock_reminder_for_command(db, actor_id, draft, proposal.reminder_to_delete)
        await ReminderService(db).cancel_reminder(row.id, actor_id)
        await commit_reminder_change(db, actor_id, draft, receipt)
