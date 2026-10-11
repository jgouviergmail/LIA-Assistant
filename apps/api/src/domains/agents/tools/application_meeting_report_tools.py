"""Minutes version actions prepare the original HITL workflow before writing."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.meeting_report_restoration import prepare_report_restoration
from src.domains.agents.application.meeting_report_restore_schemas import ReportRestoreInput
from src.domains.agents.application.meeting_report_update_schemas import ReportUpdateInput
from src.domains.agents.application.meeting_report_updating import prepare_report_update
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context

ReportRuntime = ToolRuntime[LiaRuntimeContext, object] | None


@write_tool(name="restore_lia_meeting_report", agent_name="setting_agent")
async def restore_lia_meeting_report_tool(
    request: ReportRestoreInput, runtime: Annotated[ReportRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose restoration of one exact whole generated minutes version.

    Args:
        request: Exact owned meeting identifier.
        runtime: Injected authenticated current account.

    Returns:
        Original HITL with bounded scope metadata and a sealed full version.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="restore_lia_meeting_report_tool",
        model=ReportRestoreInput,
        prepare=prepare_report_restoration,
        sessions=get_db_context,
    )


@write_tool(name="update_lia_meeting_report", agent_name="setting_agent")
async def update_lia_meeting_report_tool(
    request: ReportUpdateInput,
    runtime: Annotated[ReportRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose original sparse report edits, with literal before/after HITL.

    Args:
        request: Exact owned meeting and explicitly selected original fields.
        runtime: Injected authenticated account.

    Returns:
        Pending confirmation; no report is written until exact consent.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="update_lia_meeting_report_tool",
        model=ReportUpdateInput,
        prepare=prepare_report_update,
        sessions=get_db_context,
    )
