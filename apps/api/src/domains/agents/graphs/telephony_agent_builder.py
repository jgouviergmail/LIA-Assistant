"""
Telephony Agent Builder (LangChain v1.0) - Using Generic Template.

Builds a compiled LangChain v1 agent for agentic telephony (ADR-127): a single
draft-producing tool (``place_phone_call_tool``) that creates a PHONE_CALL
draft confirmed by the user (HITL) before any dialing happens.

Registered flag-guarded in ``startup/agents.py`` (``TELEPHONY_ENABLED``),
symmetrically with the catalogue-manifest registration in
``catalogue_loader.py``.
"""

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


def build_telephony_agent() -> Any:
    """
    Build and compile the telephony agent using the generic agent builder template.

    This function creates a LangChain v1.0 agent with:
    - The single draft-producing tool ``place_phone_call_tool`` (contact→phone
      resolution and the per-user connector guard live inside the tool)
    - LLM configuration from LLM_DEFAULTS ("telephony_agent") + DB overrides

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.
    """
    logger.info("building_telephony_agent_with_generic_template")

    from src.domains.agents.tools.telephony_tools import place_phone_call_tool

    tools: list[BaseTool] = cast(list[BaseTool], [place_phone_call_tool])

    # Load versioned prompt template
    telephony_agent_prompt_template = load_prompt("telephony_agent_prompt", version="v1")

    system_prompt_template = telephony_agent_prompt_template.format(
        current_datetime="{current_datetime}",
        context_instructions="",
    )

    config = create_agent_config_from_settings(
        agent_name="telephony_agent",
        tools=tools,
        system_prompt=system_prompt_template,
        datetime_generator=get_prompt_datetime_formatted,
    )

    agent = build_generic_agent(config)

    logger.info(
        "telephony_agent_built_successfully",
        tools_count=len(tools),
        llm_model=config["llm_config"]["model"],
    )

    return agent


__all__ = ["build_telephony_agent"]
