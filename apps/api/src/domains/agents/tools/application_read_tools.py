"""Application reads with current account authority and finite projections."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.core.i18n import resolve_language
from src.domains.agents.application.assistant_queries import read_assistant_preferences
from src.domains.agents.application.assistant_schemas import (
    AssistantPreferenceField,
    AssistantPreferenceRead,
)
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.preference_fields import PreferenceField
from src.domains.agents.application.queries import read_preferences
from src.domains.agents.application.schemas import PreferenceRead
from src.domains.agents.application.setting_choices import describe_setting_values
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_preferences", agent_name="setting_agent")
async def get_lia_preferences_tool(
    fields: Annotated[list[PreferenceField] | None, PreferenceRead.model_fields["fields"]] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read the user's saved LIA preferences without changing anything.

    Args:
        fields: Declared non-secret account fields; omit to read all.
        runtime: Injected native execution context.

    Returns:
        Current account projection or a typed refusal, never a guessed default.
    """
    validated = validate_runtime_config(runtime, "get_lia_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = PreferenceRead(fields=fields)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid preference selection.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            projection = await read_preferences(db, UUID(str(validated.user_id)), request)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Stored application state cannot be projected.",
            error_code="DEPENDENCY_ERROR",
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application access refused.",
            error_code=application_access_error_code(exc),
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Application state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return UnifiedToolOutput.data_success(
        message="Current saved application preferences.",
        structured_data={
            "preferences": projection.model_dump(mode="json"),
            "setting_choices": describe_setting_values(
                projection.values,
                resolve_language(runtime.context.language if runtime else None),
            ),
            "total": len(projection.values),
        },
    )


@read_tool(name="get_lia_assistant_preferences", agent_name="setting_agent")
async def get_lia_assistant_preferences_tool(
    fields: Annotated[
        list[AssistantPreferenceField] | None,
        AssistantPreferenceRead.model_fields["fields"],
    ] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read current non-secret assistant settings, without changing any consent.

    Args:
        fields: Distinct account preference selectors; omit to read all.
        runtime: Injected account identity, never a model-supplied user id.

    Returns:
        Current saved assistant preference values, or a finite refusal.
    """
    validated = validate_runtime_config(runtime, "get_lia_assistant_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = AssistantPreferenceRead(fields=fields)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid preference selection.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            projection = await read_assistant_preferences(db, UUID(str(validated.user_id)), request)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Stored application state cannot be projected.",
            error_code="DEPENDENCY_ERROR",
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application access refused.",
            error_code=application_access_error_code(exc),
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Application state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return UnifiedToolOutput.data_success(
        message="Current saved assistant preferences.",
        structured_data={
            "preferences": projection.model_dump(mode="json"),
            "setting_choices": describe_setting_values(
                projection.values,
                resolve_language(runtime.context.language if runtime else None),
            ),
            "total": len(projection.values),
        },
    )
