"""Real graph execution for tests that inspect a complete model-requested lot."""

from __future__ import annotations

from uuid import UUID

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import TypeAdapter

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.react_nodes import react_execute_tools_node
from src.domains.agents.nodes.routing import route_from_react_execute_tools


def state_result(value: object) -> MessagesState:
    """Validate LangGraph's generic output against the actual production state contract."""
    return TypeAdapter(MessagesState).validate_python(value)


def execution_graph(
    checkpointer: InMemorySaver | None = None,
) -> CompiledStateGraph[MessagesState, LiaRuntimeContext, MessagesState, MessagesState]:
    """Use the production node, router, reducers and state schema."""
    builder: StateGraph[MessagesState, LiaRuntimeContext, MessagesState, MessagesState] = (
        StateGraph(
            MessagesState,
            context_schema=LiaRuntimeContext,
            input_schema=MessagesState,
            output_schema=MessagesState,
        )
    )
    builder.add_node("react_execute_tools", react_execute_tools_node)
    builder.add_edge(START, "react_execute_tools")
    builder.add_conditional_edges(
        "react_execute_tools",
        route_from_react_execute_tools,
        {
            "react_execute_tools": "react_execute_tools",
            "react_finalize": END,
            "react_call_model": END,
            "hitl_dispatch": END,
        },
    )
    return builder.compile(checkpointer=checkpointer)


async def execute_all(state: MessagesState) -> dict[str, object]:
    """Return all segments rather than assuming one node executes the whole lot."""
    context = LiaRuntimeContext(user_id=UUID(int=0), thread_id="test", conversation_id="test")
    with treatment_collector():
        result: object = await execution_graph().ainvoke(state, context=context)
    if not isinstance(result, dict):
        raise AssertionError("The production state graph must return its state mapping")
    return {str(key): value for key, value in result.items()}
