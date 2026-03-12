"""
Wikipedia Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Wikipedia operations using the
generic agent builder template for consistency and maintainability.

LOT 10: Wikipedia agent with free API (no authentication).
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


def build_wikipedia_agent() -> Any:
    """
    Build and compile the Wikipedia agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Wikipedia tools (search, summary, article, related)
    - Free API (no authentication required)
    - LLM configuration from settings

    Note:
        Wikipedia API is free and doesn't require authentication.
        No context tools are included as Wikipedia data is stateless.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_wikipedia_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.wikipedia_tools import (
        get_wikipedia_article_tool,
        get_wikipedia_related_tool,
        get_wikipedia_summary_tool,
        search_wikipedia_tool,
    )

    # Wikipedia tools only - no context tools needed (stateless API)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            search_wikipedia_tool,
            get_wikipedia_summary_tool,
            get_wikipedia_article_tool,
            get_wikipedia_related_tool,
        ],
    )

    # Load versioned prompt template (v1.1 optimized)
    wikipedia_agent_prompt_template = load_prompt("wikipedia_agent_prompt", version="v1")

    # Wikipedia is stateless - no context_instructions needed
    system_prompt_template = wikipedia_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless API, no context
    )

    config = create_agent_config_from_settings(
        agent_name="wikipedia_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "wikipedia_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_wikipedia_agent"]
