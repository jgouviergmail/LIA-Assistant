"""Delete the exact approved routine through its source writer and cascade."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.routine_operations import (
    commit_routine_change,
    lock_routine_for_command,
    routine_snapshot,
)
from src.domains.agents.application.routine_removal_schemas import (
    RoutineDeletePatch,
    RoutineDeleteRequest,
)
from src.domains.agents.application.routine_spec import ROUTINE_DELETE_OPERATION
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_routine_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: RoutineDeleteRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = RoutineDeleteRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await ScheduledActionService(db).get_with_ownership_check(validated.routine_id, actor_id)
    patch = RoutineDeletePatch(routine_to_delete=routine_snapshot(row))
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        ROUTINE_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"routine_to_delete": None},
        command_id=command_id,
    )


async def execute_routine_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    expected = RoutineDeletePatch.model_validate(draft.intent)
    if expected.model_dump(mode="json") != draft.before or draft.after != {
        "routine_to_delete": None
    }:
        raise ValueError("A deletion must retain its confirmed routine selection")
    row = await lock_routine_for_command(db, actor_id, draft, expected.routine_to_delete)
    await ScheduledActionService(db).delete(row.id, actor_id)
    await commit_routine_change(db, actor_id, draft, receipt)
