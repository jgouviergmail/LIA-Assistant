"""
Perplexity Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Perplexity AI operations using the
generic agent builder template for consistency and maintainability.

LOT 10: Perplexity agent with API key authentication.
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


def build_perplexity_agent() -> Any:
    """
    Build and compile the Perplexity agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Perplexity tools (search, ask)
    - API key authentication (PERPLEXITY_API_KEY)
    - LLM configuration from settings

    Note:
        Perplexity tools require PERPLEXITY_API_KEY to be configured.
        No context tools are included as Perplexity data is stateless.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_perplexity_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.perplexity_tools import (
        perplexity_ask_tool,
        perplexity_search_tool,
    )

    # Perplexity tools only - no context tools needed (stateless API)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            perplexity_search_tool,
            perplexity_ask_tool,
        ],
    )

    # Load versioned prompt template (v1.1 optimized)
    perplexity_agent_prompt_template = load_prompt("perplexity_agent_prompt", version="v1")

    # Perplexity is stateless - no context_instructions needed
    # user_language placeholder for runtime injection (same pattern as current_datetime)
    system_prompt_template = perplexity_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless API, no context
        user_language="{user_language}",  # Injected at runtime from state
    )

    config = create_agent_config_from_settings(
        agent_name="perplexity_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "perplexity_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_perplexity_agent"]
