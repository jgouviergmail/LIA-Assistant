"""Routine state changes reuse the owner service under an exact configuration lock."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.routine_schemas import (
    RoutineSnapshot,
    RoutineStatePatch,
    RoutineStateRequest,
    RoutineStateValues,
)
from src.domains.agents.application.routine_spec import ROUTINE_STATE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

_CONFIGURATION_FIELDS = frozenset(
    {
        "title",
        "action_prompt",
        "recurrence",
        "trigger_kind",
        "condition_config",
        "requires_approval",
        "execution_mode",
    }
)
_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def routine_snapshot(row: ScheduledAction) -> RoutineSnapshot:
    if set(ScheduledActionCreate.model_fields) != _CONFIGURATION_FIELDS:
        raise ValueError("Review new routine settings before preparing confirmation")
    configuration = {
        name: _JSON.validate_python(getattr(row, name)) for name in _CONFIGURATION_FIELDS
    }
    configuration.update(user_timezone=row.user_timezone, created_at=row.created_at.isoformat())
    return RoutineSnapshot(
        id=row.id,
        title=row.title,
        enabled=row.is_enabled,
        configuration_digest=payload_digest(configuration),
    )


async def prepare_routine_state(
    db: AsyncSession,
    actor_id: UUID,
    request: RoutineStateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = RoutineStateRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await ScheduledActionService(db).get_with_ownership_check(validated.routine_id, actor_id)
    snapshot = routine_snapshot(row)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    before = RoutineStatePatch(
        routine_state=RoutineStateValues(expected=snapshot, enabled=snapshot.enabled)
    )
    after = RoutineStatePatch(
        routine_state=RoutineStateValues(expected=snapshot, enabled=validated.enabled)
    )
    return build_action_content(
        actor_id,
        ROUTINE_STATE_OPERATION,
        after,
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
        command_id=command_id,
    )


async def execute_routine_state(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    desired = RoutineStatePatch.model_validate(draft.intent).routine_state
    previous = RoutineStatePatch.model_validate(draft.before).routine_state
    if desired.expected != previous.expected or previous.enabled != previous.expected.enabled:
        raise ValueError("A routine change cannot replace its confirmed configuration")
    row = await lock_routine_for_command(db, actor_id, draft, previous.expected)
    if row.is_enabled == desired.enabled:
        receipt.committed = True
        receipt.no_op = True
        return
    await ScheduledActionService(db).set_enabled(row.id, actor_id, desired.enabled)
    await commit_routine_change(db, actor_id, draft, receipt)


async def lock_routine_for_command(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    expected: RoutineSnapshot,
) -> ScheduledAction:
    await require_application_tools(db)
    actor = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    authorize_actor(actor)
    row = await db.scalar(
        select(ScheduledAction)
        .where(ScheduledAction.id == expected.id, ScheduledAction.user_id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    if row is None:
        raise ResourceConflictError("scheduled_action", detail={"error_code": "STALE_STATE"})
    if routine_snapshot(row) != expected:
        raise ResourceConflictError("scheduled_action", detail={"error_code": "STALE_STATE"})
    return row


async def commit_routine_change(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    # Service reads and flushes await I/O. A withdrawn switch must still roll back.
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
