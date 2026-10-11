"""Habit preference writes are proposals behind mandatory exact human confirmation."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.habit_action_schemas import (
    HabitDeleteRequest,
    HabitStatusRequest,
)
from src.domains.agents.application.habit_actions import prepare_habit_action
from src.domains.agents.application.habit_forget_schemas import HabitForgetRequest
from src.domains.agents.application.habit_forgetting import prepare_habit_forgetting
from src.domains.agents.application.habit_recompute import prepare_habit_recompute
from src.domains.agents.application.habit_recompute_schemas import HabitRecomputeRequest
from src.domains.agents.application.habit_settings import prepare_habit_settings
from src.domains.agents.application.habit_settings_schemas import HabitSettingsPatch
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="update_lia_habit_settings", agent_name="setting_agent")
async def update_lia_habit_settings_tool(
    patch: HabitSettingsPatch,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Save reviewed reversible preferences; sensitive fields retain confirmation.

    Args:
        patch: Explicit source settings; omitted fields and existing records are preserved.
        runtime: Injected account identity and permissions.

    Returns:
        Actual saved values or an exact confirmation for a sensitive patch.
    """
    return await prepare_native_tool(
        patch,
        runtime,
        name="update_lia_habit_settings_tool",
        model=HabitSettingsPatch,
        prepare=prepare_habit_settings,
        sessions=get_db_context,
    )


async def _prepare_habit_action(
    request: object,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    source_tool: str,
    model: (
        type[HabitStatusRequest]
        | type[HabitDeleteRequest]
        | type[HabitForgetRequest]
        | type[HabitRecomputeRequest]
    ),
) -> UnifiedToolOutput:
    actor = validate_runtime_config(runtime, source_tool)
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        parsed = model.model_validate(request)
        async with get_db_context() as db:
            if isinstance(parsed, HabitRecomputeRequest):
                content = await prepare_habit_recompute(db, UUID(actor.user_id), parsed)
            else:
                content = (
                    await prepare_habit_forgetting(db, UUID(actor.user_id), parsed)
                    if isinstance(parsed, HabitForgetRequest)
                    else await prepare_habit_action(db, UUID(actor.user_id), parsed)
                )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool=source_tool,
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
        return output
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Habit unavailable.", error_code="NOT_FOUND")
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Habit access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Habit proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid habit request or source state.", error_code="INVALID_INPUT"
        )


@write_tool(name="set_lia_habit_status", agent_name="setting_agent")
async def set_lia_habit_status_tool(
    request: HabitStatusRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to pause, resume or block one learned habit.

    Args:
        request: Owned habit identity and source target status.
        runtime: Injected authenticated account context.

    Returns:
        Complete before/after confirmation; no mutation before approval.
    """
    return await _prepare_habit_action(
        request, runtime, "set_lia_habit_status_tool", HabitStatusRequest
    )


@write_tool(name="delete_lia_habit", agent_name="setting_agent")
async def delete_lia_habit_tool(
    request: HabitDeleteRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to remove one learned habit, permitting relearning.

    Args:
        request: Owned habit identity; no arbitrary scope or authority.
        runtime: Injected authenticated account context.

    Returns:
        Exact removal confirmation without disabling learning or erasing other records.
    """
    return await _prepare_habit_action(
        request, runtime, "delete_lia_habit_tool", HabitDeleteRequest
    )


@write_tool(name="delete_all_lia_habits", agent_name="setting_agent")
async def delete_all_lia_habits_tool(
    request: HabitForgetRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to forget all owned habit learning state.

    Args:
        request: Explicit complete owned scope, never an arbitrary actor or Redis key.
        runtime: Injected authenticated account context.

    Returns:
        Bounded count/scope confirmation; no erasure before exact approval.
    """
    return await _prepare_habit_action(
        request, runtime, "delete_all_lia_habits_tool", HabitForgetRequest
    )


@write_tool(name="recompute_lia_habits", agent_name="setting_agent")
async def recompute_lia_habits_tool(
    request: HabitRecomputeRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to recompute the current account's rhythm and habits.

    Args:
        request: Current account source recompute only; no forced outcome or foreign owner.
        runtime: Injected authenticated account context.

    Returns:
        Pending source recompute confirmation without learning before approval.
    """
    return await _prepare_habit_action(
        request, runtime, "recompute_lia_habits_tool", HabitRecomputeRequest
    )
