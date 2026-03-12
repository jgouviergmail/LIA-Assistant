"""
Query Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for LocalQueryEngine operations using the
generic agent builder template for consistency and maintainability.

INTELLIA: LocalQueryEngine agent for cross-domain data analysis.
Operates on Registry data (no external API calls).

Key Differences from Other Agents:
- No OAuth or API key required
- Works purely on in-memory Registry data
- Data is injected by parallel_executor
- Useful for filtering, sorting, aggregating, and finding patterns
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


def build_query_agent() -> Any:
    """
    Build and compile the Query agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - LocalQueryEngine tool for data analysis
    - No external API access required
    - LLM configuration from settings

    Note:
        Query agent operates on Registry data only.
        Data is injected via injected_registry_items by parallel_executor.
        No OAuth or API key needed.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_query_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.local_query_tool import local_query_engine_tool

    # Query tools only - no context tools needed (internal analysis)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            local_query_engine_tool,
        ],
    )

    # Load versioned prompt template
    query_agent_prompt_template = load_prompt("query_agent_prompt", version="v1")

    # Build available domains list dynamically from DOMAIN_REGISTRY
    from src.domains.agents.registry.domain_taxonomy import (
        DOMAIN_REGISTRY,
        get_routable_domains,
    )

    domain_lines = []
    for domain_name in get_routable_domains():
        domain_config = DOMAIN_REGISTRY.get(domain_name)
        if domain_config:
            domain_lines.append(f"- {domain_name} ({domain_config.description})")
    available_domains_str = "\n".join(domain_lines) if domain_lines else "- (none)"

    # Query agent operates on Registry data only - no context needed
    system_prompt_template = query_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Local analysis, no external context
        available_domains=available_domains_str,
    )

    config = create_agent_config_from_settings(
        agent_name="query_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "query_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_query_agent"]
