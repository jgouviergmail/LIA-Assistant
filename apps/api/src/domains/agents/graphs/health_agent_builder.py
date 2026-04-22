"""Health Metrics Agent Builder (LangChain v1.0) — v1.17.2.

Single agent owning the seven Health Metrics tools (steps, heart rate,
cross-kind overview + change detection). Follows the codebase convention
``one agent per domain`` (cf. ``weather_agent_builder``, ``emails_agent_builder``).

Phase: evolution — Health Metrics (assistant agents v1.17.2)
Created: 2026-04-22
"""

from __future__ import annotations

from typing import Any, cast

from langchain_core.tools import BaseTool

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def build_health_agent() -> Any:
    """Build and compile the Health Metrics agent.

    Returns:
        Compiled LangChain agent with the seven health tools wired to the
        Health Metrics service.
    """
    logger.info("building_health_agent")

    from src.domains.agents.tools.health_tools import (
        compare_heart_rate_to_baseline_tool,
        compare_steps_to_baseline_tool,
        detect_health_changes_tool,
        get_health_overview_tool,
        get_heart_rate_summary_tool,
        get_steps_daily_breakdown_tool,
        get_steps_summary_tool,
    )

    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            get_steps_summary_tool,
            get_steps_daily_breakdown_tool,
            compare_steps_to_baseline_tool,
            get_heart_rate_summary_tool,
            compare_heart_rate_to_baseline_tool,
            get_health_overview_tool,
            detect_health_changes_tool,
        ],
    )

    prompt_template = load_prompt("health_agent_prompt", version="v1")
    system_prompt = prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",
    )

    config = create_agent_config_from_settings(
        agent_name="health_agent",
        tools=tools,
        system_prompt=system_prompt,
        datetime_generator=get_prompt_datetime_formatted,
    )
    agent = build_generic_agent(config)
    logger.info("health_agent_built_successfully", tools_count=len(tools))
    return agent


__all__ = ["build_health_agent"]
