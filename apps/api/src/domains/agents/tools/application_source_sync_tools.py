"""Prepare original native HITL approval for one owned manual source synchronization."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.source_sync import prepare_source_sync
from src.domains.agents.application.source_sync_schemas import SourceSyncInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context


@write_tool(name="sync_lia_knowledge_source", agent_name="setting_agent")
async def sync_lia_knowledge_source_tool(
    request: SourceSyncInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose bounded synchronization; acceptance is never proof of finished indexing.

    Args:
        request: Exact real owned destination, linked source identity and kind.
        runtime: Injected authenticated current-account context.

    Returns:
        Durable HITL draft stating replacement/removal scope, quotas and indexing costs.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="sync_lia_knowledge_source_tool",
        model=SourceSyncInput,
        prepare=prepare_source_sync,
        sessions=get_db_context,
    )
