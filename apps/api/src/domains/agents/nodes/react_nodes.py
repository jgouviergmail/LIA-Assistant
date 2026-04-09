"""ReAct execution mode nodes — Custom ReAct loop in the parent graph (ADR-070).

Architecture: Instead of a create_react_agent subgraph (which has known interrupt bugs
with dynamic tools — GitHub issues #5863, #4796), we implement the ReAct loop as
separate nodes in the parent graph:

    react_setup → react_call_model ←→ react_execute_tools → react_finalize

Each node benefits from the parent graph's PostgreSQL checkpointer, so interrupt()
works natively in react_execute_tools for HITL on mutation tools.

State contract:
    - Non-serializable objects (LLM, tools) are NEVER stored in state
    - Tool names and hitl_map are stored in state (JSON-serializable)
    - LLM and tools are recreated in each node (~1-2ms, standard LIA pattern)
"""

import time
from typing import Any

import structlog
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.core.config import settings
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.analysis.query_intelligence_helpers import (
    get_qi_attr,
    get_query_intelligence_from_state,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.tool_registry import get_tool
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    react_agent_duration_seconds,
    react_agent_executions_total,
    react_agent_hitl_interrupts_total,
    react_agent_iterations,
    react_agent_tools_called_total,
)
from src.infrastructure.observability.tracing import trace_node

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _window_messages_for_react(
    messages: list[BaseMessage],
) -> list[BaseMessage]:
    """Window messages for the ReAct LLM call to control token usage.

    Reuses get_windowed_messages() from message_windowing.py for the history
    of previous turns, and preserves the current ReAct loop integrally.

    Strategy:
    1. Split messages at the last HumanMessage (= current turn boundary)
    2. Window the history (previous turns) via get_windowed_messages()
       → keeps SystemMessages + last N conversational turns (no ToolMessages)
    3. Append ALL current turn messages (HumanMessage + ReAct loop: AIMessage
       with tool_calls + ToolMessages) — the agent needs its full reasoning chain

    Args:
        messages: Full state messages (accumulated across turns + ReAct loop).

    Returns:
        Windowed message list.
    """
    from langchain_core.messages import HumanMessage as HM

    from src.domains.agents.utils.message_windowing import get_windowed_messages

    # Find the last HumanMessage — everything after it is the current ReAct loop
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HM):
            last_human_idx = i
            break

    if last_human_idx == -1:
        return messages

    # Split: history (before last HumanMessage) and current turn (from HumanMessage onward)
    history = messages[:last_human_idx]
    current_turn = messages[last_human_idx:]

    # Window the history using existing infrastructure
    windowed_history = get_windowed_messages(
        history, window_size=settings.react_agent_history_window_turns
    )

    windowed = windowed_history + current_turn

    if len(windowed) < len(messages):
        logger.debug(
            "react_messages_windowed",
            original_count=len(messages),
            windowed_count=len(windowed),
            history_kept=len(windowed_history),
            current_turn_msgs=len(current_turn),
        )

    return windowed


def _rebuild_wrapped_tools(
    tool_names: list[str],
    hitl_map: dict[str, bool],
) -> list[ReactToolWrapper]:
    """Rebuild ReactToolWrapper instances from tool names.

    Called in each node that needs tools (call_model for binding, execute_tools
    for execution). Cost: ~5-10ms total, negligible vs LLM latency.

    Args:
        tool_names: List of tool names to wrap.
        hitl_map: Map of tool_name → hitl_required.

    Returns:
        List of ReactToolWrapper instances.
    """
    wrappers: list[ReactToolWrapper] = []
    for name in tool_names:
        base_tool = get_tool(name)
        if base_tool is None:
            continue
        wrappers.append(
            ReactToolWrapper(
                original_tool=base_tool,
                hitl_required=hitl_map.get(name, False),
            )
        )
    return wrappers


def _build_system_prompt(state: MessagesState) -> str:
    """Build the ReAct agent system prompt with context variables.

    Args:
        state: Current graph state.

    Returns:
        Formatted system prompt string.
    """
    personality = state.get("personality_instruction") or "a helpful, friendly assistant"
    user_tz = state.get("user_timezone", "Europe/Paris")
    user_lang = state.get("user_language", "fr")

    template = load_prompt("react_agent_prompt")
    return template.format(
        personnalite=personality,
        current_datetime=get_prompt_datetime_formatted(),
        user_timezone=user_tz,
        user_language=user_lang,
    )


