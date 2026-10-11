"""Manual current-account recomputation is always behind exact HITL and live act gates."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.habit_queries import require_habit_records
from src.domains.agents.application.habit_recompute_schemas import (
    HabitRecomputePatch,
    HabitRecomputeRequest,
    HabitRecomputeScope,
)
from src.domains.agents.application.habit_settings import habit_settings_fence
from src.domains.agents.application.habit_spec import HABIT_RECOMPUTE_OPERATION
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.habits.management_commands import HabitCompletionUnknown
from src.domains.habits.recompute_commands import recompute_managed_habits
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def recompute_scope(db: AsyncSession, actor_id: UUID) -> HabitRecomputeScope:
    actor = await require_habit_records(db, actor_id)
    await require_capability_fresh(db, PlatformCapability.HABITS)
    return HabitRecomputeScope(
        timezone=str(resolve_user_timezone(actor)), habits_enabled=actor.habits_enabled
    )


async def prepare_habit_recompute(
    db: AsyncSession,
    actor_id: UUID,
    request: HabitRecomputeRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    HabitRecomputeRequest.model_validate(request.model_dump())
    scope = await recompute_scope(db, actor_id)
    return build_action_content(
        actor_id,
        HABIT_RECOMPUTE_OPERATION,
        HabitRecomputePatch(habit_recompute=scope),
        {"habit_recompute": scope.model_dump(mode="json")},
        {"habit_recompute": {**scope.model_dump(mode="json"), "requested": True}},
        command_id=command_id,
    )


def canonical_habit_recompute(draft: ApplicationActionDraftContent) -> bool:
    scope = HabitRecomputePatch.model_validate(draft.intent).habit_recompute.model_dump(mode="json")
    return draft.before == {"habit_recompute": scope} and draft.after == {
        "habit_recompute": {**scope, "requested": True}
    }


async def execute_habit_recompute(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_habit_recompute(draft):
        raise ValueError("Recompute must retain the exact confirmed account/timezone/preferences")
    expected = HabitRecomputePatch.model_validate(draft.intent).habit_recompute

    async def check() -> None:
        await habit_settings_fence(db, actor_id, draft)
        if await recompute_scope(db, actor_id) != expected:
            raise ResourceConflictError("habit_recompute", detail={"error_code": "STALE_STATE"})

    await check()
    try:
        await recompute_managed_habits(db, actor_id, receipt=receipt, check=check)
    except HabitCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
