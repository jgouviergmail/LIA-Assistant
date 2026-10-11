"""Read heartbeat availability and prepare exact settings using the shared domain owner."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.heartbeat_operations import (
    prepare_heartbeat_content,
    read_heartbeat_preferences,
)
from src.domains.agents.application.heartbeat_schemas import (
    HeartbeatPreferenceField,
    HeartbeatPreferencePatch,
    HeartbeatPreferenceRead,
)
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_heartbeat_preferences", agent_name="setting_agent")
async def get_lia_heartbeat_preferences_tool(
    fields: Annotated[
        list[HeartbeatPreferenceField] | None, HeartbeatPreferenceRead.model_fields["fields"]
    ] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read saved heartbeat settings and the current platform/source availability.

    Args:
        fields: Distinct non-secret heartbeat selectors; omit to read all.
        runtime: Injected authenticated account context.

    Returns:
        Sanitized current UI values; no inferred defaults beyond the UI owner.
    """
    validated = validate_runtime_config(runtime, "get_lia_heartbeat_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = HeartbeatPreferenceRead(fields=fields)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid heartbeat selection.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            projection = await read_heartbeat_preferences(db, UUID(str(validated.user_id)), request)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Application state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return UnifiedToolOutput.data_success(
        message="Current saved heartbeat settings and delivery/source availability.",
        structured_data={
            "preferences": projection.model_dump(mode="json"),
            "total": len(projection.values),
        },
    )


@write_tool(name="update_lia_heartbeat_preferences", agent_name="setting_agent")
async def update_lia_heartbeat_preferences_tool(
    patch: HeartbeatPreferencePatch,
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
        name="update_lia_heartbeat_preferences_tool",
        model=HeartbeatPreferencePatch,
        prepare=prepare_heartbeat_content,
        sessions=get_db_context,
    )
