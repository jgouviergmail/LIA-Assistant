"""Read session device metadata; no cookie, revocation or reauthentication material."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.session_bulk_operations import prepare_other_sessions_revocation
from src.domains.agents.application.session_operations import read_session_settings
from src.domains.agents.application.session_revocation_operations import prepare_session_revocation
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokeRequest
from src.domains.agents.application.session_schemas import DeviceSessionsRead
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.cache.session_store import SessionListingLimitError
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_device_sessions", agent_name="setting_agent")
async def get_lia_device_sessions_tool(
    query: DeviceSessionsRead | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read owned live session metadata and device names with bounded pagination.

    Args:
        query: Bounded page; pass the last shown next_cursor as cursor.
        runtime: Injected authenticated account context.

    Returns:
        Session display ids, coarse device/IP metadata, authentication tags and timestamps.
        current is null and current_session_known false without trusted origin session context.
        No raw cookie, attestation id, session credential, step-up proof or revocation.
    """
    actor = validate_runtime_config(runtime, "get_lia_device_sessions_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    try:
        request = (
            DeviceSessionsRead.model_validate(query) if query is not None else DeviceSessionsRead()
        )
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid session query.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            result = await read_session_settings(
                db,
                UUID(actor.user_id),
                request,
                origin=context.application_origin if context is not None else None,
            )
    except RedisError, SQLAlchemyError, OSError:
        return UnifiedToolOutput.failure(
            message="Session metadata unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Session metadata unavailable.", error_code=application_access_error_code(exc)
        )
    except SessionListingLimitError:
        return UnifiedToolOutput.failure(
            message="Session index exceeds the bounded read allowance. Consult the devices interface.",
            error_code="CONSTRAINT_VIOLATION",
        )
    except ValidationError:
        return UnifiedToolOutput.failure(
            message="Saved session metadata invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    except ValueError:
        return UnifiedToolOutput.failure(
            message="Session cursor unavailable. Restart at the first page.",
            error_code="INVALID_INPUT",
        )
    return UnifiedToolOutput.data_success(
        message="Owned live device sessions; follow next_cursor for further rows. If incomplete is true, invalid or mismatched indexed metadata was omitted and total counts only observed valid owned rows. Current session is unknown without trusted origin context. Revocation uses a separate confirmed flow.",
        structured_data=result.model_dump(mode="json"),
        metadata={"application_session_cursor": True},
    )


@write_tool(name="revoke_lia_device_session", agent_name="setting_agent")
async def revoke_lia_device_session_tool(
    change: DeviceSessionRevokeRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation to sign out one displayed owned session.

    Args:
        change: Opaque id returned by the session reader; never a session cookie.
        runtime: Injected account and live originating browser session.

    Returns:
        A durable original-session-bound proposal, with no revocation before approval.
        Revoking the current session can interrupt delivery; detached jobs continue.
    """
    actor = validate_runtime_config(runtime, "revoke_lia_device_session_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    if context is None:
        return UnifiedToolOutput.failure(
            message="Authenticated browser required.", error_code="FORBIDDEN"
        )
    try:
        request = DeviceSessionRevokeRequest.model_validate(change)
        async with get_db_context() as db:
            content = await prepare_session_revocation(
                db, UUID(actor.user_id), request, origin=context.application_origin
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="revoke_lia_device_session_tool",
                user_language=context.language,
            )
            await save_command(
                db, content, next(iter(output.registry_updates)), origin=context.application_origin
            )
    except RedisError, SQLAlchemyError, OSError:
        return UnifiedToolOutput.failure(
            message="Session proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Session revocation unavailable.", error_code=application_access_error_code(exc)
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Owned session unavailable.", error_code="NOT_FOUND"
        )
    except SessionListingLimitError:
        return UnifiedToolOutput.failure(
            message="Session index exceeds the bounded allowance.",
            error_code="CONSTRAINT_VIOLATION",
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid session selection.", error_code="INVALID_INPUT"
        )
    return output


@write_tool(name="revoke_lia_other_device_sessions", agent_name="setting_agent")
async def revoke_lia_other_device_sessions_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation to sign out all other sessions observed now.

    The current originating browser is kept; sessions opened later are excluded.
    Execution requires the original confirmed proposal and secure browser reauthentication.
    No revocation happens during preparation. Never pass cookies or proof through chat.
    """
    actor = validate_runtime_config(runtime, "revoke_lia_other_device_sessions_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    if context is None:
        return UnifiedToolOutput.failure(
            message="Authenticated browser required.", error_code="FORBIDDEN"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_other_sessions_revocation(
                db, UUID(actor.user_id), origin=context.application_origin
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="revoke_lia_other_device_sessions_tool",
                user_language=context.language,
            )
            await save_command(
                db, content, next(iter(output.registry_updates)), origin=context.application_origin
            )
    except RedisError, SQLAlchemyError, OSError:
        return UnifiedToolOutput.failure(
            message="Session proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Session revocation unavailable.", error_code=application_access_error_code(exc)
        )
    except SessionListingLimitError:
        return UnifiedToolOutput.failure(
            message="Session selection exceeds the bounded allowance.",
            error_code="CONSTRAINT_VIOLATION",
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Session selection is incomplete or invalid.", error_code="INVALID_INPUT"
        )
    return output
