"""Read available choices on saved Live keys, without opening a voice session."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.live_options_operations import read_live_options
from src.domains.agents.application.live_options_schemas import LiveOptionsRead
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context
from src.infrastructure.live_connector_preferences import LiveConnectorSettingsRefused


@read_tool(name="get_lia_live_options", agent_name="setting_agent")
async def get_lia_live_options_tool(
    request: LiveOptionsRead,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read model or voice choices available to this account's saved Live providers.

    Args:
        request: Bounded models or voices page; voices require a provider. Continue with next_cursor.
        runtime: Injected authenticated account context.

    Returns:
        Declared choices, provenance and continuation; listings may consume the provider's API quota.
        A stale catalogue requires a new first page. No session, audio sample or settings write.
    """
    actor = validate_runtime_config(runtime, "get_lia_live_options_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        validated = LiveOptionsRead.model_validate(request)
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid Live page request.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            result = await read_live_options(db, UUID(actor.user_id), validated)
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Live choices unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Live management unavailable.", error_code=application_access_error_code(exc)
        )
    except LiveConnectorSettingsRefused as exc:
        return UnifiedToolOutput.failure(message="Live choices unavailable.", error_code=exc.code)
    except TimeoutError:
        return UnifiedToolOutput.failure(message="Live listing timed out.", error_code="TIMEOUT")
    except ValidationError, TypeError, ValueError:
        return UnifiedToolOutput.failure(
            message="Live catalogue unavailable or changed. Restart at the first page.",
            error_code="INVALID_RESPONSE_FORMAT",
        )
    return UnifiedToolOutput.data_success(
        message="Available Live choices. Use next_cursor to continue. Listing provenance is retained; this does not open a session or synthesize audio.",
        structured_data=result,
        metadata={"application_live_options_cursor": True},
    )
