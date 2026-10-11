"""Frozen Studio configuration uses the common source creation slot and deterministic identity."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.routine_create_schemas import (
    RoutineCreatePatch,
    RoutineCreateRequest,
    RoutineCreationValues,
)
from src.domains.agents.application.routine_spec import ROUTINE_CREATE_OPERATION
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService, validate_routine_creation
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_routine_creation(
    db: AsyncSession,
    actor_id: UUID,
    request: RoutineCreateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = RoutineCreateRequest.model_validate(request.model_dump(mode="json"))
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    timezone = actor.timezone or DEFAULT_USER_DISPLAY_TIMEZONE
    validate_routine_creation(
        ScheduledActionCreate.model_validate(validated.model_dump(mode="json")), timezone
    )
    identity = command_id or uuid4()
    patch = RoutineCreatePatch(
        routine_to_create=RoutineCreationValues(
            id=identity, user_timezone=timezone, configuration=validated
        )
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        ROUTINE_CREATE_OPERATION,
        patch,
        {"routine_to_create": None},
        patch.model_dump(mode="json"),
        command_id=identity,
    )


async def execute_routine_creation(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    proposal = RoutineCreatePatch.model_validate(draft.intent).routine_to_create
    if proposal.id != draft.command_id or draft.before != {"routine_to_create": None}:
        raise ValueError("A creation must retain its confirmed command identity")
    await require_application_tools(db)
    actor = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    current = authorize_actor(actor)
    if (current.timezone or DEFAULT_USER_DISPLAY_TIMEZONE) != proposal.user_timezone:
        raise ResourceConflictError("scheduled_action", detail={"error_code": "STALE_STATE"})
    await require_application_tools(db)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    await ScheduledActionService(db).create(
        actor_id,
        ScheduledActionCreate.model_validate(proposal.configuration.model_dump(mode="json")),
        proposal.user_timezone,
        action_id=proposal.id,
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        # The deterministic id permits observation; an uncertain insert is never replayed.
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