# ---------------------------------------------------------------------------
# Node 1: react_setup
# ---------------------------------------------------------------------------


@trace_node("react_setup")
@track_metrics(node_name="react_setup")
async def react_setup_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Prepare tools, prompt, and state for the ReAct loop.

    Runs once at the beginning of the ReAct path. Filters tools by
    QueryIntelligence domains, builds the system prompt, and stores
    serializable metadata in state.

    Args:
        state: Current graph state (from router).
        config: RunnableConfig with user context.

    Returns:
        State update with react_tool_names, react_hitl_map, and SystemMessage.
    """
    start_time = time.monotonic()
    intelligence = get_query_intelligence_from_state(state)

    # Feature flag guard
    if not settings.react_agent_enabled:
        logger.warning("react_setup_disabled", reason="feature_flag_off")
        return {}

    # Select and wrap tools
    selector = ReactToolSelector()
    wrapped_tools, hitl_map = selector.select(intelligence) if intelligence else ([], {})
    tool_names = [t.name for t in wrapped_tools]

    # Build system prompt
    system_prompt = _build_system_prompt(state)

    # Build memory context message.
    # Memory resolution happens pre-routing (QueryAnalyzer) and produces:
    # - resolved_references: {"mon frère": "Alexandre Gouvier"}
    # - injected_memories: relevant memory facts
    # Without a search_memories tool, this is the only way the ReAct agent
    # can access memory. The agent still decides autonomously what to DO
    # with this context (search contacts, get route, etc.).
    messages_to_add: list[SystemMessage] = [SystemMessage(content=system_prompt)]

    context_parts: list[str] = []
    resolved_refs = state.get("resolved_references") or (
        intelligence.resolved_references if intelligence else None
    )
    if resolved_refs:
        ref_lines = [f'- "{k}" = {v}' for k, v in resolved_refs.items()]
        context_parts.append("Reference resolution:\n" + "\n".join(ref_lines))

    injected_memories = state.get("injected_memories")
    if injected_memories and isinstance(injected_memories, str) and injected_memories.strip():
        context_parts.append(f"User memory facts:\n{injected_memories}")

    if context_parts:
        messages_to_add.append(
            SystemMessage(
                content="<MemoryContext>\n" + "\n\n".join(context_parts) + "\n</MemoryContext>"
            )
        )

    # Inject active skills catalogue (L1) so the ReAct agent can discover
    # and use skills via the existing skill tools (activate_skill_tool,
    # run_skill_script, read_skill_resource). Same filtered catalogue as
    # the pipeline planner — respects active_skills_ctx per user.
    skills_catalog = ""
    if getattr(settings, "skills_enabled", False):
        from src.core.context import active_skills_ctx
        from src.domains.skills.injection import build_skills_catalog

        configurable = config.get("configurable", {})
        skill_user_id = configurable.get("langgraph_user_id", "")
        active = active_skills_ctx.get()
        skills_catalog = build_skills_catalog(user_id=skill_user_id, active_skills=active)
        if skills_catalog:
            messages_to_add.append(
                SystemMessage(content=f"<AvailableSkills>\n{skills_catalog}\n</AvailableSkills>")
            )

    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(
        "react_setup_complete",
        tool_count=len(tool_names),
        hitl_count=sum(1 for v in hitl_map.values() if v),
        domains=get_qi_attr(state, "domains", default=[]),
        has_memory_context=bool(context_parts),
        has_skills_catalog=bool(skills_catalog),
        duration_ms=duration_ms,
    )

    return {
        "react_tool_names": tool_names,
        "react_hitl_map": hitl_map,
        "react_iteration": 0,
        "react_start_time": time.time(),
        "messages": messages_to_add,
    }


# ---------------------------------------------------------------------------
# Node 2: react_call_model
# ---------------------------------------------------------------------------


@trace_node("react_call_model")
@track_metrics(node_name="react_call_model")
async def react_call_model_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Call the ReAct LLM with bound tools.

    Recreates LLM and tool bindings each iteration (~1-2ms).
    Streaming is handled automatically by astream_events() at service layer.

    Args:
        state: Current graph state with messages and tool metadata.
        config: RunnableConfig.

    Returns:
        State update with the AIMessage (with or without tool_calls).
    """
    tool_names = state.get("react_tool_names", [])
    hitl_map = state.get("react_hitl_map", {})
    iteration = state.get("react_iteration", 0)

    # Recreate LLM and bind tools
    llm = get_llm("react_agent")
    wrapped_tools = _rebuild_wrapped_tools(tool_names, hitl_map)

    if wrapped_tools:
        llm_with_tools = llm.bind_tools(wrapped_tools)
    else:
        llm_with_tools = llm

    # Apply windowing to control context size.
    # state["messages"] accumulates across turns (checkpoint persistence) AND within
    # the ReAct loop (AIMessage + ToolMessage per iteration). Without windowing,
    # tokens explode: 12K → 74K → 131K across 3 turns.
    #
    # Strategy: keep SystemMessages + recent conversational history + ALL ReAct
    # loop messages from the current turn (the agent needs its own reasoning chain).
    messages = _window_messages_for_react(state["messages"])

    response: AIMessage = await llm_with_tools.ainvoke(messages, config)

    tool_call_count = len(response.tool_calls) if response.tool_calls else 0
    logger.info(
        "react_call_model_complete",
        iteration=iteration + 1,
        tool_calls=tool_call_count,
        has_content=bool(response.content),
    )

    return {
        "messages": [response],
        "react_iteration": iteration + 1,
    }


