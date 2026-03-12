"""
Web Fetch Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for web page content extraction using the
generic agent builder template for consistency and maintainability.

Features:
- Fetch and extract content from web pages (URL → Markdown)
- SSRF prevention (private IP/hostname blacklists, DNS pre-resolution)
- No OAuth or API key required (fetches public URLs directly)
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


def build_web_fetch_agent() -> Any:
    """
    Build and compile the Web Fetch agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Web page fetch tool (URL → clean Markdown)
    - SSRF prevention (no access to private/internal IPs)
    - No external authentication required

    Note:
        Web Fetch is stateless - no context tools are included.
        The tool fetches public URLs directly with httpx.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_web_fetch_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.web_fetch_tools import fetch_web_page_tool

    # Web Fetch tools - single tool, no context tools needed (stateless)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            fetch_web_page_tool,
        ],
    )

    # Load versioned prompt template
    web_fetch_agent_prompt_template = load_prompt("web_fetch_agent_prompt", version="v1")

    # Web Fetch is stateless - no context_instructions needed
    system_prompt_template = web_fetch_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless, no context
    )

    config = create_agent_config_from_settings(
        agent_name="web_fetch_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "web_fetch_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_web_fetch_agent"]
