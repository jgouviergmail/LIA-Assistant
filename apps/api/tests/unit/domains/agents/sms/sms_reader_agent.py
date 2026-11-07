"""A compiled agent that reads SMS: what the model boundary stands in front of.

``SmsModelBoundary`` is the middleware of every agent ``build_generic_agent`` compiles. The domain
agent that used to carry its proofs is gone (ADR-371); this one keeps them on the real tools and
the real middleware, under a slot that exists.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
)
from src.domains.agents.models import AgentMessagesState
from src.domains.agents.tools.sms_tools import get_sms_tool, list_sms_tool, search_sms_tool


def build_sms_reader() -> (
    CompiledStateGraph[
        AgentMessagesState, LiaRuntimeContext, AgentMessagesState, AgentMessagesState
    ]
):
    """Compile an agent holding the SMS read tools.

    Returns:
        The agent, behind the middleware every compiled agent carries.

    Raises:
        TypeError: If a read tool is not a LangChain tool, or the builder returns no graph.
    """
    tools: list[BaseTool] = []
    for candidate in (get_sms_tool, list_sms_tool, search_sms_tool):
        if not isinstance(candidate, BaseTool):
            raise TypeError("SMS read tool was not registered as a LangChain tool")
        tools.append(candidate)
    agent: object = build_generic_agent(
        create_agent_config_from_settings(
            agent_name="query_agent",
            tools=tools,
            system_prompt="Read the SMS the tools return. Now: {current_datetime}.",
            datetime_generator=get_prompt_datetime_formatted,
        )
    )
    if not isinstance(agent, CompiledStateGraph):
        raise TypeError("the builder returned no compiled graph")
    return agent
