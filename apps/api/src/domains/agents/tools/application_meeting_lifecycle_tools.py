"""Owned workflow proposals use the original account HITL command lifecycle."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.meeting_deletion import prepare_meeting_deletion
from src.domains.agents.application.meeting_deletion_schemas import MeetingDeletionInput
from src.domains.agents.application.meeting_reformat import prepare_meeting_reformat
from src.domains.agents.application.meeting_reformat_schemas import MeetingReformatInput
from src.domains.agents.application.meeting_regeneration import prepare_meeting_regeneration
from src.domains.agents.application.meeting_regeneration_schemas import MeetingRegenerationInput
from src.domains.agents.application.meeting_retry import prepare_meeting_retry
from src.domains.agents.application.meeting_retry_schemas import MeetingRetryInput
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context

LifecycleRuntime = ToolRuntime[LiaRuntimeContext, object] | None


@write_tool(name="retry_lia_meeting", agent_name="setting_agent")
async def retry_lia_meeting_tool(
    request: MeetingRetryInput, runtime: Annotated[LifecycleRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose retrying the original potentially paid meeting processing workflow.

    Args:
        request: Exact owned stopped/failed meeting identifier.
        runtime: Injected authenticated account context.

    Returns:
        Original mandatory HITL proposal, never completed processing.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="retry_lia_meeting_tool",
        model=MeetingRetryInput,
        prepare=prepare_meeting_retry,
        sessions=get_db_context,
    )


@write_tool(name="regenerate_lia_meeting_report", agent_name="setting_agent")
async def regenerate_lia_meeting_report_tool(
    request: MeetingRegenerationInput, runtime: Annotated[LifecycleRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose rebuilding all minutes from the owned retained transcript.

    Args:
        request: Exact owned ready and idle meeting identifier.
        runtime: Injected authenticated account context.

    Returns:
        Original mandatory HITL proposal, never completed processing.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="regenerate_lia_meeting_report_tool",
        model=MeetingRegenerationInput,
        prepare=prepare_meeting_regeneration,
        sessions=get_db_context,
    )


@write_tool(name="reformat_lia_meeting_report", agent_name="setting_agent")
async def reformat_lia_meeting_report_tool(
    request: MeetingReformatInput, runtime: Annotated[LifecycleRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose changing the minutes template in place or as separate new minutes.

    Args:
        request: Exact owned ready meeting, selected template and replace/new mode.
        runtime: Injected authenticated account context.

    Returns:
        Original mandatory HITL proposal, never completed processing.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="reformat_lia_meeting_report_tool",
        model=MeetingReformatInput,
        prepare=prepare_meeting_reformat,
        sessions=get_db_context,
    )


@write_tool(name="delete_lia_meeting", agent_name="setting_agent")
async def delete_lia_meeting_tool(
    request: MeetingDeletionInput, runtime: Annotated[LifecycleRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose deleting the complete owned meeting and its projection.

    Args:
        request: Exact owned non-live meeting identifier.
        runtime: Injected authenticated account context.

    Returns:
        Original mandatory HITL proposal, never a deletion before confirmation.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="delete_lia_meeting_tool",
        model=MeetingDeletionInput,
        prepare=prepare_meeting_deletion,
        sessions=get_db_context,
    )
