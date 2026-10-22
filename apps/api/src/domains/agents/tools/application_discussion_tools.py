"""Private native discussion settings/context tools, shared by Pipeline and ReAct."""

from datetime import UTC, datetime
from functools import partial
from typing import Annotated
from uuid import UUID

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.availability import (
    application_access_error_code,
    require_application_tools,
)
from src.domains.agents.application.discussion_commands import prepare_discussion_action
from src.domains.agents.application.discussion_schemas import (
    DiscussionDetailsRequest,
    DiscussionPageRequest,
    DiscussionPreferencesIntent,
    DiscussionPurgeIntent,
    DiscussionRebuildIntent,
    DiscussionUseIntent,
)
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.openings import (
    OpeningPageRequest,
    get_opening,
    list_openings,
)
from src.domains.proactive_discussions.settings_service import read_settings
from src.infrastructure.database.session import get_db_context


async def _read(
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    request: DiscussionPageRequest | OpeningPageRequest | DiscussionDetailsRequest | None,
    *,
    name: str | None = None,
) -> UnifiedToolOutput:
    validated = validate_runtime_config(
        runtime,
        name
        or ("get_lia_discussion_context_tool" if request else "get_lia_proactive_discussions_tool"),
    )
    if isinstance(validated, UnifiedToolOutput):
        return validated
    try:
        async with get_db_context() as db:
            await require_application_tools(db)
            owner = UUID(str(validated.user_id))
            if isinstance(request, OpeningPageRequest):
                result = await list_openings(db, owner, request)
            elif isinstance(request, DiscussionDetailsRequest):
                result = await get_opening(db, owner, request.opening_id)
            elif request is None:
                result = await read_settings(db, owner)
            else:
                result = await ContextRepository(db).read_generation(
                    owner,
                    now=datetime.now(UTC),
                    limit=request.limit,
                    after_id=request.after_id,
                    after_exclusion_id=request.after_exclusion_id,
                    filters=request.filters,
                )
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Discussion controls access refused.",
            error_code=application_access_error_code(exc),
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Discussion controls unavailable.", error_code="DEPENDENCY_ERROR"
        )
    except ValueError, ValidationError:
        return UnifiedToolOutput.failure(
            message="Invalid context selection.", error_code="INVALID_INPUT"
        )
    return UnifiedToolOutput.data_success(
        message="Current private discussion controls.",
        structured_data={"data": result.model_dump(mode="json")},
    )


@read_tool(name="get_lia_proactive_discussions", agent_name="setting_agent")
async def get_lia_proactive_discussions_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read current discussion settings and producer/budget availability.

    Args:
        runtime: Injected current-account context.

    Returns:
        Private saved settings without starting work.
    """
    return await _read(runtime, None)


@read_tool(name="get_lia_discussion_context", agent_name="setting_agent")
async def get_lia_discussion_context_tool(
    request: DiscussionPageRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read one context and exclusion page with proof/retention metadata.

    Args:
        request: Bounded owner-scoped cursors.
        runtime: Injected authenticated account.

    Returns:
        Derived observations, episodes, patterns and non-usable choices.
    """
    return await _read(runtime, request)


@write_tool(name="update_lia_proactive_discussions", agent_name="setting_agent")
async def update_lia_proactive_discussions_tool(
    request: DiscussionPreferencesIntent,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact approval for explicit personal discussion preferences.

    Args:
        request: Exact selected scope, never authority or approval.
        runtime: Injected authenticated account.

    Returns:
        Native pending human confirmation; no mutation during preparation.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="update_lia_proactive_discussions_tool",
        model=DiscussionPreferencesIntent,
        prepare=partial(prepare_discussion_action, operation="proactive_discussions.update"),
        sessions=get_db_context,
    )


@write_tool(name="set_lia_discussion_context_use", agent_name="setting_agent")
async def set_lia_discussion_context_use_tool(
    request: DiscussionUseIntent,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact approval to exclude or restore one owned context item.

    Args:
        request: Exact selected scope, never authority or approval.
        runtime: Injected authenticated account.

    Returns:
        Native pending human confirmation; no mutation during preparation.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="set_lia_discussion_context_use_tool",
        model=DiscussionUseIntent,
        prepare=partial(prepare_discussion_action, operation="discussion_context.use"),
        sessions=get_db_context,
    )


@write_tool(name="purge_lia_discussion_context", agent_name="setting_agent")
async def purge_lia_discussion_context_tool(
    request: DiscussionPurgeIntent,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact approval for a precisely snapshotted derived-context purge.

    Args:
        request: Exact selected scope, never authority or approval.
        runtime: Injected authenticated account.

    Returns:
        Native pending human confirmation; no mutation during preparation.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="purge_lia_discussion_context_tool",
        model=DiscussionPurgeIntent,
        prepare=partial(prepare_discussion_action, operation="discussion_context.purge"),
        sessions=get_db_context,
    )


@write_tool(name="rebuild_lia_discussion_context", agent_name="setting_agent")
async def rebuild_lia_discussion_context_tool(
    request: DiscussionRebuildIntent,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare exact approval to request a later bounded context reconstruction.

    Args:
        request: Exact selected scope, never authority or approval.
        runtime: Injected authenticated account.

    Returns:
        Native pending human confirmation; no mutation during preparation.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="rebuild_lia_discussion_context_tool",
        model=DiscussionRebuildIntent,
        prepare=partial(prepare_discussion_action, operation="discussion_context.rebuild"),
        sessions=get_db_context,
    )


@read_tool(name="list_lia_discussions", agent_name="setting_agent")
async def list_lia_discussions_tool(
    request: OpeningPageRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read the owner's real archived personal openings and exact page total.

    Args:
        request: Closed page selection, never an account identity.
        runtime: Injected authenticated account.

    Returns:
        Private archived openings, without starting new discussions.
    """
    return await _read(runtime, request, name="list_lia_discussions_tool")


@read_tool(name="get_lia_discussion_details", agent_name="setting_agent")
async def get_lia_discussion_details_tool(
    request: DiscussionDetailsRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read one owned visible opening and its explicit feedback.

    Args:
        request: Stable opening identity, never account authority.
        runtime: Injected authenticated account.

    Returns:
        The real archived message and feedback, with no internal reasoning.
    """
    return await _read(runtime, request, name="get_lia_discussion_details_tool")
