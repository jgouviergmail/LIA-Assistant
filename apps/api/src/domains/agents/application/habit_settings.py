"""An exact confirmation changes only the current owner's future learning preference."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.habit_queries import require_habit_records
from src.domains.agents.application.habit_settings_schemas import HabitSettingsPatch
from src.domains.agents.application.habit_spec import HABIT_SETTINGS_OPERATION
from src.domains.habits.preference_commands import (
    HabitSettingsCompletionUnknown,
    update_habit_settings,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_habit_settings(
    db: AsyncSession, actor_id: UUID, patch: HabitSettingsPatch, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = HabitSettingsPatch.model_validate(patch.model_dump(exclude_unset=True))
    actor = await require_habit_records(db, actor_id)
    before = {name: getattr(actor, name) for name in desired.model_fields_set}
    HabitSettingsPatch.model_validate(before)
    await require_habit_records(db, actor_id)
    return build_action_content(
        actor_id,
        HABIT_SETTINGS_OPERATION,
        desired,
        before,
        desired.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def habit_settings_fence(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await require_habit_records(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_habit_settings(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = HabitSettingsPatch.model_validate(draft.intent)
    HabitSettingsPatch.model_validate(draft.before)
    if draft.intent != draft.after or set(draft.before) != desired.model_fields_set:
        raise ValueError("Habit settings require the exact confirmed before/after scope")
    await habit_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await habit_settings_fence(db, actor_id, draft)

    try:
        await update_habit_settings(
            db, actor_id, desired, expected=draft.before, receipt=receipt, check=check
        )
    except HabitSettingsCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
