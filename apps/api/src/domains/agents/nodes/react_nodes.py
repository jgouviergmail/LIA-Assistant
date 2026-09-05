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

import asyncio
import contextlib
import time
from typing import Any

import structlog
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
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
from src.domains.agents.effects.scope import effect_scope, react_call_scope
from src.domains.agents.models import MessagesState, count_messages_tokens_cached
from src.domains.agents.nodes import react_context
from src.domains.agents.nodes.react_history import (
    window_messages_for_react as _window_messages_for_react,
)
from src.domains.agents.orchestration.step_timeouts import compute_step_timeout
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.connector_error_notice import (
    emit_connector_notice_for_exception,
)
from src.domains.agents.services.hitl.protocols import HitlInteractionType
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.tool_resolution import (
    classify_unresolved_tool_call,
    resolve_tool_instance,
)
from src.domains.agents.utils.loop_guard import (
    compute_call_digest,
    register_call,
    repeated_call_message,
)
from src.domains.agents.utils.react_budget import (
    TIMEOUT_ATTRIBUTION_MARGIN,
    abandoned_call_message,
    effective_react_budget,
    react_exit_reason,
    tool_timeout_message,
)
from src.domains.agents.utils.react_budget import (
    loop_compute_seconds as _loop_compute_seconds,
)
from src.domains.agents.utils.react_budget import (
    loop_tool_seconds as _loop_tool_seconds,
)
from src.domains.agents.utils.react_budget import (
    uncharged_wall_seconds as _uncharged_wall_seconds,
)
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    semantic_param_guard_blocks_total,
)
from src.infrastructure.observability.metrics_react import (
    react_agent_duration_seconds,
    react_agent_executions_total,
    react_agent_hitl_interrupts_total,
    react_agent_iterations,
    react_agent_tools_called_total,
    react_context_window_utilization,
    react_delivered_context_tokens,
    react_repeated_calls_total,
    react_tool_executions_before_interrupt_total,
    react_unknown_tool_calls_total,
)
from src.infrastructure.observability.tracing import trace_node

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _is_productive_result(raw_result: Any) -> bool:
    """Did this tool call actually bring something back?

    Productivity is what buys more iterations (ADR-248), so it must mean
    "the context learned something", never "a call was attempted". A declared
    failure and an empty result both teach the loop nothing it can build on.

    Args:
        raw_result: The tool's return value, before string conversion.

    Returns:
        True when the call produced usable content.
    """
    if raw_result is None:
        return False
    if isinstance(raw_result, dict):
        return raw_result.get("success") is not False
    return bool(raw_result)


