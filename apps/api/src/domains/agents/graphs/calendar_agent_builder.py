"""
Calendar Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Google Calendar operations using the
generic agent builder template for consistency and maintainability.

LOT 9: Calendar agent with Data Registry support.
"""

from typing import Any

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def build_calendar_agent() -> Any:
    """
    Build and compile the Calendar agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Calendar tools (search, details, create, update, delete)
    - Context resolution tools for reference handling
    - HITL support for write operations
    - LLM configuration from settings

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_calendar_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.calendar_tools import (
        create_event_tool,
        delete_event_tool,
        get_events_tool,  # Unified tool (v2.0 - replaces search + details)
        list_calendars_tool,
        update_event_tool,
    )
    from src.domains.agents.tools.context_tools import (
        get_context_list,
        get_context_state,
        list_active_domains,
        resolve_reference,
        set_current_item,
    )

    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            # Calendar tools (unified)
            list_calendars_tool,
            get_events_tool,  # Unified: search + details
            create_event_tool,
            update_event_tool,
            delete_event_tool,
            # Context resolution tools
            resolve_reference,
            get_context_list,
            set_current_item,
            get_context_state,
            list_active_domains,
        ],
    )

    context_instructions = """
## Contexte Multi-Domaines (Calendar)

Le domaine "events" est actif pour stocker les résultats de recherche et les détails d'événements.
Les outils resolve_reference, get_context_state, set_current_item fonctionnent avec domain="events".

**Exemples de références contextuelles** :
- $context.events.0 → Premier événement des résultats de recherche
- $context.events.current → Événement actuellement sélectionné
    """.strip()

    # Load versioned prompt template (v1.2 optimized)
    calendar_agent_prompt_template = load_prompt("calendar_agent_prompt", version="v1")

    system_prompt_template = calendar_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions=context_instructions,
    )

    config = create_agent_config_from_settings(
        agent_name="calendar_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "calendar_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_calendar_agent"]
