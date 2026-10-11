"""Original human approval stops one source and removes its indexed documents."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.source_delete import prepare_source_deletion
from src.domains.agents.application.source_delete_schemas import SourceDeleteInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context


@write_tool(name="delete_lia_knowledge_source", agent_name="setting_agent")
async def delete_lia_knowledge_source_tool(
    request: SourceDeleteInput,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Propose source/document destruction; files await known SQL acknowledgement.

    Args:
        request: Exact real owned space, linked source id and drive/mail kind.
        runtime: Injected authenticated current-account context.

    Returns:
        Durable HITL draft with the whole exact indexed-document selection.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="delete_lia_knowledge_source_tool",
        model=SourceDeleteInput,
        prepare=prepare_source_deletion,
        sessions=get_db_context,
    )
