"""Edited habit identity/status receives current facts and a new approval digest."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.habit_action_schemas import (
    HabitDeleteRequest,
    HabitStatusRequest,
)
from src.domains.agents.application.habit_actions import prepare_habit_action
from src.domains.agents.application.habit_forget_schemas import HabitForgetRequest
from src.domains.agents.application.habit_forgetting import prepare_habit_forgetting
from src.domains.agents.application.habit_recompute import prepare_habit_recompute
from src.domains.agents.application.habit_recompute_schemas import HabitRecomputeRequest
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_habit_draft(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    models: dict[
        str,
        type[HabitStatusRequest]
        | type[HabitDeleteRequest]
        | type[HabitForgetRequest]
        | type[HabitRecomputeRequest],
    ] = {
        "habits.status": HabitStatusRequest,
        "habits.delete": HabitDeleteRequest,
        "habits.forget": HabitForgetRequest,
        "habits.recompute": HabitRecomputeRequest,
    }
    model = models[old.operation_id]
    request = model.model_validate(modified.get("intent"))
    async with get_db_context() as db:
        if isinstance(request, HabitRecomputeRequest):
            revised = await prepare_habit_recompute(
                db, old.actor_id, request, command_id=old.command_id
            )
        else:
            revised = (
                await prepare_habit_forgetting(db, old.actor_id, request, command_id=old.command_id)
                if isinstance(request, HabitForgetRequest)
                else await prepare_habit_action(
                    db, old.actor_id, request, command_id=old.command_id
                )
            )
        if not await replace_pending_command(db, old, revised):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
