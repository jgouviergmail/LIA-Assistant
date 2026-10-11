"""Prepare native human confirmation for source removal with document retention."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.source_unlink import prepare_source_unlink
from src.domains.agents.application.source_unlink_schemas import SourceUnlinkInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context


@write_tool(name="unlink_lia_knowledge_source", agent_name="setting_agent")
async def unlink_lia_knowledge_source_tool(
    request: SourceUnlinkInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare one exact owned source unlink; documents always remain.

    Args:
        request: Real owned space/source identity and Drive or mail source kind.
        runtime: Injected current-account context.

    Returns:
        A durable mandatory approval draft, without provider, file or source writes.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="unlink_lia_knowledge_source_tool",
        model=SourceUnlinkInput,
        prepare=prepare_source_unlink,
        sessions=get_db_context,
    )
