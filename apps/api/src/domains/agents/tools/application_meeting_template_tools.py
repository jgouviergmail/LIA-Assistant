"""Template library mutations always prepare the original exact HITL workflow."""

from typing import Annotated

from langchain_core.tools import InjectedToolArg
from langgraph.prebuilt import ToolRuntime

from src.domains.agents.application.meeting_template_preparation import (
    prepare_template_creation,
    prepare_template_removal,
    prepare_template_replacement,
)
from src.domains.agents.application.meeting_template_schemas import (
    TemplateCreateInput,
    TemplateDeleteInput,
    TemplateUpdateInput,
)
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context

TemplateRuntime = ToolRuntime[LiaRuntimeContext, object] | None


@write_tool(name="create_lia_meeting_template", agent_name="setting_agent")
async def create_lia_meeting_template_tool(
    request: TemplateCreateInput, runtime: Annotated[TemplateRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose a new owned template or an exact copy, without saving.

    Args:
        request: Original creation fields; either sections/name or an exact source ref.
        runtime: Injected authenticated current account.

    Returns:
        Original HITL showing the resolved copied name, content and quota.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="create_lia_meeting_template_tool",
        model=TemplateCreateInput,
        prepare=prepare_template_creation,
        sessions=get_db_context,
    )


@write_tool(name="update_lia_meeting_template", agent_name="setting_agent")
async def update_lia_meeting_template_tool(
    request: TemplateUpdateInput, runtime: Annotated[TemplateRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose only requested changes to an owned template, retaining all other fields.

    Args:
        request: Exact owned ref and sparse changes; builtins are readonly.
        runtime: Injected authenticated current account.

    Returns:
        Original HITL for the complete before/after template content.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="update_lia_meeting_template_tool",
        model=TemplateUpdateInput,
        prepare=prepare_template_replacement,
        sessions=get_db_context,
    )


@write_tool(name="delete_lia_meeting_template", agent_name="setting_agent")
async def delete_lia_meeting_template_tool(
    request: TemplateDeleteInput, runtime: Annotated[TemplateRuntime, InjectedToolArg] = None
) -> UnifiedToolOutput:
    """Propose an owned library deletion including any default-format reset.

    Args:
        request: Exact owned template ref; builtins are readonly.
        runtime: Injected authenticated current account.

    Returns:
        Original HITL; no library/default preference change before approval.
    """
    return await prepare_native_tool(
        request,
        runtime,
        name="delete_lia_meeting_template_tool",
        model=TemplateDeleteInput,
        prepare=prepare_template_removal,
        sessions=get_db_context,
    )
