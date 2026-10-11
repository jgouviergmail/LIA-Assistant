"""Routine management creates proposals; the shared confirmed writer alone changes state."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import JsonValue, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.core.exceptions import ValidationError as DomainValidationError
from src.domains.agents.application.availability import (
    application_access_error_code,
    require_application_tools,
)
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_creation import prepare_routine_creation
from src.domains.agents.application.routine_execution import prepare_routine_launch
from src.domains.agents.application.routine_operations import prepare_routine_state
from src.domains.agents.application.routine_queries import read_routines
from src.domains.agents.application.routine_read_schemas import RoutineProjection, RoutineRead
from src.domains.agents.application.routine_removal import prepare_routine_removal
from src.domains.agents.application.routine_removal_schemas import RoutineDeleteRequest
from src.domains.agents.application.routine_run_schemas import RoutineRunRequest
from src.domains.agents.application.routine_schemas import RoutineStateRequest
from src.domains.agents.application.routine_update import prepare_routine_update
from src.domains.agents.application.routine_update_schemas import RoutineUpdateRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.scheduled_actions.service import ScheduledActionService
from src.infrastructure.database.session import get_db_context


async def routine_state_proposal(
    actor_id: UUID,
    routine_id: UUID,
    enabled: bool | None,
    language: str,
) -> UnifiedToolOutput:
    """Legacy toggle resolves its desired state once; neither caller makes a write."""
    try:
        async with get_db_context() as db:
            await require_application_tools(db)
            if enabled is None:
                row = await ScheduledActionService(db).get_with_ownership_check(
                    routine_id, actor_id
                )
                enabled = not row.is_enabled
            content = await prepare_routine_state(
                db, actor_id, RoutineStateRequest(routine_id=routine_id, enabled=enabled)
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="set_lia_routine_state_tool",
                user_language=language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Routine proposal unavailable.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Routine unavailable.", error_code="NOT_FOUND")
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Routine proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid routine configuration.", error_code="INVALID_INPUT"
        )
    return output


@write_tool(name="execute_lia_routine", agent_name="setting_agent")
async def execute_lia_routine_tool(
    selection: RoutineRunRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for one manual Studio trigger.

    Args:
        selection: Owned routine id; execution uses its confirmed saved settings.
        runtime: Injected authenticated account context.

    Returns:
        Pending manual trigger, retaining source condition, approval and quota checks.
    """
    actor = validate_runtime_config(runtime, "execute_lia_routine_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = RoutineRunRequest.model_validate(selection)
        request = RoutineRunRequest.model_validate(parsed.model_dump())
        async with get_db_context() as db:
            content = await prepare_routine_launch(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="execute_lia_routine_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Routine access refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Routine unavailable.", error_code="NOT_FOUND")
    except ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="Routine is already executing.", error_code="ALREADY_EXECUTING"
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Routine proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid routine configuration.", error_code="INVALID_INPUT"
        )
    return output


