"""Saved connection cards and mandatory confirmation for local service unlink."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.connection_operations import (
    prepare_connector_unlink_content,
    read_connector_connections,
)
from src.domains.agents.application.connection_schemas import (
    ConnectorConnectionsRead,
    ConnectorUnlinkRequest,
)
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.connectors.removal_commands import ConnectorIdentityUnavailable
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_connectors", agent_name="setting_agent")
async def get_lia_connectors_tool(
    query: ConnectorConnectionsRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read this account's saved connection cards with explicit pagination.

    Args:
        query: Selected connection or bounded page; pass next_cursor as after_id.
        runtime: Injected authenticated account context.

    Returns:
        Saved connection identities, status and timestamps. No credentials or live provider probe.
    """
    validated = validate_runtime_config(runtime, "get_lia_connectors_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        request = (
            ConnectorConnectionsRead.model_validate(query)
            if query is not None
            else ConnectorConnectionsRead()
        )
        async with get_db_context() as db:
            values = await read_connector_connections(db, UUID(validated.user_id), request)
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Saved connections unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ConnectorIdentityUnavailable:
        return UnifiedToolOutput.failure(
            message="Saved connection identity unavailable.",
            error_code=ToolErrorCode.INVALID_RESPONSE_FORMAT,
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Connection request or saved identity unavailable.", error_code="INVALID_INPUT"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return UnifiedToolOutput.data_success(
        message="Saved connection cards; follow next_cursor for all pages. Status is saved state, not a live availability check. Credentials and authorization are secure UI flows.",
        structured_data=values.model_dump(mode="json"),
        metadata={"application_connector_cursor": True},
    )


@write_tool(name="disconnect_lia_connector", agent_name="setting_agent")
async def disconnect_lia_connector_tool(
    change: ConnectorUnlinkRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation to unlink one local connection; provider consent is retained.

    Args:
        change: Existing owned connection id read from its saved card.
        runtime: Injected authenticated account context.

    Returns:
        Durable confirmation; no unlink before approval and no provider-wide revocation.
    """
    validated = validate_runtime_config(runtime, "disconnect_lia_connector_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    try:
        request = ConnectorUnlinkRequest.model_validate(change)
        async with get_db_context() as db:
            content = await prepare_connector_unlink_content(db, UUID(validated.user_id), request)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="disconnect_lia_connector_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Connection proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ConnectorIdentityUnavailable:
        return UnifiedToolOutput.failure(
            message="Saved connection identity unavailable.",
            error_code=ToolErrorCode.INVALID_RESPONSE_FORMAT,
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid connection change.", error_code="INVALID_INPUT"
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="Connection unavailable.", error_code="NOT_FOUND")
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application management unavailable.",
            error_code=application_access_error_code(exc),
        )
    return output
