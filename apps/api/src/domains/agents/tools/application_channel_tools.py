"""Read linked channels and prepare desired state; credentials and OTPs stay in secure UI flows."""

from typing import Annotated
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.channel_operations import (
    prepare_channel_binding_content,
    prepare_channel_unlink_content,
    read_channel_bindings,
)
from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkRequest,
    ChannelBindingUpdateRequest,
)
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@read_tool(name="get_lia_channel_bindings", agent_name="setting_agent")
async def get_lia_channel_bindings_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read this account's displayed channel identities and active state; no OTP or credentials.

    Args:
        runtime: Injected authenticated account context.

    Returns:
        Current linked channels as shown in the application.
    """
    validated = validate_runtime_config(runtime, "get_lia_channel_bindings_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        async with get_db_context() as db:
            values = await read_channel_bindings(db, UUID(validated.user_id))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Channel management unavailable.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError, ValidationError:
        return UnifiedToolOutput.failure(
            message="Channel state unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return UnifiedToolOutput.data_success(
        message="Current displayed channel bindings.",
        structured_data={"channels": values.model_dump(mode="json"), "total": values.total},
    )


@write_tool(name="update_lia_channel_binding", agent_name="setting_agent")
async def update_lia_channel_binding_tool(
    change: ChannelBindingUpdateRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare confirmation for one owned channel's desired active state.

    Args:
        change: Binding selected from current reads and its desired state, never a blind toggle.
        runtime: Injected authenticated account context.

    Returns:
        Exact durable human confirmation; no channel change before approval.
    """
    return await _prepare_channel_draft(change, runtime, unlink=False)


@write_tool(name="unlink_lia_channel_binding", agent_name="setting_agent")
async def unlink_lia_channel_binding_tool(
    binding: ChannelBindingUnlinkRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation to remove one owned external messaging binding.

    Args:
        binding: Current owned binding id selected from a channel read.
        runtime: Injected authenticated account context.

    Returns:
        Destructive confirmation; removal happens only after approval. Re-linking uses the secure UI.
    """
    return await _prepare_channel_draft(binding, runtime, unlink=True)


async def _prepare_channel_draft(
    change: object, runtime: ToolRuntime[LiaRuntimeContext, object] | None, *, unlink: bool
) -> UnifiedToolOutput:
    source_tool = "unlink_lia_channel_binding_tool" if unlink else "update_lia_channel_binding_tool"
    validated = validate_runtime_config(runtime, source_tool)
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    try:
        async with get_db_context() as db:
            if unlink:
                removal = ChannelBindingUnlinkRequest.model_validate(change)
                content = await prepare_channel_unlink_content(db, UUID(validated.user_id), removal)
            else:
                request = ChannelBindingUpdateRequest.model_validate(change)
                content = await prepare_channel_binding_content(
                    db, UUID(validated.user_id), request
                )
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool=source_tool,
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid channel change.", error_code="INVALID_INPUT"
        )
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(
            message="Channel binding unavailable.", error_code="NOT_FOUND"
        )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Channel management unavailable.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="The proposal could not be persisted.", error_code="DEPENDENCY_ERROR"
        )
    return output
