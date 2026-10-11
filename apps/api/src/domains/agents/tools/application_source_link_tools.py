"""Prepare mandatory exact human approval for an automatic Drive/Gmail source link."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.source_link import prepare_source_link
from src.domains.agents.application.source_link_schemas import SourceLinkInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context


@write_tool(name="link_lia_knowledge_source", agent_name="setting_agent")
async def link_lia_knowledge_source_tool(
    request: SourceLinkInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare a standing source-link approval; metadata reads do not import or index.

    Args:
        request: Real owned space, Drive folder or Gmail user-label identity.
        runtime: Injected current-account context.

    Returns:
        Durable native HITL draft with actual provider name and ongoing-sync/cost disclosure.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="link_lia_knowledge_source_tool",
        model=SourceLinkInput,
        prepare=prepare_source_link,
        sessions=get_db_context,
    )
