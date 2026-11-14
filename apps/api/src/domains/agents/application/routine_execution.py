"""Accept one confirmed manual trigger; the source worker decides its outcome."""

import asyncio
from functools import partial
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, raise_scheduled_action_already_executing
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_execution_policy import (
    RoutineExecutionReservation,
    authorize_reserved_routine,
    cancel_routine_reservation,
    wait_for_routine_turn,
)
from src.domains.agents.application.routine_operations import (
    commit_routine_change,
    lock_routine_for_command,
    routine_snapshot,
)
from src.domains.agents.application.routine_run_schemas import (
    RoutineRunPatch,
    RoutineRunRequest,
    RoutineRunValues,
)
from src.domains.agents.application.routine_spec import ROUTINE_RUN_OPERATION
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.scheduled_actions.mcp_preapproval import preapproval_names
from src.domains.scheduled_actions.models import ScheduledActionStatus
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.async_utils import finish_owned_task, safe_fire_and_forget

logger = structlog.get_logger(__name__)


async def prepare_routine_launch(
    db: AsyncSession, actor_id: UUID, request: RoutineRunRequest, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    validated = RoutineRunRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    row = await ScheduledActionService(db).get_with_ownership_check(validated.routine_id, actor_id)
    if row.status == ScheduledActionStatus.EXECUTING.value:
        raise_scheduled_action_already_executing(row.id)
    patch = RoutineRunPatch(
        routine_to_run=RoutineRunValues(
            expected=routine_snapshot(row),
            user_timezone=row.user_timezone,
            configuration=RoutineCreateRequest.model_validate(
                {name: getattr(row, name) for name in ScheduledActionCreate.model_fields}
            ),
            mcp_preapproval=await preapproval_names(db, actor, row),
        )
    )
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        ROUTINE_RUN_OPERATION,
        patch,
        {"routine_to_run": None},
        patch.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def execute_routine_launch(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    selected = RoutineRunPatch.model_validate(draft.intent).routine_to_run
    if draft.before != {"routine_to_run": None}:
        raise ValueError("A manual trigger must retain its exact confirmed selection")
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    row = await lock_routine_for_command(db, actor_id, draft, selected.expected)
    current = RoutineCreateRequest.model_validate(
        {name: getattr(row, name) for name in ScheduledActionCreate.model_fields}
    )
    if selected.configuration != current or selected.user_timezone != row.user_timezone:
        raise ResourceConflictError("scheduled_action", detail={"error_code": "STALE_STATE"})
    await ScheduledActionService(db).reserve_manual_execution(
        row.id, actor_id, execution_token=draft.command_id
    )
    await commit_routine_change(db, actor_id, draft, receipt)
    reservation = RoutineExecutionReservation(
        actor_id, selected.expected, draft.command_id, draft.expires_at
    )
    _start_reserved_run(reservation)


def _start_reserved_run(reservation: RoutineExecutionReservation) -> None:
    task = _run_reserved(reservation)
    try:
        safe_fire_and_forget(
            task, name=f"lia-routine-{reservation.token}", independent_of_graph=True
        )
    except Exception:
        task.close()
        raise


async def _run_reserved(reservation: RoutineExecutionReservation) -> None:
    from src.infrastructure.scheduler.scheduled_action_executor import execute_single_action

    try:
        if await wait_for_routine_turn(reservation.actor_id, reservation.expires_at):
            await execute_single_action(
                action_id=reservation.expected.id,
                user_id=reservation.actor_id,
                execution_guard=partial(authorize_reserved_routine, reservation),
                execution_token=reservation.token,
                # Asked in the chat and confirmed: the person's run.
                started_by_person=True,
            )
    except SQLAlchemyError:
        logger.warning("routine_readiness_unavailable", action_id=str(reservation.expected.id))
    finally:
        await finish_owned_task(asyncio.create_task(_release_reservation(reservation)))


async def _release_reservation(reservation: RoutineExecutionReservation) -> None:
    """A cancelled or refused launcher owns its conditional cleanup through shutdown."""
    try:
        await cancel_routine_reservation(reservation)
    except SQLAlchemyError:
        logger.warning(
            "routine_reservation_cancel_unavailable", action_id=str(reservation.expected.id)
        )
