"""Source habit management uses mandatory exact human approval and fresh ownership."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.habit_action_schemas import (
    HabitDeletePatch,
    HabitDeleteRequest,
    HabitStatusChange,
    HabitStatusPatch,
    HabitStatusRequest,
    HabitStatusValues,
    canonical_habit,
    habit_after,
    habit_command,
)
from src.domains.agents.application.habit_queries import require_habit_records
from src.domains.agents.application.habit_settings import habit_settings_fence
from src.domains.agents.application.habit_spec import HABIT_DELETE_OPERATION, HABIT_STATUS_OPERATION
from src.domains.habits.management_commands import (
    HabitCompletionUnknown,
    change_managed_habit,
    managed_habit,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_habit_action(
    db: AsyncSession,
    actor_id: UUID,
    request: HabitStatusRequest | HabitDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    request = type(request).model_validate(request.model_dump(mode="json"))
    await require_habit_records(db, actor_id)
    expected = await managed_habit(db, actor_id, request.habit_id)
    change = (
        HabitStatusChange(status=request.status)
        if isinstance(request, HabitStatusRequest)
        else None
    )
    intent = (
        HabitStatusPatch(habit=HabitStatusValues(expected=expected, status=change))
        if change is not None
        else HabitDeletePatch(habit=expected)
    )
    await require_habit_records(db, actor_id)
    return build_action_content(
        actor_id,
        HABIT_STATUS_OPERATION if change is not None else HABIT_DELETE_OPERATION,
        intent,
        {"habit": expected.model_dump(mode="json")},
        habit_after(expected, change),
        command_id=command_id,
    )


async def execute_habit_action(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_habit(draft):
        raise ValueError("Habit management requires the exact confirmed source transition")
    expected, change = habit_command(draft)
    await habit_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await habit_settings_fence(db, actor_id, draft)

    try:
        await change_managed_habit(
            db, actor_id, expected.id, change, expected=expected, receipt=receipt, check=check
        )
    except HabitCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
