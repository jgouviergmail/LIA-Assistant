"""Meeting preference tools take the account exclusively from trusted runtime."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.meeting_preference_schemas import MeetingPreferenceInput
from src.domains.agents.application.meeting_preferences import (
    prepare_meeting_preferences,
    read_meeting_preferences,
)
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_meeting_preferences", agent_name="setting_agent")
async def get_lia_meeting_preferences_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Observe current future meeting defaults without recording or processing.

    Args:
        runtime: Injected authenticated account context.

    Returns:
        Current preferences and the enforced readonly retention ceiling.
    """
    actor = validate_runtime_config(runtime, "get_lia_meeting_preferences_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        async with get_db_context() as db:
            observed = await read_meeting_preferences(db, UUID(actor.user_id))
    except AuthorizationError as error:
        return UnifiedToolOutput.failure(
            message="Meeting settings unavailable.", error_code=application_access_error_code(error)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Meeting settings temporarily unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid stored meeting settings.", error_code="INVALID_INPUT"
        )
    return UnifiedToolOutput.data_success(
        message="Observed future meeting defaults; no recording, processing or email occurred.",
        structured_data=observed.model_dump(mode="json"),
    )


@write_tool(name="update_lia_meeting_preferences", agent_name="setting_agent")
async def update_lia_meeting_preferences_tool(
    request: MeetingPreferenceInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare mandatory confirmation for only the requested future meeting defaults.

    Args:
        request: Requested preference fields, excluding the readonly ceiling.
        runtime: Injected authenticated account context.

    Returns:
        Exact HITL proposal; no preference changes during preparation.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="update_lia_meeting_preferences_tool",
        model=MeetingPreferenceInput,
        prepare=prepare_meeting_preferences,
        sessions=get_db_context,
    )
