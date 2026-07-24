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
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_types import get_language_name
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.analysis.query_intelligence_helpers import (
    get_qi_attr,
    get_query_intelligence_from_state,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.connector_error_notice import (
    emit_connector_notice_for_exception,
)
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.tool_resolution import resolve_tool_instance
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    react_agent_duration_seconds,
    react_agent_executions_total,
    react_agent_hitl_interrupts_total,
    react_agent_iterations,
    react_agent_tools_called_total,
    semantic_param_guard_blocks_total,
)
from src.infrastructure.observability.tracing import trace_node

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _neutralize_widget_sentinels(history: list[BaseMessage]) -> list[BaseMessage]:
    """Replace host-owned widget sentinels in prior answers with a short marker.

    ``response_node`` writes the enriched answer — sentinel included — back into
    ``state["messages"]``, and this window serves that history RAW to the ReAct
    model (the response path neutralizes HTML, this one never did). The model
    learned the markup by imitation and started emitting its own, which produced
    duplicate widgets and, worse, sentinels pointing at a registry id from an
    earlier turn. Removing the example removes the incentive — and reclaims the
    tokens the markup was costing on every turn.

    Args:
        history: Windowed prior-turn messages (the current turn is untouched —
            the ReAct loop needs its own reasoning chain verbatim).

    Returns:
        A new list; messages without a sentinel are passed through by identity.
    """
    from src.core.constants import CONTEXT_WIDGET_DISPLAYED_PLACEHOLDER
    from src.domains.agents.display.sentinel_filter import strip_widget_sentinels
    from src.infrastructure.llm.message_text import coerce_content_to_text
    from src.infrastructure.observability.metrics_registry import (
        widget_sentinels_stripped_total,
    )

    out: list[BaseMessage] = []
    stripped = 0
    for msg in history:
        if not isinstance(msg, AIMessage):
            out.append(msg)
            continue
        text = coerce_content_to_text(getattr(msg, "content", ""))
        cleaned, count = strip_widget_sentinels(
            text, replacement=CONTEXT_WIDGET_DISPLAYED_PLACEHOLDER
        )
        if not count:
            out.append(msg)
            continue
        stripped += count
        # Copy, never rebuild: a fresh ``AIMessage(content=..., id=...)`` would
        # silently drop ``tool_calls``/``additional_kwargs``. An AIMessage that
        # carried BOTH tool_calls and a sentinel would then leave its
        # ToolMessages orphaned, and the provider rejects the whole request
        # ("messages with role 'tool' must be a response to a preceding message
        # with 'tool_calls'") — or worse, `enforce_tool_message_pairing` drops
        # the carrier and its results silently. `model_copy` changes the content
        # and nothing else.
        out.append(msg.model_copy(update={"content": cleaned}))

    if stripped:
        widget_sentinels_stripped_total.labels(source="react_history").inc(stripped)
        logger.debug("react_history_widget_sentinels_neutralized", count=stripped)
    return out


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

    windowed = _neutralize_widget_sentinels(windowed_history) + current_turn

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
        # Resolve across the global registry AND the per-request user MCP
        # ContextVar (pipeline parity) so user MCP tools selected at setup can
        # still be bound/executed in later nodes.
        base_tool = resolve_tool_instance(name)
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
    user_tz = state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE)
    user_lang = state.get("user_language", "fr")

    # Cross-domain type links (same section the pipeline planner receives,
    # ontology ∪ live manifests). Without it, the ReAct LLM has no signal
    # that e.g. a route destination should come from a contact's exact
    # address rather than an approximate memory value.
    from src.domains.agents.semantic.expansion_service import (
        generate_semantic_dependencies_for_prompt,
    )

    domains = get_qi_attr(state, "domains", default=[]) or []
    semantic_deps = generate_semantic_dependencies_for_prompt(
        domains, include_jinja2_patterns=False
    )

    template = load_prompt("react_agent_prompt")
    return template.format(
        personnalite=personality,
        current_datetime=get_prompt_datetime_formatted(),
        user_timezone=user_tz,
        # Human-readable name ("French") — clearer language directive for the
        # LLM than a raw code ("fr"); same convention as get_response_prompt.
        user_language=get_language_name(user_lang),
        semantic_dependencies=semantic_deps,
    )


def _record_react_metrics(iteration: int, duration_s: float, status: str) -> None:
    """Record ReAct loop completion metrics.

    Shared by ``react_finalize_node`` (normal completion) and
    ``react_execute_tools_node`` (when the loop is short-circuited because a
    mutation tool produced a draft that is handed off to the draft_critique HITL
    flow). Without this, draft-terminated ReAct turns would be invisible in the
    ReAct dashboards.

    Args:
        iteration: Number of ReAct iterations performed during the turn.
        duration_s: Total ReAct loop duration in seconds.
        status: Outcome label for ``react_agent_executions_total``
            ("success", "empty" or "draft").
    """
    react_agent_iterations.observe(iteration)
    react_agent_duration_seconds.observe(duration_s)
    react_agent_executions_total.labels(status=status).inc()


