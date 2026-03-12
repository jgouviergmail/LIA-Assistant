"""
Routes Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Google Routes operations using the
generic agent builder template for consistency and maintainability.

Google Routes API provides:
- Route computation (A to B directions)
- Route matrix (N origins to M destinations)
- Traffic-aware routing
- Multiple travel modes (DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER)

Authentication:
- Uses global API key (GOOGLE_API_KEY) - no per-user OAuth required
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


def build_routes_agent() -> Any:
    """
    Build and compile the Routes agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Routes tools (get_route, get_route_matrix)
    - API key authentication (GOOGLE_API_KEY)
    - LLM configuration from settings

    Note:
        Routes tools require GOOGLE_API_KEY to be configured.
        No OAuth is required - uses global API key.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_routes_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.routes_tools import (
        get_route_matrix_tool,
        get_route_tool,
    )

    # Routes tools only - stateless API (no context tools needed)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            get_route_tool,  # Directions A to B
            get_route_matrix_tool,  # Distance/duration matrix
        ],
    )

    # Load versioned prompt template
    routes_agent_prompt_template = load_prompt("routes_agent_prompt", version="v1")

    # Routes is stateless - no persistent context
    system_prompt_template = routes_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless API, no persistent context
    )

    config = create_agent_config_from_settings(
        agent_name="routes_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "routes_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_routes_agent"]
