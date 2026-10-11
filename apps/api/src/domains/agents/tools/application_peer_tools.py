"""Current-account connection controls travel through native authorization contracts."""

from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import application_access_error_code
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_block import prepare_peer_block
from src.domains.agents.application.peer_block_schemas import PeerBlockInput
from src.domains.agents.application.peer_discovery import search_peer_directory
from src.domains.agents.application.peer_discovery_schemas import PeerDiscoveryQuery
from src.domains.agents.application.peer_image import prepare_peer_image
from src.domains.agents.application.peer_image_schemas import PeerImageInput
from src.domains.agents.application.peer_preference_schemas import PeerPreferencePatch
from src.domains.agents.application.peer_preferences import prepare_peer_preferences
from src.domains.agents.application.peer_read import read_peer_ui
from src.domains.agents.application.peer_read_schemas import PeerUIQuery
from src.domains.agents.application.peer_removal import prepare_peer_removal
from src.domains.agents.application.peer_removal_schemas import PeerRemovalInput
from src.domains.agents.application.peer_request import prepare_peer_request
from src.domains.agents.application.peer_request_schemas import PeerRequestInput
from src.domains.agents.application.peer_response import prepare_peer_response
from src.domains.agents.application.peer_response_schemas import PeerResponseInput
from src.domains.agents.application.peer_share import prepare_peer_share
from src.domains.agents.application.peer_share_schemas import PeerShareInput
from src.domains.agents.application.peer_tool_preparation import prepare_peer_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.infrastructure.database.session import get_db_context


