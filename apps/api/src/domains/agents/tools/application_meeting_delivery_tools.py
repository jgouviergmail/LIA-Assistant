"""Original delivery proposals never render or send before exact confirmation."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.meeting_email_schemas import MeetingEmailInput
from src.domains.agents.application.meeting_email_send import prepare_meeting_email
from src.domains.agents.application.meeting_pdf_download import prepare_meeting_pdf
from src.domains.agents.application.meeting_pdf_schemas import MeetingPDFInput
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context

DeliveryRuntime = ToolRuntime[LiaRuntimeContext, object] | None


@write_tool(name="email_lia_meeting_report", agent_name="setting_agent")
async def email_lia_meeting_report_tool(
    request: MeetingEmailInput, runtime: Annotated[DeliveryRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose one complete current-minutes email to the account's own address.

    Args:
        request: Exact owned ready meeting identifier.
        runtime: Injected authenticated account context.

    Returns:
        Original mandatory HITL proposal; no email has been sent yet.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="email_lia_meeting_report_tool",
        model=MeetingEmailInput,
        prepare=prepare_meeting_email,
        sessions=get_db_context,
    )


@write_tool(name="download_lia_meeting_pdf", agent_name="setting_agent")
async def download_lia_meeting_pdf_tool(
    request: MeetingPDFInput, runtime: Annotated[DeliveryRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose a whole owned current-minutes PDF in the original browser.

    Args:
        request: Exact owned ready meeting identifier.
        runtime: Injected authenticated original-browser account context.

    Returns:
        Original HITL proposal; no rendering or download has happened yet.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="download_lia_meeting_pdf_tool",
        model=MeetingPDFInput,
        prepare=prepare_meeting_pdf,
        sessions=get_db_context,
    )
