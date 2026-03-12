"""
Contacts Agent Builder (LangChain v1.0) - Refactored with Generic Template.

Builds a compiled LangChain v1 agent for Google Contacts operations using the
generic agent builder template for consistency and maintainability.

This file demonstrates how to use the generic template for rapid agent creation.
For creating new agents (Gmail, Calendar, Tasks), follow this pattern.

Migration Note:
    This file was refactored during Phase 3 of the LangGraph v1.0 cleanup to use
    the generic agent builder template (base_agent_builder.py). The previous
    implementation had ~150 lines of boilerplate that is now centralized.

    Lines Before: ~150
    Lines After: ~80
    Reduction: -47%
"""

from typing import Any

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.domains.agents.prompts import load_prompt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def build_contacts_agent() -> Any:
    """
    Build and compile the contacts agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Google Contacts tools (search, list, get_details)
    - Context resolution tools (resolve_reference, set_current_item, etc.)
    - HITL middleware for tool approval
    - Pre-model hook for message history management
    - LLM configuration from settings

    Architecture (LangChain v1.0 ReAct):
        Agent Loop (internal to create_agent):
        1. LLM generates tool_calls
        2. HumanInTheLoopMiddleware intercepts (if tool matches pattern)
        3. Middleware emits interrupt() → pauses graph
        4. User approves via Command(resume={"decisions": [...]})
        5. Middleware processes decision (approve/edit/reject)
        6. Tools execute (if approved)
        7. Agent receives results and continues

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.

    Example Usage:
        >>> # In graph.py:
        >>> contacts_agent = build_contacts_agent()
        >>> async def contacts_agent_node(state, config):
        ...     result = await contacts_agent.ainvoke(state, config)
        ...     return {"messages": result["messages"], "agent_results": {...}}
        >>> graph.add_node("contacts_agent", contacts_agent_node)
        >>> compiled_graph = graph.compile(checkpointer=checkpointer, store=store)

    Note:
        This function now delegates to build_generic_agent() with contacts-specific
        configuration. The generic template handles all boilerplate (HITL, pre-model
        hook, LLM config, etc.).
    """
    logger.info("building_contacts_agent_with_generic_template")

    # Import all tools (migrated to ToolRuntime pattern)
    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.context_tools import (
        get_context_list,
        get_context_state,
        list_active_domains,
        resolve_reference,
        set_current_item,
    )
    from src.domains.agents.tools.google_contacts_tools import (
        create_contact_tool,
        delete_contact_tool,
        get_contacts_tool,  # Unified tool (v2.0 - replaces search + list + details)
        update_contact_tool,
    )

    # NOTE: Tools are wrapped by @connector_tool decorator which returns StructuredTool (subclass of BaseTool)
    # MyPy doesn't infer this from the decorator, so we use cast to tell it these are BaseTool instances
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            # Contacts tools (unified)
            get_contacts_tool,  # Unified: search + list + details
            create_contact_tool,
            update_contact_tool,
            delete_contact_tool,
            # Context resolution tools (with ToolRuntime)
            resolve_reference,  # Universal contextual reference resolver
            get_context_list,  # Get all items from context (for batch operations)
            set_current_item,  # Explicitly mark item as current
            get_context_state,  # Get current state for a domain
            list_active_domains,  # List all active domains (debugging)
        ],
    )

    # Generate system prompt with dynamic datetime
    # Use ChatPromptTemplate.partial to inject datetime at invocation time (not build time)
    context_instructions = """
## 📋 Contexte Multi-Domaines (V1 - Contacts Only)

Actuellement, seul le domaine "contacts" est actif.
Les outils resolve_reference, get_context_state, set_current_item fonctionnent avec domain="contacts".
    """.strip()

    # Load versioned prompt template
    contacts_agent_prompt_template = load_prompt("contacts_agent_prompt", version="v1")

    # Build prompt template (will be partialed later in build_generic_agent)
    system_prompt_template = contacts_agent_prompt_template.format(
        current_datetime="{current_datetime}",  # Placeholder for partial
        context_instructions=context_instructions,
    )

    # Create agent config from settings (convenience function)
    # This reads contacts_agent_llm_* settings automatically
    config = create_agent_config_from_settings(
        agent_name="contacts_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        # Pass datetime generator for dynamic injection
        datetime_generator=get_prompt_datetime_formatted,
        # NOTE: HITL is always enabled (no global kill switch)
        # Tool approval requirements are defined in tool manifests (permissions.hitl_required)
    )

    # Build agent using generic template
    # The template handles:
    # - LLM configuration from settings
    # - HITL middleware setup
    # - Pre-model hook for message history
    # - Logging and metrics
    agent = build_generic_agent(config)

    logger.info(
        "contacts_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


# Note: build_contacts_agent_manual_config() function has been removed.
# This alternative implementation with manual AgentConfig construction was never used.
# The recommended pattern is create_agent_config_from_settings() for standard agents.
# For custom config, directly use AgentConfig(...) + build_generic_agent() inline.
# Removed on 2025-11-07 as part of dead code elimination (~72 lines).


__all__ = ["build_contacts_agent"]
