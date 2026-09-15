"""
Brave Search Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Brave Search operations using the
generic agent builder template for consistency and maintainability.

Features:
- Web search via Brave Search API
- News search via Brave Search API
- API key authentication (no OAuth)
"""

from typing import Any

from src.core.constants import BRAVE_NEWS_SEARCH_MAX_COUNT, BRAVE_WEB_SEARCH_MAX_COUNT
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def render_brave_agent_prompt() -> str:
    """Render the Brave agent system prompt with every value the code enforces.

    The ``count`` maxima are the tool's own constants (published in the catalogue
    manifest too), so the prompt cannot promise a bound the tool then halves.
    ``{current_datetime}`` is re-escaped: the agent config fills it per call.

    Returns:
        The system prompt template, ``{current_datetime}`` still pending.
    """
    return load_prompt("brave_agent_prompt", version="v1").format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless API, no context
        brave_web_max_count=BRAVE_WEB_SEARCH_MAX_COUNT,
        brave_news_max_count=BRAVE_NEWS_SEARCH_MAX_COUNT,
    )


def build_brave_agent() -> Any:
    """
    Build and compile the Brave Search agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Brave Search tools (web search, news search)
    - API key authentication (no OAuth required)
    - LLM configuration from settings

    Note:
        Brave tools use user-specific API key from ConnectorService.
        No context tools are included as search data is stateless.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_brave_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.brave_tools import (
        brave_news_tool,
        brave_search_tool,
    )

    # Brave Search tools - no context tools needed (stateless API)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            brave_search_tool,
            brave_news_tool,
        ],
    )

    system_prompt_template = render_brave_agent_prompt()

    config = create_agent_config_from_settings(
        agent_name="brave_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "brave_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_brave_agent"]