@write_tool(name="update_lia_routine", agent_name="setting_agent")
async def update_lia_routine_tool(
    change: RoutineUpdateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact Studio edit confirmation; no change or run before approval.

    Args:
        change: Owned routine id and sparse requested configuration changes.
        runtime: Injected authenticated account context.

    Returns:
        Full resulting configuration and enabled state for exact confirmation.
    """
    actor = validate_runtime_config(runtime, "update_lia_routine_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = RoutineUpdateRequest.model_validate(change)
        request = RoutineUpdateRequest.model_validate(
            parsed.model_dump(mode="json", exclude_unset=True)
        )
        async with get_db_context() as db:
            content = await prepare_routine_update(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_routine_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Routine access refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Routine unavailable.", error_code="NOT_FOUND")
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Routine proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except DomainValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid routine schedule or configuration.", error_code="INVALID_INPUT"
        )
    return output


@write_tool(name="delete_lia_routine", agent_name="setting_agent")
async def delete_lia_routine_tool(
    selection: RoutineDeleteRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare confirmation to permanently remove a routine and its source run history.

    Args:
        selection: Exact owned routine id.
        runtime: Injected authenticated account context.

    Returns:
        Pending deletion only. Future triggers stop; an ongoing run may finish.
    """
    actor = validate_runtime_config(runtime, "delete_lia_routine_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        request = RoutineDeleteRequest.model_validate(selection)
        request = RoutineDeleteRequest.model_validate(request.model_dump())
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid routine selection.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_routine_removal(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="delete_lia_routine_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Routine access refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Routine unavailable.", error_code="NOT_FOUND")
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Routine proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid routine state.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return output


@write_tool(name="create_lia_routine", agent_name="setting_agent")
async def create_lia_routine_tool(
    configuration: RoutineCreateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation to create a time or condition routine.

    Args:
        configuration: Full Studio configuration, including future approval and execution mode.
        runtime: Injected authenticated account context.

    Returns:
        Pending creation only. No immediate execution; future runs use the confirmed mandate.
    """
    actor = validate_runtime_config(runtime, "create_lia_routine_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = RoutineCreateRequest.model_validate(configuration)
        request = RoutineCreateRequest.model_validate(parsed.model_dump(mode="json"))
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid routine configuration.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_routine_creation(db, UUID(actor.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="create_lia_routine_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Routine access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Routine proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except DomainValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid routine schedule or configuration.", error_code="INVALID_INPUT"
        )
    return output


@read_tool(name="get_lia_routines", agent_name="setting_agent")
async def get_lia_routines_tool(
    query: RoutineRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read owned routine configuration or the source-computed current week.

    Args:
        query: Settings or week, with an optional owned routine id.
        runtime: Injected authenticated account context.

    Returns:
        Public Studio data, exact returned count and source truncation status.
        No execution, mutation or private condition-fact ledger.
    """
    actor = validate_runtime_config(runtime, "get_lia_routines_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        request = RoutineRead.model_validate(query) if query is not None else RoutineRead()
        request = RoutineRead.model_validate(request.model_dump())
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid routine selection.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            result = await read_routines(db, UUID(actor.user_id), request)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Routine access refused.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Routine unavailable.", error_code="NOT_FOUND")
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Routine data unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Stored routine data invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return UnifiedToolOutput.data_success(
        message="Owned Studio routine data. No routine was started or changed. Truncation is stated explicitly.",
        structured_data=public_routine_read(result),
        metadata={"application_routine_cursor": True},
    )


def public_routine_read(result: RoutineProjection) -> dict[str, JsonValue]:
    """Keep the item list at the shared result-budget seam, never cut a nested JSON blob."""
    data = result.settings if result.view == "settings" else result.week
    if data is None:
        raise ValueError("A routine read requires its selected source view")
    return {
        **data.model_dump(mode="json"),
        "view": result.view,
        "returned_count": result.returned_count,
        "total_available": result.total_available,
        "truncated": result.truncated,
        "next_cursor": str(result.next_cursor) if result.next_cursor else None,
    }


@write_tool(name="set_lia_routine_state", agent_name="setting_agent")
async def set_lia_routine_state_tool(
    change: RoutineStateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare confirmation to pause or enable a routine by its owned id.

    Args:
        change: Routine id and explicit desired enabled state.
        runtime: Injected authenticated account context.

    Returns:
        Exact pending proposal only. Pausing leaves an ongoing run to finish.
        Changed configuration requires a new preview and confirmation.
    """
    actor = validate_runtime_config(runtime, "set_lia_routine_state_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = RoutineStateRequest.model_validate(change)
        request = RoutineStateRequest.model_validate(parsed.model_dump())
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid desired routine state.", error_code="INVALID_INPUT"
        )
    return await routine_state_proposal(
        UUID(actor.user_id), request.routine_id, request.enabled, runtime.context.language
    )
