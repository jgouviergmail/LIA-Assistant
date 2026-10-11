"""Sparse Studio edits freeze their full result, including source revival."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_operations import (
    commit_routine_change,
    lock_routine_for_command,
    routine_snapshot,
)
from src.domains.agents.application.routine_spec import ROUTINE_UPDATE_OPERATION
from src.domains.agents.application.routine_update_schemas import (
    RoutineUpdatePatch,
    RoutineUpdateRequest,
    RoutineUpdateValues,
)
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.schemas import ScheduledActionCreate, ScheduledActionUpdate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.preference_cas import PreferenceWriteReceipt


def _configuration(row: ScheduledAction) -> RoutineCreateRequest:
    return RoutineCreateRequest.model_validate(
        {name: getattr(row, name) for name in ScheduledActionCreate.model_fields}
    )


async def prepare_routine_update(
    db: AsyncSession,
    actor_id: UUID,
    request: RoutineUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = RoutineUpdateRequest.model_validate(
        request.model_dump(mode="json", exclude_unset=True)
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    source = ScheduledActionService(db)
    row = await source.get_with_ownership_check(validated.routine_id, actor_id)
    changes = ScheduledActionUpdate.model_validate(
        validated.changes.model_dump(mode="json", exclude_unset=True)
    )
    previous = RoutineUpdateValues(
        expected=routine_snapshot(row),
        user_timezone=row.user_timezone,
        enabled=row.is_enabled,
        configuration=_configuration(row),
        changes=validated.changes,
    )
    desired = previous.model_copy(
        update={
            "configuration": RoutineCreateRequest.model_validate(
                source.preview_configuration(row, changes).model_dump(mode="json")
            ),
            "enabled": source.preview_enabled(row, changes),
        }
    )
    before, after = RoutineUpdatePatch(routine_configuration=previous), RoutineUpdatePatch(
        routine_configuration=desired
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        ROUTINE_UPDATE_OPERATION,
        after,
        before.model_dump(mode="json", exclude_unset=True),
        after.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def execute_routine_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = RoutineUpdatePatch.model_validate(draft.intent).routine_configuration
    previous = RoutineUpdatePatch.model_validate(draft.before).routine_configuration
    if (
        desired.expected != previous.expected
        or desired.changes != previous.changes
        or desired.user_timezone != previous.user_timezone
        or previous.enabled != previous.expected.enabled
    ):
        raise ValueError("A routine edit cannot replace its confirmed comparison data")
    row = await lock_routine_for_command(db, actor_id, draft, previous.expected)
    source = ScheduledActionService(db)
    changes = ScheduledActionUpdate.model_validate(
        desired.changes.model_dump(mode="json", exclude_unset=True)
    )
    actual = RoutineCreateRequest.model_validate(
        source.preview_configuration(row, changes).model_dump(mode="json")
    )
    if (
        _configuration(row) != previous.configuration
        or actual != desired.configuration
        or source.preview_enabled(row, changes) != desired.enabled
        or row.user_timezone != desired.user_timezone
    ):
        raise ResourceConflictError("scheduled_action", detail={"error_code": "STALE_STATE"})
    if previous.configuration == desired.configuration and previous.enabled == desired.enabled:
        receipt.committed, receipt.no_op = True, True
        return
    updated = await source.update(row.id, actor_id, changes)
    if _configuration(updated) != desired.configuration or updated.is_enabled != desired.enabled:
        raise ResourceConflictError("scheduled_action", detail={"error_code": "STALE_STATE"})
    await commit_routine_change(db, actor_id, draft, receipt)
