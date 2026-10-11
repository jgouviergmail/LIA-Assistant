"""Native personal choices for shared MCP servers; global configuration is never accepted."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.shared_mcp_operations import (
    prepare_shared_mcp_content,
    read_shared_mcp_preferences,
)
from src.domains.agents.application.shared_mcp_schemas import (
    SharedMCPPreferenceRead,
    SharedMCPPreferenceUpdateRequest,
)
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_shared_mcp_preferences", agent_name="setting_agent")
async def get_lia_shared_mcp_preferences_tool(
    query: SharedMCPPreferenceRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read personal enabled choices for configured shared MCP servers, in bounded pages.

    Args:
        query: Optional selected server, page limit and prior next_cursor as after_key.
        runtime: Injected authenticated account context.

    Returns:
        Saved personal choices and tool counts. No global configuration or credentials.
    """
    validated = validate_runtime_config(runtime, "get_lia_shared_mcp_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = (
            SharedMCPPreferenceRead.model_validate(query)
            if query is not None
            else SharedMCPPreferenceRead()
        )
        async with get_db_context() as db:
            values = await read_shared_mcp_preferences(db, UUID(validated.user_id), request)
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Saved shared preferences unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid shared preference query.", error_code="INVALID_INPUT"
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Shared server unavailable.", error_code="NOT_FOUND"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return UnifiedToolOutput.data_success(
        message="Personal shared MCP choices. Follow next_cursor for all pages; global configuration and full tool descriptions are separate.",
        structured_data=values.model_dump(mode="json"),
        metadata={"application_shared_mcp_cursor": True},
    )


@write_tool(name="update_lia_shared_mcp_preferences", agent_name="setting_agent")
async def update_lia_shared_mcp_preferences_tool(
    change: SharedMCPPreferenceUpdateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare human confirmation to enable or disable one shared server for this account.

    Args:
        change: Existing shared server key and desired personal enabled state.
        runtime: Injected authenticated account context.

    Returns:
        Durable exact confirmation. No change before approval; other accounts are unaffected.
    """
    validated = validate_runtime_config(runtime, "update_lia_shared_mcp_preferences_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    try:
        request = SharedMCPPreferenceUpdateRequest.model_validate(change)
        async with get_db_context() as db:
            content = await prepare_shared_mcp_content(db, UUID(validated.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_shared_mcp_preferences_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Shared preference proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid shared preference change.", error_code="INVALID_INPUT"
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Shared server unavailable.", error_code="NOT_FOUND"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return output