def _extract_draft_info(raw_result: Any, tool_name: str) -> dict[str, Any] | None:
    """Extract draft metadata from a tool result requiring confirmation.

    Mirrors the pipeline's ``parallel_executor`` draft detection so the ReAct
    loop can hand a prepared draft off to the shared draft_critique HITL flow.
    A mutation tool (create/update/delete) returns ``requires_confirmation=True``
    and stores the executable payload in its registry item — the actual action
    is only performed after the user confirms.

    Args:
        raw_result: Raw tool output (``UnifiedToolOutput`` for draft tools).
        tool_name: Name of the tool that produced the result.

    Returns:
        A ``PendingDraftInfo``-compatible dict (draft_id, draft_type,
        draft_content, draft_summary, registry_ids, tool_name, step_id), or
        ``None`` when the result is not a confirmable draft.
    """
    tool_metadata = getattr(raw_result, "tool_metadata", None)
    if not isinstance(tool_metadata, dict) or not tool_metadata.get("requires_confirmation"):
        return None

    draft_id = tool_metadata.get("draft_id")
    if not draft_id:
        return None

    registry_updates = getattr(raw_result, "registry_updates", None) or {}

    # Extract the executable draft content from the registry item payload — the
    # same source the pipeline's DraftExecutor consumes to perform the real action.
    draft_content: dict[str, Any] = {}
    item = registry_updates.get(draft_id)
    if item is not None:
        payload = getattr(item, "payload", None)
        if payload is None and isinstance(item, dict):
            payload = item.get("payload")
        if isinstance(payload, dict):
            draft_content = payload.get("content") or {}

    return {
        "draft_id": draft_id,
        "draft_type": tool_metadata.get("draft_type"),
        "draft_content": draft_content,
        "draft_summary": getattr(raw_result, "summary_for_llm", "") or "",
        "registry_ids": list(registry_updates.keys()),
        "tool_name": tool_name,
        "step_id": None,
    }


# ---------------------------------------------------------------------------
# Node 1: react_setup
# ---------------------------------------------------------------------------


@trace_node("react_setup")
@track_metrics(node_name="react_setup", duration_metric=agent_node_duration_seconds)
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

    # User-model portrait — ambient diffusion (ADR-079, commit 3).
    # Brief format (~60 tokens) injected once at react setup so the agent
    # carries the same posture as the pipeline mode.
    if getattr(settings, "journals_enabled", False):
        try:
            configurable = config.get("configurable", {})
            user_journals_enabled = configurable.get("user_journals_enabled", False)
            react_user_id = configurable.get("langgraph_user_id", "")
            if user_journals_enabled and react_user_id:
                from src.domains.journals.portrait_builder import (
                    build_journal_user_model_block,
                )

                user_model_block = await build_journal_user_model_block(
                    user_id=react_user_id, format="brief", flow="react"
                )
                if user_model_block:
                    messages_to_add.append(SystemMessage(content=user_model_block))
        except Exception as exc:  # pragma: no cover — best-effort
            logger.warning("react_user_model_block_failed", error=str(exc))

    # Operational journal directives (L1/L2) — close the cross-mode gap.
    # The ReAct reasoning loop was blind to behavioural directives (they only
    # reached the final response_node). Inject a small, bounded set ONCE here at
    # setup (count cap, no truncation) so the loop is guided like the pipeline
    # planner. L0/L3 are excluded by default inside build_journal_context.
    # Deferred self-evaluation stays anchored to response_node (not duplicated here).
    if getattr(settings, "journals_enabled", False):
        try:
            configurable = config.get("configurable", {})
            react_user_journals = configurable.get("user_journals_enabled", False)
            react_journal_user_id = configurable.get("langgraph_user_id", "")
            max_directives = settings.journal_react_context_max_entries
            last_user_text = ""
            for _msg in reversed(state.get("messages", []) or []):
                if isinstance(_msg, HumanMessage):
                    last_user_text = coerce_content_to_text(_msg.content) or ""
                    break
            if (
                react_user_journals
                and react_journal_user_id
                and max_directives > 0
                and last_user_text
            ):
                from src.domains.journals.context_builder import build_journal_context
                from src.infrastructure.database.session import get_db_context

                async with get_db_context() as journal_db:
                    directives_block, _jdebug, _jids = await build_journal_context(
                        user_id=react_journal_user_id,
                        query=last_user_text,
                        db=journal_db,
                        session_id=configurable.get("thread_id"),
                        max_results_override=max_directives,
                        truncate_to_budget=False,
                    )
                if directives_block:
                    messages_to_add.append(SystemMessage(content=directives_block))
        except Exception as exc:  # pragma: no cover — best-effort
            logger.warning("react_journal_directives_failed", error=str(exc))

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
        # New turn starts with an EMPTY per-turn registry. Without this purge,
        # the value restored from the previous turn's checkpoint leaks into
        # react_execute_tools' intra-turn accumulation and the response node
        # then re-displays last turn's data (e.g. previous events on a route
        # question). Mirrors the pipeline behaviour where task_orchestrator
        # overwrites current_turn_registry with the current run only. The
        # cross-turn `registry` (merge reducer) is intentionally untouched —
        # context resolution still sees the full history. HITL draft resumes
        # re-enter after this node, so mid-turn items are never dropped.
        "current_turn_registry": {},
    }