@write_tool(name="share_lia_peer_image", agent_name="setting_agent")
async def share_lia_peer_image_tool(
    request: PeerImageInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation to copy an owned generated image to a connection.

    Args:
        request: Actual connection and image IDs plus optional literal comment.
        runtime: Injected authenticated account context.

    Returns:
        Pending mandatory confirmation; no copy or delivery during preparation.
    """
    return await prepare_peer_tool(
        request,
        runtime,
        name="share_lia_peer_image_tool",
        model=PeerImageInput,
        prepare=prepare_peer_image,
        sessions=get_db_context,
    )


@write_tool(name="update_lia_peer_block", agent_name="setting_agent")
async def update_lia_peer_block_tool(
    request: PeerBlockInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact silent block or non-restoring unblock confirmation.

    Args:
        request: Known Connections peer ID and explicit blocked boolean.
        runtime: Injected authenticated account context.

    Returns:
        Pending directional consent; no blocking, restoration or notification.
    """
    return await prepare_peer_tool(
        request,
        runtime,
        name="update_lia_peer_block_tool",
        model=PeerBlockInput,
        prepare=prepare_peer_block,
        sessions=get_db_context,
    )


@write_tool(name="remove_lia_peer_connection", agent_name="setting_agent")
async def remove_lia_peer_connection_tool(
    request: PeerRemovalInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact severance confirmation including both directions of sharing.

    Args:
        request: Explicit accepted connection ID.
        runtime: Injected authenticated account context.

    Returns:
        Pending confirmation; no removal, ticket release or notification.
    """
    return await prepare_peer_tool(
        request,
        runtime,
        name="remove_lia_peer_connection_tool",
        model=PeerRemovalInput,
        prepare=prepare_peer_removal,
        sessions=get_db_context,
    )


@write_tool(name="update_lia_peer_share", agent_name="setting_agent")
async def update_lia_peer_share_tool(
    request: PeerShareInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for one owned read-only calendar/task share.

    Args:
        request: Connection ID, domain and explicit level or null to revoke.
        runtime: Injected authenticated account context.

    Returns:
        Pending own-share consent, with no mutation or provider fetch.
    """
    return await prepare_peer_tool(
        request,
        runtime,
        name="update_lia_peer_share_tool",
        model=PeerShareInput,
        prepare=prepare_peer_share,
        sessions=get_db_context,
    )


@write_tool(name="respond_lia_peer_request", agent_name="setting_agent")
async def respond_lia_peer_request_tool(
    request: PeerResponseInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact confirmation for an owned incoming invitation's accept/refuse choice.

    Args:
        request: Incoming connection ID and explicit accept boolean.
        runtime: Injected authenticated account context.

    Returns:
        Pending response confirmation; no transition or notification.
    """
    return await prepare_peer_tool(
        request,
        runtime,
        name="respond_lia_peer_request_tool",
        model=PeerResponseInput,
        prepare=prepare_peer_response,
        sessions=get_db_context,
    )


@write_tool(name="request_lia_peer_connection", agent_name="setting_agent")
async def request_lia_peer_connection_tool(
    request: PeerRequestInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact invitation or crossing acceptance confirmation, with no send.

    Args:
        request: Explicit selected discoverable peer identity and optional literal note.
        runtime: Injected authenticated account context.

    Returns:
        Pending exact target/state confirmation; no request or notice created.
    """
    return await prepare_peer_tool(
        request,
        runtime,
        name="request_lia_peer_connection_tool",
        model=PeerRequestInput,
        prepare=prepare_peer_request,
        sessions=get_db_context,
    )


@read_tool(name="search_lia_peer_directory", agent_name="setting_agent")
async def search_lia_peer_directory_tool(
    query: PeerDiscoveryQuery,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read exact opt-in peer matches through source anti-enumeration controls.

    Args:
        query: Exact full name or email and optional bounded live page.
        runtime: Injected authenticated account context.

    Returns:
        Masked public source matches only; no invitation or account mutation.
    """
    actor = validate_runtime_config(runtime, "search_lia_peer_directory_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        selected = PeerDiscoveryQuery.model_validate(query)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid exact directory query.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            observed = await search_peer_directory(db, UUID(actor.user_id), selected)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Peer directory unavailable.", error_code=application_access_error_code(exc)
        )
    except CommandRejected as exc:
        return UnifiedToolOutput.failure(
            message="Peer directory quota unavailable.", error_code=exc.code
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Peer directory read failed.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Peer directory response invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return UnifiedToolOutput.data_success(
        message="Observed exact opt-in directory matches only. Masked hints distinguish candidates; no invitation sent. These are live observations, not account identity verification.",
        structured_data=observed.model_dump(mode="json"),
    )


@write_tool(name="update_lia_peer_settings", agent_name="setting_agent")
async def update_lia_peer_settings_tool(
    patch: PeerPreferencePatch,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact human confirmation for explicitly selected independent consents.

    Args:
        patch: Sparse explicit discoverability and/or address visibility booleans.
        runtime: Injected authenticated account context.

    Returns:
        Pending before/after consent confirmation; no mutation.
    """
    actor = validate_runtime_config(runtime, "update_lia_peer_settings_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    assert runtime is not None
    try:
        selected = PeerPreferencePatch.model_validate(patch)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid peer consent patch.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            content = await prepare_peer_preferences(db, UUID(actor.user_id), selected)
            output = DraftService().create_draft(
                draft_type=DraftType.APPLICATION_ACTION,
                content=content.model_dump(mode="json"),
                source_tool="update_lia_peer_settings_tool",
                user_language=runtime.context.language,
            )
            await save_command(db, content, next(iter(output.registry_updates)))
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Peer consent proposal refused.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Peer consent proposal unavailable.", error_code="DEPENDENCY_ERROR"
        )
    return output


@read_tool(name="get_lia_peer_settings", agent_name="setting_agent")
async def get_lia_peer_settings_tool(
    query: PeerUIQuery | None = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read one source Connections settings section without any action.

    Args:
        query: Optional finite section and bounded live pagination.
        runtime: Injected authenticated account context.

    Returns:
        Owned source preferences, invitations, connections, blocks, audit or relay page.
    """
    actor = validate_runtime_config(runtime, "get_lia_peer_settings_tool")
    if isinstance(actor, UnifiedToolOutput):
        return actor
    try:
        selected = PeerUIQuery() if query is None else PeerUIQuery.model_validate(query)
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Invalid connection UI query.", error_code="INVALID_INPUT"
        )
    try:
        async with get_db_context() as db:
            observed = await read_peer_ui(db, UUID(actor.user_id), selected)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Connection UI unavailable.", error_code=application_access_error_code(exc)
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Connection source read failed.", error_code="DEPENDENCY_ERROR"
        )
    except ValidationError, ValueError:
        return UnifiedToolOutput.failure(
            message="Connection UI response invalid.", error_code="INVALID_RESPONSE_FORMAT"
        )
    return UnifiedToolOutput.data_success(
        message="Observed current-account Connections UI page. Consent and note direction are source authority. Null total is unknown full history; pages are live observations, not a frozen export. No action performed.",
        structured_data=observed.model_dump(mode="json"),
    )
