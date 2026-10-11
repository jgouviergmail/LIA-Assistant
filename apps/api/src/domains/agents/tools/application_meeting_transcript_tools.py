"""Transcript purges always prepare the existing HITL workflow first."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.meeting_transcript_removal import prepare_transcript_deletion
from src.domains.agents.application.meeting_transcript_schemas import TranscriptDeleteInput
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context

TranscriptRuntime = ToolRuntime[LiaRuntimeContext, object] | None


@write_tool(name="delete_lia_meeting_transcript", agent_name="setting_agent")
async def delete_lia_meeting_transcript_tool(
    request: TranscriptDeleteInput, runtime: Annotated[TranscriptRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose a transcript purge while preserving the minutes and retained audio.

    Args:
        request: The exact owned meeting identifier.
        runtime: Injected authenticated account context.

    Returns:
        Mandatory original HITL; nothing is deleted before confirmation.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="delete_lia_meeting_transcript_tool",
        model=TranscriptDeleteInput,
        prepare=prepare_transcript_deletion,
        sessions=get_db_context,
    )
