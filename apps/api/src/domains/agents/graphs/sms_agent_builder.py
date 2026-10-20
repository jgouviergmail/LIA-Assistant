"""SMS uses the standard agent middleware, accounting, quotas and slot resolution."""

from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_config_from_settings,
    domain_context_instructions,
)
from src.domains.agents.models import AgentMessagesState
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.tools.context_tools import (
    get_context_list,
    get_context_state,
    resolve_reference,
)
from src.domains.agents.tools.sms_tools import get_sms_tool, list_sms_tool, search_sms_tool


def build_sms_agent() -> (
    CompiledStateGraph[
        AgentMessagesState, LiaRuntimeContext, AgentMessagesState, AgentMessagesState
    ]
):
    configured: tuple[object, ...] = (
        get_sms_tool,
        list_sms_tool,
        search_sms_tool,
        get_context_list,
        get_context_state,
        resolve_reference,
    )
    tools: list[BaseTool] = []
    for candidate in configured:
        if not isinstance(candidate, BaseTool):
            raise TypeError("SMS read tool was not registered as a LangChain tool")
        tools.append(candidate)
    config = create_agent_config_from_settings(
        agent_name="sms_agent",
        tools=tools,
        system_prompt=load_prompt("sms_agent_prompt", version="v1").format(
            current_datetime="{current_datetime}",
            context_instructions=domain_context_instructions("sms_messages"),
        ),
        datetime_generator=get_prompt_datetime_formatted,
    )
    agent: object = build_generic_agent(config)
    if not isinstance(agent, CompiledStateGraph):
        raise TypeError("SMS agent builder returned an invalid graph")
    return agent
