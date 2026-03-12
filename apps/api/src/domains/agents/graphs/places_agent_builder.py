"""
Places Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Google Places operations using the
generic agent builder template for consistency and maintainability.

LOT 10: Places agent with API key authentication.
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


def build_places_agent() -> Any:
    """
    Build and compile the Places agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Places tools (search, nearby, details)
    - API key authentication (GOOGLE_API_KEY)
    - LLM configuration from settings

    Note:
        Places tools require GOOGLE_API_KEY to be configured.
        No context tools are included as Places data is stateless.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_places_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.places_tools import (
        get_current_location_tool,
        get_places_tool,  # Unified tool (v2.0 - replaces search + details)
    )

    # Places tools only - no context tools needed (stateless API)
    # Note: get_places_tool is the unified tool for both text and proximity search
    # Note: get_current_location_tool for "where am I?" queries (reverse geocoding)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            get_places_tool,  # Unified: search + details
            get_current_location_tool,
        ],
    )

    # Load versioned prompt template (v2.0 unified search)
    places_agent_prompt_template = load_prompt("places_agent_prompt", version="v1")

    # Places uses context tools for reference resolution
    system_prompt_template = places_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless API, no persistent context
    )

    config = create_agent_config_from_settings(
        agent_name="places_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "places_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_places_agent"]
