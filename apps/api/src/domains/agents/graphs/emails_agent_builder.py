"""
Emails Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for email operations (Gmail API) using the
generic agent builder template for consistency and maintainability.

This file follows the same pattern as contacts_agent_builder.py for
rapid agent creation with minimal boilerplate.

Architecture (LangChain v1.0 ReAct):
    Agent Loop (internal to create_agent):
    1. LLM generates tool_calls
    2. HumanInTheLoopMiddleware intercepts (if tool matches pattern)
    3. Middleware emits interrupt() → pauses graph
    4. User approves via Command(resume={"decisions": [...]})
    5. Middleware processes decision (approve/edit/reject)
    6. Tools execute (if approved)
    7. Agent receives results and continues
"""

from typing import Any

from src.core.config import settings
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.domains.agents.prompts import load_prompt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def build_emails_agent() -> Any:
    """
    Build and compile the Emails agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Email tools (search_emails, get_email_details, send_email) via Gmail API
    - Context resolution tools (resolve_reference, set_current_item, etc.)
    - HITL middleware for tool approval (especially for send_email)
    - Pre-model hook for message history management
    - LLM configuration from settings

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.

    Example Usage:
        >>> # In graph.py:
        >>> emails_agent = build_emails_agent()
        >>> async def emails_agent_node(state, config):
        ...     result = await emails_agent.ainvoke(state, config)
        ...     return {"messages": result["messages"], "agent_results": {...}}
        >>> graph.add_node("emails_agent", emails_agent_node)
        >>> compiled_graph = graph.compile(checkpointer=checkpointer, store=store)

    Note:
        This function delegates to build_generic_agent() with emails-specific
        configuration. The generic template handles all boilerplate (HITL, pre-model
        hook, LLM config, etc.).
    """
    logger.info("building_emails_agent_with_generic_template")

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
    from src.domains.agents.tools.emails_tools import (
        delete_email_tool,
        forward_email_tool,
        get_emails_tool,  # Unified tool (v2.0 - replaces search + details)
        reply_email_tool,
        send_email_tool,
    )
    from src.domains.agents.tools.labels_tools import (
        apply_labels_tool,
        create_label_tool,
        delete_label_tool,
        list_labels_tool,
        remove_labels_tool,
        update_label_tool,
    )

    # NOTE: Tools are wrapped by @connector_tool decorator which returns StructuredTool (subclass of BaseTool)
    # MyPy doesn't infer this from the decorator, so we use cast to tell it these are BaseTool instances
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            # Gmail tools (unified)
            get_emails_tool,  # Unified: search + details
            send_email_tool,
            reply_email_tool,
            forward_email_tool,
            delete_email_tool,
            # Label management tools
            list_labels_tool,
            create_label_tool,
            update_label_tool,
            delete_label_tool,
            apply_labels_tool,
            remove_labels_tool,
            # Context resolution tools (with ToolRuntime)
            resolve_reference,  # Universal contextual reference resolver
            get_context_list,  # Get all items from context (for batch operations)
            set_current_item,  # Explicitly mark item as current
            get_context_state,  # Get current state for a domain
            list_active_domains,  # List all active domains (debugging)
        ],
    )

    # Generate system prompt with dynamic datetime
    context_instructions = """
## 📋 Contexte Multi-Domaines (Emails)

Le domaine "emails" est actif pour stocker les résultats de recherche et les détails d'emails.
Les outils resolve_reference, get_context_state, set_current_item fonctionnent avec domain="emails".

**Exemples de références contextuelles** :
- $context.emails.0 → Premier email des résultats de recherche
- $context.emails.current → Email actuellement sélectionné
    """.strip()

    # Load versioned prompt template
    emails_agent_prompt_template = load_prompt(
        "emails_agent_prompt", version=settings.emails_agent_prompt_version
    )

    # Build prompt template (will be partialed later in build_generic_agent)
    system_prompt_template = emails_agent_prompt_template.format(
        current_datetime="{current_datetime}",  # Placeholder for partial
        context_instructions=context_instructions,
    )

    # Create agent config from settings (convenience function)
    # This reads emails_agent_llm_* settings automatically
    config = create_agent_config_from_settings(
        agent_name="emails_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        # Pass datetime generator for dynamic injection
        datetime_generator=get_prompt_datetime_formatted,
        # HITL uses defaults from settings (global kill switch)
        # Tool approval requirements are now in tool manifests (permissions.hitl_required)
    )

    # Build agent using generic template
    agent = build_generic_agent(config)

    logger.info(
        "emails_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_emails_agent"]
