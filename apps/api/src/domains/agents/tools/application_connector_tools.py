"""Native non-secret connector preferences; no credentials, OAuth or provider probe."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.connector_operations import (
    prepare_connector_preference_content,
    read_connector_preferences,
)
from src.domains.agents.application.connector_schemas import (
    ConnectorPreferencesRead,
    ConnectorPreferenceUpdateRequest,
)
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.connectors.preferences.commands import ConnectorPreferenceStateUnavailable
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_connector_preferences", agent_name="setting_agent")
async def get_lia_connector_preferences_tool(
    query: ConnectorPreferencesRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read saved non-secret calendar/task-list defaults, with explicit pagination.

    Args:
        query: Page limit and previous next_cursor as after_id. Omit for the first page.
        runtime: Injected authenticated account context.

    Returns:
        Current owner's preferences and saved connector status, never credentials or a live health probe.
    """
    validated = validate_runtime_config(runtime, "get_lia_connector_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = (
            ConnectorPreferencesRead.model_validate(query)
            if query is not None
            else ConnectorPreferencesRead()
        )
        async with get_db_context() as db:
            values = await read_connector_preferences(db, UUID(validated.user_id), request)
    except ConnectorPreferenceStateUnavailable, SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Saved connector preferences unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid preference page.", error_code="INVALID_INPUT"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return UnifiedToolOutput.data_success(
        message="Saved connector preferences; follow next_cursor until empty for a complete list.",
        structured_data=values.model_dump(mode="json"),
        metadata={"application_connector_cursor": True},
    )


@write_tool(name="update_lia_connector_preferences", agent_name="setting_agent")
async def update_lia_connector_preferences_tool(
    change: ConnectorPreferenceUpdateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for saved non-secret calendar or task-list defaults.

    Args:
        change: Existing owned connector id and explicitly requested preference to set or clear.
        runtime: Injected authenticated account context.

    Returns:
        Durable confirmation for the sanitized value; no preference saved before approval.
    """
    validated = validate_runtime_config(runtime, "update_lia_connector_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    try:
        request = ConnectorPreferenceUpdateRequest.model_validate(change)
        async with get_db_context() as db:
            content = await prepare_connector_preference_content(
                db, UUID(validated.user_id), request
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_connector_preferences_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except ConnectorPreferenceStateUnavailable, SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Saved preferences or proposal persistence unavailable.",
            error_code="DEPENDENCY_ERROR",
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid connector preference change.", error_code="INVALID_INPUT"
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Connector preferences unavailable.", error_code="NOT_FOUND"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return output
