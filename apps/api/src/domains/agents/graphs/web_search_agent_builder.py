"""
Web Search Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for unified web search operations
using Perplexity AI, Brave Search, and Wikipedia in parallel.

Features:
- Unified triple source search (Perplexity AI + Brave Search + Wikipedia)
- Fallback chain: continues if one source fails
- Wikipedia always available (no authentication required)
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


def build_web_search_agent() -> Any:
    """
    Build and compile the Web Search agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Unified web search tool (Perplexity AI + Brave + Wikipedia)
    - Fallback chain for resilience
    - LLM configuration from settings

    Note:
        The unified_web_search_tool orchestrates three sources in parallel:
        - Perplexity AI (synthesis)
        - Brave Search (URLs)
        - Wikipedia (encyclopedia - always available)

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_web_search_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.web_search_tools import unified_web_search_tool

    # Web Search tools - single unified tool
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            unified_web_search_tool,
        ],
    )

    # Load versioned prompt template
    web_search_agent_prompt_template = load_prompt("web_search_agent_prompt", version="v1")

    # Web Search is stateless - no context_instructions needed
    system_prompt_template = web_search_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless API, no context
    )

    config = create_agent_config_from_settings(
        agent_name="web_search_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "web_search_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_web_search_agent"]
