"""
Hue Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for Philips Hue smart lighting operations
using the generic agent builder template for consistency and maintainability.

Smart Home: Hue agent with ConnectorTool authentication (hybrid local/remote).
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


def build_hue_agent() -> Any:
    """
    Build and compile the Hue agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - Hue tools (lights, rooms, scenes — list and control)
    - ConnectorTool authentication (hybrid local API key / remote OAuth)
    - LLM configuration from settings

    Note:
        Hue tools use ConnectorTool base class (same as Apple/OAuth tools),
        not APIKeyConnectorTool. Credentials retrieved via get_hue_credentials().

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_hue_agent_with_generic_template")

    from typing import cast

    from langchain_core.tools import BaseTool

    from src.domains.agents.tools.hue_tools import (
        activate_hue_scene_tool,
        control_hue_light_tool,
        control_hue_room_tool,
        list_hue_lights_tool,
        list_hue_rooms_tool,
        list_hue_scenes_tool,
    )

    tools: list[BaseTool] = cast(
        list[BaseTool],
        [
            list_hue_lights_tool,
            control_hue_light_tool,
            list_hue_rooms_tool,
            control_hue_room_tool,
            list_hue_scenes_tool,
            activate_hue_scene_tool,
        ],
    )

    # Load versioned prompt template
    hue_agent_prompt_template = load_prompt("hue_agent_prompt", version="v1")

    system_prompt_template = hue_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",
    )

    config = create_agent_config_from_settings(
        agent_name="hue_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "hue_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_hue_agent"]
