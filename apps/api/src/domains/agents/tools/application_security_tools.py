"""Read the account's reviewed security state without credentials or secure ceremonies."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.security_operations import read_security_settings
from src.domains.agents.application.security_schemas import SecurityRead
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_security_settings", agent_name="setting_agent")
async def get_lia_security_settings_tool(
    query: SecurityRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read authentication features, password-enabled state, TOTP and owned passkey metadata.

    Args:
        query: Overview, TOTP status or bounded passkey page; continue with next_cursor as cursor.
        runtime: Injected authenticated account context.

    Returns:
        Public security status only. MFA_DISABLED makes hidden state unavailable, not inactive.
        Available methods are not proof of reauthentication. Freshness is observed from a live
        authenticated transport session, or unknown when no such session was injected.
        No key, credential id, OTP, recovery code, password or authentication ceremony.
    """
    actor = validate_runtime_config(runtime, "get_lia_security_settings_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    try:
        request = SecurityRead.model_validate(query) if query is not None else SecurityRead()
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid security read request.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            result = await read_security_settings(
                db,
                UUID(actor.user_id),
                request,
                origin=context.application_origin if context is not None else None,
            )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Security state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Security state unavailable.", error_code=application_access_error_code(exc)
        )
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Saved security state unavailable.", error_code="INVALID_RESPONSE_FORMAT"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Passkey cursor unavailable. Restart at the first page.",
            error_code="INVALID_INPUT",
        )
    return UnifiedToolOutput.data_success(
        message="Account security state and passkey metadata. Follow next_cursor as cursor for all passkeys. Enrollment, revocation, recovery-code regeneration, password changes and device sessions use separate secure flows.",
        structured_data=result.model_dump(mode="json"),
        metadata={"application_passkey_cursor": True},
    )
