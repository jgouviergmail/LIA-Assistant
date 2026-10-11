"""Native personalization uses the common risk policy and original domain writers."""

from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.domains.agents.application.assistant_schemas import AssistantPreferenceChange
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.preparation import (
    prepare_assistant_content,
    prepare_preference_change,
)
from src.domains.agents.application.schemas import PreferenceChangeRequest
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.database.session import get_db_context


@write_tool(name="update_lia_preferences", agent_name="setting_agent")
async def update_lia_preferences_tool(
    change: PreferenceChangeRequest,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Save reversible personalization directly; use offered IDs or displayed labels.

    Args:
        change: Explicit settings patch or a one-pixel increase/decrease of font size.
        runtime: Injected account context; identity never comes from the model.

    Returns:
        Saved values or a finite refusal. No confirmation for personalization.
    """
    return await prepare_native_tool(
        change,
        runtime,
        name="update_lia_preferences_tool",
        model=PreferenceChangeRequest,
        prepare=prepare_preference_change,
        sessions=get_db_context,
    )


@write_tool(name="update_lia_assistant_preferences", agent_name="setting_agent")
async def update_lia_assistant_preferences_tool(
    patch: AssistantPreferenceChange,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, object] | None, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Save reversible preferences; sensitive consent retains confirmation.

    Args:
        patch: Non-secret settings. Remote STT, location, health access and login
            notifications retain confirmation. Omitted fields stay unchanged.
        runtime: Injected account context.

    Returns:
        Saved values, a sensitive confirmation proposal, or a finite refusal.
    """
    return await prepare_native_tool(
        patch,
        runtime,
        name="update_lia_assistant_preferences_tool",
        model=AssistantPreferenceChange,
        prepare=prepare_assistant_content,
        sessions=get_db_context,
    )
