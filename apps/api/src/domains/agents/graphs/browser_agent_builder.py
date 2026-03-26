"""
Browser Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for interactive web browsing using the
generic agent builder template for consistency and maintainability.

Phase: evolution F7 — Browser Control (Playwright)
Pattern: graphs/wikipedia_agent_builder.py
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


def build_browser_agent() -> Any:
    """Build and compile the browser agent using the generic agent builder template.

    Creates a LangChain v1.0 agent with browser interaction tools
    (navigate, snapshot, click, fill, press_key).
    No authentication required — uses local Playwright + Chromium.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_browser_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.browser_tools import (
        browser_click_tool,
        browser_fill_tool,
        browser_navigate_tool,
        browser_press_key_tool,
        browser_snapshot_tool,
    )

    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            browser_navigate_tool,
            browser_snapshot_tool,
            browser_click_tool,
            browser_fill_tool,
            browser_press_key_tool,
        ],
    )

    # Load versioned prompt template
    browser_agent_prompt_template = load_prompt("browser_agent_prompt", version="v1")

    # Browser is stateless (session-scoped) — no persistent context_instructions
    system_prompt_template = browser_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",
    )

    config = create_agent_config_from_settings(
        agent_name="browser_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)
    logger.info("browser_agent_built_successfully", tool_count=len(tools))
    return agent
