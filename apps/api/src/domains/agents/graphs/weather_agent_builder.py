"""
Weather Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for OpenWeatherMap operations using the
generic agent builder template for consistency and maintainability.

LOT 10: Weather agent with API key authentication (no OAuth).
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


def build_weather_agent() -> Any:
    """
    Build and compile the Weather agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Weather tools (current, forecast, hourly)
    - API key authentication (no OAuth required)
    - LLM configuration from settings

    Note:
        Weather tools don't use OAuth connectors - they use OPENWEATHERMAP_API_KEY.
        No context tools are included as weather data is stateless.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_weather_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.weather_tools import (
        get_current_weather_tool,
        get_hourly_forecast_tool,
        get_weather_forecast_tool,
    )

    # Weather tools only - no context tools needed (stateless API)
    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            get_current_weather_tool,
            get_weather_forecast_tool,
            get_hourly_forecast_tool,
        ],
    )

    # Load versioned prompt template (v1.2 optimized)
    weather_agent_prompt_template = load_prompt("weather_agent_prompt", version="v1")

    # Weather is stateless - no context_instructions needed
    system_prompt_template = weather_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",  # Stateless API, no context
    )

    config = create_agent_config_from_settings(
        agent_name="weather_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "weather_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_weather_agent"]