def _record_react_metrics(iteration: int, duration_s: float, status: str) -> None:
    """Record ReAct loop completion metrics.

    Shared by ``react_finalize_node`` (normal completion) and
    ``react_execute_tools_node`` (when the loop is short-circuited because a
    mutation tool produced a draft that is handed off to the draft_critique HITL
    flow). Without this, draft-terminated ReAct turns would be invisible in the
    ReAct dashboards.

    ``duration_s`` is the REASONING duration, not the turn's total: tool time is
    already carried per tool by ``agent_tool_duration_seconds``. Folding it in
    here would break a historical series to fix a sentence — the metric's help
    text and the dashboard descriptions say what it measures instead (ADR-256).

    Args:
        iteration: Number of ReAct iterations performed during the turn.
        duration_s: ReAct reasoning duration in seconds.
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

    # Context blocks, in injection ORDER — the order is meaningful. Standing
    # rules lead: they govern how everything after them is used. Each builder is
    # best-effort and returns None when it has nothing to say (zero tokens).
    system_blocks: list[str] = [system_prompt]
    context_blocks = [
        # Memory parity with the pipeline (2026-08-28): a behavioural rule that
        # only reaches the response node can reword a promise, never turn it
        # into an action. It has to be present where the decision is taken.
        await react_context.build_memory_profile_block(state, config),
        react_context.build_reference_resolution_block(state, intelligence),
        await react_context.build_user_model_block(config),
        await react_context.build_journal_directives_block(state, config),
        react_context.build_skills_catalog_block(config),
        await react_context.build_degradations_block(),
        await react_context.build_mcp_auth_notices_block(),
    ]
    system_blocks.extend(block for block in context_blocks if block)
    has_memory_block = bool(context_blocks[0])
    skills_catalog = context_blocks[4] or ""

    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(
        "react_setup_complete",
        tool_count=len(tool_names),
        hitl_count=sum(1 for v in hitl_map.values() if v),
        domains=get_qi_attr(state, "domains", default=[]),
        has_memory_context=has_memory_block,
        has_skills_catalog=bool(skills_catalog),
        duration_ms=duration_ms,
    )

    # ADR-238: adaptive iteration budget from the query's domain span —
    # computed ONCE per turn here; the router reads it (ceiling fallback).
    effective_budget: int | None = None
    if settings.react_adaptive_budget_enabled:
        effective_budget = effective_react_budget(
            len(get_qi_attr(state, "domains", default=[]) or []),
            base=settings.react_iterations_base,
            per_extra_domain=settings.react_iterations_per_extra_domain,
            ceiling=settings.react_agent_max_iterations,
        )

    return {
        "react_tool_names": tool_names,
        "react_hitl_map": hitl_map,
        "react_iteration": 0,
        # ADR-249: a new turn starts with a full ephemeral-script budget.
        # The COUNTER lives in state, never in a ContextVar: a `.set()` in
        # one task is invisible in a sibling task, and the runner is free to
        # invoke each node in its own.
        "react_script_runs": 0,
        "react_max_iterations_effective": effective_budget,
        "react_start_time": time.time(),
        # The turn's system blocks are STATE, not messages (ADR-169). Appending
        # them to `messages` persisted one copy per turn: the windowing hoisted
        # every past copy to the front, so the payload carried the ReAct prompt
        # N times (840 tok each) and the cacheable prefix changed on every turn.
        # On Anthropic it was worse than costly — hoisted-old + appended-new are
        # NON-CONSECUTIVE system messages, which the provider rejects outright.
        "react_system_blocks": system_blocks,
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


def _observe_delivered_context(messages: list[BaseMessage]) -> None:
    """Measure the prompt about to be delivered to the ReAct model (Lot D).

    Uses the reducer's memoized per-message counter, so unchanged history
    costs nothing to re-count; only the fresh system blocks (no message id)
    are encoded each call. The window ratio reads the effective model through
    the same DB-backed seam the compaction threshold uses (ADR-244).
    """
    # Observability is best-effort by contract: a tokenizer or catalogue
    # hiccup must never break the loop, so the whole block swallows —
    # the metric's absence IS the signal in that case.
    with contextlib.suppress(Exception):
        delivered = count_messages_tokens_cached(messages)
        react_delivered_context_tokens.observe(delivered)

        from src.core.llm_config_helper import (
            get_effective_context_window,
            get_llm_config_for_agent,
        )

        model = get_llm_config_for_agent(settings, "react_agent").model
        window = get_effective_context_window(model)
        if window > 0:
            react_context_window_utilization.observe(delivered / window)


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
    node_started = time.perf_counter()
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
    #
    # The turn's system blocks are recomposed HERE, as a leading block, instead of
    # living in `messages` (ADR-169). Leading and contiguous means: one merged
    # system block for the provider, a prefix whose bytes do not change from one
    # turn to the next (so prompt caching can actually hit), and no second,
    # non-consecutive system block for Anthropic to reject.
    windowed = _window_messages_for_react(state["messages"])
    system_blocks = state.get("react_system_blocks") or []
    messages: list[BaseMessage] = [
        SystemMessage(content=block) for block in system_blocks
    ] + windowed

    _observe_delivered_context(messages)

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
        # ADR-170: charge this node's COMPUTE time, never wall clock. A node
        # that gets interrupted never returns, so the seconds a user spends
        # deciding on an approval are structurally excluded — which is the whole
        # point: they used to count against the loop's timeout.
        "react_elapsed_seconds": (state.get("react_elapsed_seconds") or 0.0)
        + (time.perf_counter() - node_started),
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

    Idempotence, and its documented limit: a tool_call is skipped when a
    ToolMessage for it already exists **in state**. That covers previous node
    executions, NOT the current one — an interrupted node never returns, so the
    ToolMessages it produced before the interrupt are never persisted, and every
    call preceding the interrupt is replayed on resume (double quota, double
    latency, and an approval decided on data that may have changed since). The
    replay is counted by ``react_tool_executions_before_interrupt_total`` so the
    real blast radius
    can be measured before the node is restructured; it is bounded by the single
    tool allowed to interrupt here (see ``test_hitl_required_consistency``).

    HITL: Mutation tools (hitl_required=True) trigger interrupt() which pauses
    the graph and waits for user approval. On resume, previously-matched
    interrupts return their resume value immediately (LangGraph index matching).

    IMPORTANT: Tool calls are processed in the EXACT order from AIMessage.tool_calls.
    Never reorder — interrupt() matching is index-based.

    Args:
        state: Current graph state with messages and tool metadata.
        config: RunnableConfig (thread plumbing); tool dependencies travel on the run context.

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
    productive_calls = 0
    # ADR-256: the delegated half of the turn. Accumulated here and
    # returned to state, because the ContextVars do not survive the node.
    tool_seconds_spent = 0.0

    # ADR-249: load this invocation's script budget and data from STATE.
    from src.domains.agents.tools.python_sandbox_tools import runs_spent, seed_turn

    seed_turn(
        runs_spent=int(state.get("react_script_runs") or 0),
        items=dict(state.get("current_turn_registry") or {}),
    )
    pending_drafts: list[dict[str, Any]] = []
    call_digests: dict[str, int] = dict(state.get("react_call_digests") or {})
    no_progress = False

    # Index of the first call that will interrupt. Every call BEFORE it runs in
    # an execution that cannot return, so its result is discarded and the call
    # runs again on resume.
    #
    # What the counter measures, precisely: executions that sit before an
    # interrupt — NOT redundant executions. Nothing in state distinguishes the
    # first pass from the resume (the interrupted pass persisted nothing), so
    # one interrupt yields TWO samples for one wasted execution. Read it as
    # `samples − distinct calls = redundant executions`. Naming it "replayed"
    # would have overstated the waste by a factor of two.
    first_hitl_index = next(
        (
            index
            for index, call in enumerate(last_message.tool_calls)
            if hitl_map.get(call["name"], False)
        ),
        len(last_message.tool_calls),
    )

    for call_index, tool_call in enumerate(last_message.tool_calls):
        tc_id: str = tool_call["id"]
        tc_name: str = tool_call["name"]
        tc_args: dict[str, Any] = tool_call.get("args", {})

        # IDEMPOTENCE: skip if already executed
        if tc_id in existing_tool_msg_ids:
            continue

        # This execution sits before an interrupt, so it cannot be persisted
        # (see the node docstring). Measured, not yet prevented.
        if call_index < first_hitl_index:
            react_tool_executions_before_interrupt_total.labels(tool_name=tc_name).inc()

        # Parity with the parallel executor: a textual "no value" ("null",
        # "none", ...) on an optional typed parameter means "not provided".
        # Deterministic, so re-executing after an interrupt is stable.
        tc_args = strip_placeholder_arguments(tc_name, tc_args)

        # NO-PROGRESS GUARD (ADR-170) — placed AFTER the idempotence skip on
        # purpose: that is what makes it replay-safe. An interrupted execution
        # never returns, so its increments are discarded with the rest of its
        # partial work; on resume, only the calls that still lack a ToolMessage
        # are counted, exactly once. Counting before the skip would charge a
        # resumed turn twice and could block a legitimate call.
        call_digests, verdict = register_call(
            call_digests,
            compute_call_digest(tc_name, tc_args, settings.secret_key),
            block_threshold=settings.react_repeated_call_block_threshold,
            terminal_threshold=settings.react_repeated_call_terminal_threshold,
        )
        if verdict != "allow":
            # No PII: the arguments are the user's own data, only the tool name
            # and the verdict are recorded.
            logger.warning(
                "react_repeated_call_blocked",
                tool_name=tc_name,
                verdict=verdict,
                iteration=state.get("react_iteration", 0),
            )
            react_repeated_calls_total.labels(tool_name=tc_name, verdict=verdict).inc()
            new_messages.append(
                ToolMessage(
                    content=repeated_call_message(verdict),
                    tool_call_id=tc_id,
                    name=tc_name,
                )
            )
            no_progress = no_progress or verdict == "terminal"
            continue

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
            # ADR-256: this branch used to be silent. `not_selected` means the
            # cap or the per-request filtering dropped a real tool; `unknown`
            # means the model invented the name. Opposite fixes, so they are
            # counted apart — and the NAME stays out of the label set, since it
            # comes from a model and its cardinality is unbounded.
            reason = classify_unresolved_tool_call(tc_name)
            react_unknown_tool_calls_total.labels(reason=reason).inc()
            logger.warning(
                "react_tool_call_unresolved",
                tool_name=tc_name,
                reason=reason,
                bound_tools=len(tool_by_name),
            )
            new_messages.append(
                ToolMessage(
                    content=f"Tool '{tc_name}' not found.",
                    tool_call_id=tc_id,
                    name=tc_name,
                )
            )
            continue

        # ADR-256: the pipeline bounds every tool family through this exact
        # policy; ReAct bounded none, so the same delegating tool ran capped at
        # 300 s in one mode and unbounded in the other. One policy, two callers.
        tool_timeout = compute_step_timeout(tc_name, None)
        tool_started = time.perf_counter()
        try:
            # Inject ToolRuntime into args (required by ConnectorTools).
            # LangChain's InjectedToolArg is normally injected by ToolNode,
            # but we call tools directly — so we must build ToolRuntime manually.
            # Pattern: parallel_executor._build_tool_runtime()
            injected_args = _build_tool_runtime(wrapper._original_tool, tc_args, config, store)
            # ADR-263: the authority. ``tc_id`` is the key that makes one
            # approval one execution, and ``is_mutation`` is True only past the
            # interrupt above — so it IS the user's confirmation.
            with effect_scope(react_call_scope(config, tc_id, approved=is_mutation)):
                raw_result = await asyncio.wait_for(
                    wrapper._original_tool.coroutine(**injected_args),
                    timeout=tool_timeout,
                )
            # Process through wrapper for string conversion + registry collection
            content = wrapper._process_result(raw_result)
            productive_calls += _is_productive_result(raw_result)
            # Draft detection: a mutation tool (create/update/delete) returns
            # requires_confirmation=True — it prepared a DRAFT, not the real
            # action. Collect it for the HITL handoff (see return below).
            draft_info = _extract_draft_info(raw_result, tc_name)
            if draft_info is not None:
                pending_drafts.append(draft_info)
        except TimeoutError:
            # Recoverable, like the pipeline's failed StepResult: the model is
            # told what happened and can choose another route. Killing the node
            # would discard the tool results that DID come back this iteration.
            # The wording lives with its two siblings in ``react_budget`` and
            # decides for itself WHICH timeout fired — see that function.
            elapsed = time.perf_counter() - tool_started
            content = tool_timeout_message(tc_name, bound_s=tool_timeout, elapsed_s=elapsed)
            logger.warning(
                "react_execute_tools_timeout",
                tool_name=tc_name,
                timeout_seconds=tool_timeout,
                elapsed_seconds=round(elapsed, 1),
                enforced_by=(
                    "react_budget"
                    if elapsed >= tool_timeout * TIMEOUT_ATTRIBUTION_MARGIN
                    else "tool"
                ),
            )
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

        # Charged whatever the outcome: a call that failed or timed out still
        # spent the time. Placed outside the try so no branch can forget it.
        tool_seconds_spent += time.perf_counter() - tool_started

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

    result: dict[str, Any] = {"messages": new_messages, "react_call_digests": call_digests}
    if tool_seconds_spent:
        # Cumulative across the turn's iterations: the budget bounds the
        # WHOLE turn, not one node execution.
        result["react_tool_seconds"] = (
            float(state.get("react_tool_seconds") or 0.0) + tool_seconds_spent
        )

    # ADR-249: what the sandbox ran (admin debug panel only) and what it spent,
    # both returned to STATE — the ContextVars do not survive the next node.
    from src.domains.agents.tools.python_sandbox_tools import drain_turn_scripts

    scripts = drain_turn_scripts()
    if scripts:
        result["react_scripts"] = list(state.get("react_scripts") or []) + scripts
    result["react_script_runs"] = runs_spent()
    if productive_calls:
        # ADR-248: one PRODUCTIVE iteration, whatever the number of calls in it.
        result["react_productive_iterations"] = (
            int(state.get("react_productive_iterations", 0) or 0) + 1
        )
    if no_progress:
        # Terminal repetition: hand the loop its own iteration ceiling so the
        # NEXT routing finalises. Cutting the edge here instead would skip
        # react_finalize, and the response node reads its result contract.
        result["react_iteration"] = settings.react_agent_max_iterations
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
        _record_react_metrics(iteration, _loop_compute_seconds(state), "draft")
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


def _abandoned_tool_outputs(
    messages: list[BaseMessage],
    last_message: BaseMessage | None,
    reason: str,
) -> list[ToolMessage]:
    """Build one explicit result per tool call the loop will never run.

    Args:
        messages: The turn's history, read to find calls a ``ToolMessage``
            already answers — two results for one ``tool_call_id`` would be
            the very malformation this function exists to prevent.
        last_message: The turn's last message — the carrier of the pending calls.
        reason: The already-resolved stop condition, shared verbatim with
            ``react_agent_result.truncation``.

    Returns:
        One ``ToolMessage`` per IDENTIFIED pending call, flagged ``error`` (the
        call did not succeed; the model must not read it as data). A call with
        no id is skipped rather than paired by guesswork — inventing a
        ``tool_call_id`` would corrupt the history this function exists to keep
        valid. The turn-start repair removes those.

        That skip is reachable, not decoration: ``AIMessage`` validates
        ``tool_calls`` at CONSTRUCTION only, so ``id: None`` survives a
        checkpoint round-trip and a post-construction append bypasses the
        check entirely (both measured 2026-09-02).
    """
    answered = {
        m.tool_call_id
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None)
    }
    body = abandoned_call_message(reason)
    return [
        ToolMessage(
            content=body,
            tool_call_id=str(call["id"]),
            name=call.get("name"),
            status="error",
        )
        for call in getattr(last_message, "tool_calls", None) or []
        if isinstance(call, dict) and call.get("id") and call["id"] not in answered
    ]


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

    # A final AIMessage carries no tool_calls. One that still does is MID-THOUGHT:
    # its text is the model narrating what it is about to do, and those calls will
    # never run — the loop is over. Serving it hands the user a promise instead of
    # an answer, and this product has no background continuation to honour it
    # (production, 2026-08-28). An empty final message routes the response node to
    # synthesise from the tool results that DID come back, exactly like the draft
    # handoff above.
    last_message = state["messages"][-1] if state.get("messages") else None
    final_content = ""
    if isinstance(last_message, AIMessage):
        # Normalize str (most providers) and list[dict] blocks (Gemini 3.x) to text.
        final_content = coerce_content_to_text(last_message.content)

    pending_tool_calls = bool(getattr(last_message, "tool_calls", None))
    exit_reason = react_exit_reason(state) if pending_tool_calls else None
    truncation: dict[str, Any] | None = None
    abandoned: list[ToolMessage] = []
    if pending_tool_calls:
        # Resolved ONCE: the banner the user reads and the result the model is
        # given must name the same stop condition (ADR-248).
        reason = exit_reason or "pending_tool_calls"
        truncation = {
            "reason": reason,
            "iterations": iteration,
        }
        final_content = ""
        # The loop closes its own books. Those calls will never run, and an
        # AIMessage whose tool_calls stay unanswered poisons the checkpoint:
        # the provider rejects the WHOLE history on every later turn of the
        # thread (measured 2026-09-02). Answering them makes the history valid
        # by construction and tells the model what it lost, instead of letting
        # it silently re-derive the same work next turn. The turn-start repair
        # stays the safety net for what no node can close — a hard kill.
        abandoned = _abandoned_tool_outputs(state["messages"], last_message, reason)

    # Prometheus metrics (shared helper — also used by the draft handoff path).
    # COMPUTE time, not wall clock: a turn that waited on a HITL approval would
    # otherwise report the user's thinking time as ReAct latency and skew the
    # dashboards (ADR-170).
    compute_s = _loop_compute_seconds(state)
    tool_s = _loop_tool_seconds(state)
    _record_react_metrics(iteration, compute_s, "success" if final_content else "empty")

    logger.info(
        "react_finalize_complete",
        total_iterations=iteration,
        has_final_content=bool(final_content),
        # Which capabilities the turn asked for and never got: the signal that
        # says whether the budget is calibrated, not merely that it was hit.
        abandoned_calls=[m.name for m in abandoned] or None,
        compute_seconds=round(compute_s, 2),
        # ADR-256: the delegated half, previously charged to nothing at all.
        tool_seconds=round(tool_s, 2),
        # wall - (compute + tools): HITL wait on an interrupted turn, graph
        # overhead otherwise. The router logs the same quantity from the same
        # helper — two copies of this arithmetic would drift (ADR-170).
        uncharged_wall_seconds=_uncharged_wall_seconds(state, compute_s + tool_s),
    )

    react_result: dict[str, Any] = {
        "final_message": final_content,
        "iteration_count": iteration,
        "mode": "react",
    }
    if truncation is not None:
        react_result["truncation"] = truncation
    update: dict[str, Any] = {"react_agent_result": react_result}
    if abandoned:
        update["messages"] = abandoned
    return update