# ---------------------------------------------------------------------------
# Node 3: react_execute_tools
# ---------------------------------------------------------------------------


@trace_node("react_execute_tools")
@track_metrics(node_name="react_execute_tools")
async def react_execute_tools_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Execute tools from the last AIMessage, with HITL for mutations.

    Uses the idempotence pattern: on re-execution after interrupt resume,
    tool_calls that already have a ToolMessage in state are skipped.

    HITL: Mutation tools (hitl_required=True) trigger interrupt() which pauses
    the graph and waits for user approval. On resume, previously-matched
    interrupts return their resume value immediately (LangGraph index matching).

    IMPORTANT: Tool calls are processed in the EXACT order from AIMessage.tool_calls.
    Never reorder — interrupt() matching is index-based.

    Args:
        state: Current graph state with messages and tool metadata.
        config: RunnableConfig with __deps for tool execution.

    Returns:
        State update with ToolMessages and collected registry items.
    """
    # Get the last AIMessage (must have tool_calls)
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    hitl_map = state.get("react_hitl_map", {})
    tool_names = state.get("react_tool_names", [])

    # IDEMPOTENCE: find tool_calls already resolved (have a ToolMessage in state)
    existing_tool_msg_ids: set[str] = {
        m.tool_call_id for m in state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id
    }

    # Rebuild tools for execution
    wrapped_tools = _rebuild_wrapped_tools(tool_names, hitl_map)
    tool_by_name: dict[str, ReactToolWrapper] = {t.name: t for t in wrapped_tools}

    # Pre-load ToolRuntime dependencies (outside loop for efficiency)
    from src.domains.agents.context.store import get_tool_context_store
    from src.domains.agents.orchestration.parallel_executor import _build_tool_runtime

    store = await get_tool_context_store()

    new_messages: list[ToolMessage] = []
    collected_registry: dict[str, Any] = {}

    for tool_call in last_message.tool_calls:
        tc_id: str = tool_call["id"]
        tc_name: str = tool_call["name"]
        tc_args: dict[str, Any] = tool_call.get("args", {})

        # IDEMPOTENCE: skip if already executed
        if tc_id in existing_tool_msg_ids:
            continue

        # HITL for mutation tools
        is_mutation = hitl_map.get(tc_name, False)
        if is_mutation:
            # interrupt() halts on first call, returns resume value on re-execution
            decision = interrupt(
                {
                    "type": "react_tool_approval",
                    "tool_name": tc_name,
                    "tool_args": tc_args,
                }
            )
            if isinstance(decision, dict) and decision.get("action") == "reject":
                new_messages.append(
                    ToolMessage(
                        content=f"Action '{tc_name}' was declined by the user.",
                        tool_call_id=tc_id,
                        name=tc_name,
                    )
                )
                react_agent_hitl_interrupts_total.labels(tool_name=tc_name, decision="reject").inc()
                logger.info(
                    "react_hitl_rejected",
                    tool_name=tc_name,
                )
                continue

            react_agent_hitl_interrupts_total.labels(tool_name=tc_name, decision="approve").inc()
            logger.info(
                "react_hitl_approved",
                tool_name=tc_name,
            )

        # Execute tool: call ORIGINAL tool via ainvoke with config (for ToolRuntime injection),
        # then process result through wrapper for string conversion + registry collection.
        wrapper = tool_by_name.get(tc_name)
        if wrapper is None:
            new_messages.append(
                ToolMessage(
                    content=f"Tool '{tc_name}' not found.",
                    tool_call_id=tc_id,
                    name=tc_name,
                )
            )
            continue

        try:
            # Inject ToolRuntime into args (required by ConnectorTools).
            # LangChain's InjectedToolArg is normally injected by ToolNode,
            # but we call tools directly — so we must build ToolRuntime manually.
            # Pattern: parallel_executor._build_tool_runtime()
            injected_args = _build_tool_runtime(wrapper._original_tool, tc_args, config, store)
            raw_result = await wrapper._original_tool.coroutine(**injected_args)
            # Process through wrapper for string conversion + registry collection
            content = wrapper._process_result(raw_result)
        except Exception as exc:
            content = f"Error executing {tc_name}: {exc!s}"
            logger.warning(
                "react_execute_tools_error",
                tool_name=tc_name,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        new_messages.append(
            ToolMessage(
                content=content,
                tool_call_id=tc_id,
                name=tc_name,
            )
        )
        react_agent_tools_called_total.labels(tool_name=tc_name).inc()

        # Collect registry from wrapper
        if wrapper._accumulated_registry:
            collected_registry.update(wrapper._accumulated_registry)

    logger.info(
        "react_execute_tools_complete",
        tools_executed=len(new_messages),
        registry_items=len(collected_registry),
    )

    result: dict[str, Any] = {"messages": new_messages}
    if collected_registry:
        result["registry"] = collected_registry
        # Merge with existing current_turn_registry from previous iterations.
        # current_turn_registry has NO reducer (overwrite semantics), so each node
        # return replaces the previous value. We must manually accumulate items
        # across ReAct iterations to preserve data cards from earlier tool calls.
        # Example: iteration 1 → events, iteration 2 → contacts → both must be
        # present for response_node to generate all HTML cards.
        existing_turn_registry = dict(state.get("current_turn_registry") or {})
        existing_turn_registry.update(collected_registry)
        result["current_turn_registry"] = existing_turn_registry
    return result


# ---------------------------------------------------------------------------
# Node 4: react_finalize
# ---------------------------------------------------------------------------


@trace_node("react_finalize")
@track_metrics(node_name="react_finalize")
async def react_finalize_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Finalize the ReAct loop and prepare metadata for the response node.

    Collects iteration count and sets react_agent_result for the response node
    to detect ReAct mode and use the final AIMessage directly.

    Args:
        state: Current graph state after ReAct loop completion.
        config: RunnableConfig.

    Returns:
        State update with react_agent_result metadata.
    """
    iteration = state.get("react_iteration", 0)
    start_time = state.get("react_start_time")

    # The last message should be the final AIMessage (no tool_calls)
    last_message = state["messages"][-1] if state.get("messages") else None
    final_content = ""
    if isinstance(last_message, AIMessage):
        if isinstance(last_message.content, str):
            final_content = last_message.content
        elif isinstance(last_message.content, list):
            # Anthropic format: list of content blocks
            final_content = " ".join(
                block.get("text", "") for block in last_message.content if isinstance(block, dict)
            )

    # Prometheus metrics
    duration_s = time.time() - start_time if start_time else 0.0
    react_agent_iterations.observe(iteration)
    react_agent_duration_seconds.observe(duration_s)
    react_agent_executions_total.labels(status="success" if final_content else "empty").inc()

    logger.info(
        "react_finalize_complete",
        total_iterations=iteration,
        has_final_content=bool(final_content),
        duration_seconds=round(duration_s, 2),
    )

    return {
        "react_agent_result": {
            "final_message": final_content,
            "iteration_count": iteration,
            "mode": "react",
        },
    }
