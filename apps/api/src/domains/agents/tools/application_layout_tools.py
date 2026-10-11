"""Read UI layouts and prepare exact replacements using the shared domain owner."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.layout_queries import read_layout_preferences
from src.domains.agents.application.layout_schemas import (
    LayoutPreferenceField,
    LayoutPreferenceRead,
)
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.preparation import prepare_layout_content
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.account_preferences import LayoutPreferencePatch
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_layout_preferences", agent_name="setting_agent")
async def get_lia_layout_preferences_tool(
    fields: Annotated[
        list[LayoutPreferenceField] | None, LayoutPreferenceRead.model_fields["fields"]
    ] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read the current account's displayed grid and shortcut lists.

    Args:
        fields: Distinct non-secret layout selectors; omit to read all.
        runtime: Injected authenticated account context.

    Returns:
        Sanitized current UI values; no inferred defaults beyond the UI owner.
    """
    validated = validate_runtime_config(runtime, "get_lia_layout_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = LayoutPreferenceRead(fields=fields)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid layout selection.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            projection = await read_layout_preferences(db, UUID(str(validated.user_id)), request)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application access refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Application state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return UnifiedToolOutput.data_success(
        message="Current displayed application layouts.",
        structured_data={
            "preferences": projection.model_dump(mode="json"),
            "total": len(projection.values),
        },
    )


@write_tool(name="update_lia_layout_preferences", agent_name="setting_agent")
async def update_lia_layout_preferences_tool(
    patch: LayoutPreferencePatch,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Save reversible layout personalization, preserving concurrent visible edits.

    Args:
        patch: Complete desired lists for selected layouts, including preserved entries.
        runtime: Injected account context; the model cannot select an actor.

    Returns:
        Actual saved state or a finite refusal; no confirmation for personalization.
    """
    return await prepare_native_tool(
        patch,
        runtime,
        name="update_lia_layout_preferences_tool",
        model=LayoutPreferencePatch,
        prepare=prepare_layout_content,
        sessions=get_db_context,
    )
