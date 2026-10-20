"""SMS settings tools only prepare source-owned exact approval drafts."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import JsonValue, TypeAdapter, ValidationError
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.sms_action_schemas import (
    SmsTokenCreateRequest,
    SmsTokenRevokeRequest,
)
from src.domains.agents.application.sms_actions import prepare_sms_action
from src.domains.agents.application.sms_manifests import SMS_REQUEST_MODELS
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.sms.management_schemas import SmsEraseRequest
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.sender_commands import SmsSenderBlockRequest
from src.infrastructure.database.session import get_db_context

_JSON = TypeAdapter(dict[str, JsonValue])


async def _proposal(
    request: object,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    operation: str,
    tool_name: str,
) -> UnifiedToolOutput:
    actor = validate_runtime_config(runtime, tool_name)
    if isinstance(actor, UnifiedToolOutput):
        return actor
    context = tool_runtime_context(runtime)
    if context is None:
        return UnifiedToolOutput.failure(
            message="Authenticated context required.", error_code="FORBIDDEN"
        )
    try:
        selected = SMS_REQUEST_MODELS[operation].model_validate(request)
        async with get_db_context() as db:
            draft = await prepare_sms_action(
                db,
                UUID(actor.user_id),
                operation,
                _JSON.validate_python(selected.model_dump(mode="json")),
                origin=context.application_origin,
            )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=draft.model_dump(mode="json"),
                source_tool=tool_name,
                user_language=context.language,
            )
            await save_command(
                db, draft, next(iter(output.registry_updates)), origin=context.application_origin
            )
    except AuthorizationError as error:
        return UnifiedToolOutput.failure(
            message="SMS management access refused.",
            error_code=application_access_error_code(error),
        )
    except ResourceNotFoundError, ResourceConflictError:
        return UnifiedToolOutput.failure(
            message="SMS selection changed or unavailable.", error_code="STALE_STATE"
        )
    except SQLAlchemyError, RedisError, OSError, TimeoutError:
        return UnifiedToolOutput.failure(
            message="SMS proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except CommandRejected, ValidationError, ValueError:
        return UnifiedToolOutput.failure(message="Invalid SMS scope.", error_code="INVALID_INPUT")
    return output


@write_tool(name="create_lia_sms_ingestion_token", agent_name="setting_agent")
async def create_lia_sms_ingestion_token_tool(
    request: SmsTokenCreateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for sms_token.create without performing the action.

    Args:
        request: Exact requested source scope; no approval or authority.
        runtime: Injected authenticated context.

    Returns:
        Pending non-secret approval or a bounded refusal.
    """
    return await _proposal(
        request, runtime, "sms_token.create", "create_lia_sms_ingestion_token_tool"
    )


@write_tool(name="revoke_lia_sms_ingestion_token", agent_name="setting_agent")
async def revoke_lia_sms_ingestion_token_tool(
    request: SmsTokenRevokeRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for sms_token.revoke without performing the action.

    Args:
        request: Exact requested source scope; no approval or authority.
        runtime: Injected authenticated context.

    Returns:
        Pending non-secret approval or a bounded refusal.
    """
    return await _proposal(
        request, runtime, "sms_token.revoke", "revoke_lia_sms_ingestion_token_tool"
    )


@write_tool(name="update_lia_sms_preferences", agent_name="setting_agent")
async def update_lia_sms_preferences_tool(
    request: SmsPreferences,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for sms_preferences.update without performing the action.

    Args:
        request: Exact requested source scope; no approval or authority.
        runtime: Injected authenticated context.

    Returns:
        Pending non-secret approval or a bounded refusal.
    """
    return await _proposal(
        request, runtime, "sms_preferences.update", "update_lia_sms_preferences_tool"
    )


@write_tool(name="set_lia_sms_sender_block", agent_name="setting_agent")
async def set_lia_sms_sender_block_tool(
    request: SmsSenderBlockRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for sms_sender_block.update without performing the action.

    Args:
        request: Exact requested source scope; no approval or authority.
        runtime: Injected authenticated context.

    Returns:
        Pending non-secret approval or a bounded refusal.
    """
    return await _proposal(
        request, runtime, "sms_sender_block.update", "set_lia_sms_sender_block_tool"
    )


@write_tool(name="delete_lia_sms", agent_name="setting_agent")
async def delete_lia_sms_tool(
    request: SmsEraseRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for sms_messages.delete without performing the action.

    Args:
        request: Exact requested source scope; no approval or authority.
        runtime: Injected authenticated context.

    Returns:
        Pending non-secret approval or a bounded refusal.
    """
    return await _proposal(request, runtime, "sms_messages.delete", "delete_lia_sms_tool")
