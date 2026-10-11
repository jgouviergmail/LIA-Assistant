"""Confirmed reset binds complete PostgreSQL state and reports Redis partial failure honestly."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.habit_forget_schemas import HabitForgetPatch, HabitForgetRequest
from src.domains.agents.application.habit_queries import require_habit_records
from src.domains.agents.application.habit_settings import habit_settings_fence
from src.domains.agents.application.habit_spec import HABIT_FORGET_OPERATION
from src.domains.habits.forget_snapshot import habit_forget_snapshot
from src.domains.habits.forgetting import forget_habit_data
from src.domains.habits.management_commands import HabitCompletionUnknown
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_habit_forgetting(
    db: AsyncSession, actor_id: UUID, request: HabitForgetRequest, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    HabitForgetRequest.model_validate(request.model_dump())
    await require_habit_records(db, actor_id)
    snapshot = await habit_forget_snapshot(db, actor_id)
    await require_habit_records(db, actor_id)
    return build_action_content(
        actor_id,
        HABIT_FORGET_OPERATION,
        HabitForgetPatch(habit_data=snapshot),
        {"habit_data": snapshot.public_counts()},
        {"habit_data": None},
        command_id=command_id,
    )


def canonical_habit_forgetting(draft: ApplicationActionDraftContent) -> bool:
    expected = HabitForgetPatch.model_validate(draft.intent).habit_data
    return draft.before == {"habit_data": expected.public_counts()} and draft.after == {
        "habit_data": None
    }


async def execute_habit_forgetting(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_habit_forgetting(draft):
        raise ValueError("Forgetting requires the exact confirmed complete source scope")
    expected = HabitForgetPatch.model_validate(draft.intent).habit_data
    await habit_settings_fence(db, actor_id, draft)

    async def check() -> None:
        await habit_settings_fence(db, actor_id, draft)

    try:
        result = await forget_habit_data(
            db, actor_id, expected=expected, receipt=receipt, check=check
        )
    except HabitCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    if not result.advisory_cleanup_confirmed:
        raise CommandRejected("ADVISORY_CLEANUP_FAILED")