# ---------------------------------------------------------------------------
# Node 2: react_call_model
# ---------------------------------------------------------------------------


@trace_node("react_call_model")
@track_metrics(node_name="react_call_model", duration_metric=agent_node_duration_seconds)
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

    # Stream the model's reasoning live (thinking models) to the progress UI via
    # the custom channel, while returning the SAME aggregated AIMessage as
    # ``ainvoke`` (tool_calls/content identical — proven by prod POC). On any
    # failure or empty result, fall back to ``ainvoke`` so the loop never breaks.
    from src.infrastructure.llm.reasoning_stream import (
        make_reasoning_emit,
        stream_reasoning_events,
    )

    response: AIMessage | None = None
    try:
        response = await stream_reasoning_events(
            llm_with_tools,
            messages,
            emit=make_reasoning_emit("react_call_model"),
            config=config,
        )
    except Exception as exc:  # defensive: reasoning streaming must never break the loop
        logger.warning(
            "react_reasoning_stream_failed",
            iteration=iteration + 1,
            error=str(exc),
            error_type=type(exc).__name__,
        )
    if response is None:
        # Silent-double-call guard: the stream completed without a terminal
        # output, so this ainvoke is a SECOND full LLM call. This path is
        # healthy today (raw tool-bound LLM, proven capture) — if this warning
        # ever fires, a provider/model/langchain change broke the capture.
        logger.warning(
            "react_reasoning_stream_no_output_double_call",
            iteration=iteration + 1,
            msg="Reasoning stream yielded no terminal output — falling back to "
            "a second full LLM call (double cost/latency for this iteration)",
        )
        response = await llm_with_tools.ainvoke(messages, config)

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
@track_metrics(node_name="react_execute_tools", duration_metric=agent_node_duration_seconds)
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
    from src.domains.agents.semantic.param_guard import (
        check_semantic_params,
        collect_resolved_person_names,
        strip_placeholder_arguments,
    )

    store = await get_tool_context_store()

    # Runtime semantic contract guard (parity with the parallel executor):
    # person names resolved for this turn must not reach address/email-typed
    # params — the API would geocode/send arbitrarily. Recoverable ToolMessage
    # instead, so the ReAct loop fetches the real value and retries.
    guard_person_names = collect_resolved_person_names(state.get("resolved_references"))

    new_messages: list[ToolMessage] = []
    collected_registry: dict[str, Any] = {}
    pending_drafts: list[dict[str, Any]] = []

    for tool_call in last_message.tool_calls:
        tc_id: str = tool_call["id"]
        tc_name: str = tool_call["name"]
        tc_args: dict[str, Any] = tool_call.get("args", {})

        # IDEMPOTENCE: skip if already executed
        if tc_id in existing_tool_msg_ids:
            continue

        # Parity with the parallel executor: a textual "no value" ("null",
        # "none", ...) on an optional typed parameter means "not provided".
        # Deterministic, so re-executing after an interrupt is stable.
        tc_args = strip_placeholder_arguments(tc_name, tc_args)

        # Semantic guard BEFORE the HITL interrupt: never ask the user to
        # approve a call that would be blocked anyway. Deterministic across
        # interrupt re-executions (state mappings and args are stable).
        if guard_person_names:
            violation = check_semantic_params(tc_name, tc_args, guard_person_names)
            if violation is not None:
                semantic_param_guard_blocks_total.labels(
                    tool_name=tc_name,
                    semantic_type=violation.semantic_type,
                    execution_mode="react",
                ).inc()
                # No PII at WARNING: the offending value is a person name.
                logger.warning(
                    "semantic_param_guard_blocked",
                    tool_name=tc_name,
                    param_name=violation.param_name,
                    semantic_type=violation.semantic_type,
                )
                new_messages.append(
                    ToolMessage(
                        content=f"ERROR: {violation.llm_message()}",
                        tool_call_id=tc_id,
                        name=tc_name,
                    )
                )
                continue

        # HITL for mutation tools (non-draft) — route through the SHARED
        # tool_confirmation contract, the SAME interaction the pipeline uses via
        # hitl_dispatch. A type-tagged action_request makes the streaming service
        # render a real confirmation (question + buttons) AND persist it in Redis,
        # and the resume flows through _parse_approval_decision → {"action": ...}.
        # The legacy bare "react_tool_approval" value had no action_requests, so it
        # was never rendered nor resumable (silent hang, #3). Draft-based mutation
        # tools are hitl_required=False and confirm via the draft_critique handoff
        # below (invariant enforced by test_hitl_required_consistency.py).
        is_mutation = hitl_map.get(tc_name, False)
        if is_mutation:
            # interrupt() halts on first call, returns the resume value on re-execution
            decision = interrupt(
                {
                    "action_requests": [
                        {
                            "type": "tool_confirmation",
                            "tool_name": tc_name,
                            "tool_args": tc_args,
                        }
                    ],
                    "generate_question_streaming": True,
                    "user_language": state.get("user_language", "fr"),
                    "user_timezone": state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE),
                    "hitl_type": HitlInteractionType.TOOL_CONFIRMATION.value,
                }
            )
            # Execute ONLY on an explicit confirmation. Anything else (cancel,
            # reject, ambiguous, or a malformed resume) declines — the safe default
            # for a mutation gated behind HITL.
            decision_action = decision.get("action") if isinstance(decision, dict) else None
            if decision_action not in ("confirm", "approve"):
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
                    decision_action=decision_action,
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
            # Draft detection: a mutation tool (create/update/delete) returns
            # requires_confirmation=True — it prepared a DRAFT, not the real
            # action. Collect it for the HITL handoff (see return below).
            draft_info = _extract_draft_info(raw_result, tc_name)
            if draft_info is not None:
                pending_drafts.append(draft_info)
        except Exception as exc:
            content = f"Error executing {tc_name}: {exc!s}"
            logger.warning(
                "react_execute_tools_error",
                tool_name=tc_name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            # Lot 3 P3 (ADR-134): safety net for tools that don't route their
            # exceptions through handle_tool_exception (ConnectorToolBase does;
            # this covers direct-coroutine tools). Best-effort, deduped
            # frontend-side.
            emit_connector_notice_for_exception(exc, tool_name=tc_name)

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
        pending_drafts=len(pending_drafts),
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

    # Draft HITL handoff (parity with the pipeline draft_critique flow).
    # When a mutation tool prepared a draft, hand it off to the shared
    # hitl_dispatch → draft_critique → response flow via pending_draft_critique
    # instead of looping back to the LLM (which would hallucinate "done" without
    # ever executing the action). route_from_react_execute_tools routes on this.
    # We ALWAYS set these keys (None / [] when no draft) so a stale value from a
    # previous turn can never mis-route the loop — the router does not reset them.
    result["pending_draft_critique"] = pending_drafts[0] if pending_drafts else None
    result["pending_drafts_queue"] = pending_drafts[1:] if len(pending_drafts) > 1 else []

    if pending_drafts:
        # The draft handoff short-circuits the loop before react_finalize, so emit
        # the ReAct completion metrics here to keep the dashboards accurate.
        iteration = state.get("react_iteration", 0)
        start_time = state.get("react_start_time")
        duration_s = time.time() - start_time if start_time else 0.0
        _record_react_metrics(iteration, duration_s, "draft")
        # Minimal metadata for debug/observability. final_message is intentionally
        # empty so response_node uses the draft execution result (not a passthrough,
        # which is guarded by `if react_result.get("final_message")`).
        result["react_agent_result"] = {
            "final_message": "",
            "iteration_count": iteration,
            "mode": "react",
        }
        logger.info(
            "react_draft_handoff",
            draft_count=len(pending_drafts),
            primary_draft_id=pending_drafts[0].get("draft_id"),
            primary_draft_type=pending_drafts[0].get("draft_type"),
            iteration=iteration,
        )

    return result


# ---------------------------------------------------------------------------
# Node 4: react_finalize
# ---------------------------------------------------------------------------


@trace_node("react_finalize")
@track_metrics(node_name="react_finalize", duration_metric=agent_node_duration_seconds)
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
        # Normalize str (most providers) and list[dict] blocks (Gemini 3.x) to text.
        final_content = coerce_content_to_text(last_message.content)

    # Prometheus metrics (shared helper — also used by the draft handoff path)
    duration_s = time.time() - start_time if start_time else 0.0
    _record_react_metrics(iteration, duration_s, "success" if final_content else "empty")

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
