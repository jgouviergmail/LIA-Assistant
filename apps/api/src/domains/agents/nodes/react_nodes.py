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
from contextlib import suppress
from typing import Any

import structlog
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.core.config import settings
from src.core.exchange_rhythm import ExchangeRhythm
from src.core.run_config import run_id_of
from src.domains.agents.analysis.query_intelligence_helpers import (
    get_qi_attr,
    get_query_intelligence_from_state,
)
from src.domains.agents.constants import STATE_KEY_CURRENT_TURN_ID
from src.domains.agents.models import MessagesState, count_messages_tokens_cached
from src.domains.agents.nodes import react_context
from src.domains.agents.nodes.react_call_execution import CallPorts, execute_call
from src.domains.agents.nodes.react_drafts import extract_draft_info as _extract_draft_info
from src.domains.agents.nodes.react_egress_question import invoke_with_settlement
from src.domains.agents.nodes.react_execution import (
    execute_checkpointed_batch,
    latest_answered_calls,
)
from src.domains.agents.nodes.react_history import (
    window_messages_for_react as _window_messages_for_react,
)
from src.domains.agents.nodes.react_observed_gaps import (
    proven_final_content,
    requested_final_report,
    requested_outcome_block,
)
from src.domains.agents.nodes.react_output_guard import model_call_update
from src.domains.agents.nodes.react_prompt import build_bound_system_prompt
from src.domains.agents.nodes.react_recovery import recovery_report, with_recovery_directives
from src.domains.agents.nodes.react_turn_layout import (
    compose_turn_messages,
    extended_cache_horizon,
    frequent_exchanges,
    react_slot_provider,
)
from src.domains.agents.nodes.router_tool_scoring import GLOBAL_RANKING_KEY
from src.domains.agents.orchestration.step_timeouts import compute_step_timeout
from src.domains.agents.services.react_tool_selector import (
    ReactToolSelector,
    bound_tool_tokens,
)
from src.domains.agents.sms.state_policy import guard_sms_state
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.tool_resolution import (
    resolve_tool_instance,
)
from src.domains.agents.utils.react_budget import (
    abandoned_call_message,
    effective_react_budget,
    loop_cut_reason,
    slot_tool_result_budget,
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
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.prompt_cache_horizon import extended_prompt_cache_horizon
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
)
from src.infrastructure.observability.metrics_react import (
    react_agent_duration_seconds,
    react_agent_executions_total,
    react_agent_iterations,
    react_bound_tool_tokens,
    react_context_window_utilization,
    react_delivered_context_tokens,
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

    # Select and wrap tools — by relevance when the router ranked them (ADR-293),
    # every tool when the turn's rhythm is frequent (ADR-308, ADR-311).
    selector = ReactToolSelector()
    ranking = (state.get("tool_selection_result") or {}).get(GLOBAL_RANKING_KEY)
    frequent = frequent_exchanges(state)
    wrapped_tools, hitl_map = (
        selector.select(intelligence, ranking=ranking, every_tool=frequent)
        if intelligence
        else ([], {})
    )
    tool_names = [t.name for t in wrapped_tools]
    schema_tokens = bound_tool_tokens(wrapped_tools)
    with suppress(Exception):  # a metric never breaks the turn
        react_bound_tool_tokens.observe(schema_tokens)

    # Build system prompt — it promises only what this turn can actually run,
    # and about the network only what this ACCOUNT may reach (ADR-298).
    system_prompt = await build_bound_system_prompt(state, tool_names)

    # Context blocks, in injection ORDER (react_context.build_setup_blocks).
    setup_blocks = await react_context.build_setup_blocks(state, config)
    system_blocks: list[str] = [system_prompt, *setup_blocks.blocks]

    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(
        "react_setup_complete",
        # The rhythm the setup bound on (ADR-311): it was in no log line, so a
        # frequent turn that fell back read exactly like an occasional one.
        exchange_rhythm=(
            ExchangeRhythm.FREQUENT.value if frequent else ExchangeRhythm.OCCASIONAL.value
        ),
        tool_count=len(tool_names),
        bound_tool_tokens=schema_tokens,
        hitl_count=sum(1 for v in hitl_map.values() if v),
        domains=get_qi_attr(state, "domains", default=[]),
        has_memory_context=setup_blocks.has_memory,
        has_knowledge_context=setup_blocks.has_knowledge,
        has_skills_catalog=bool(setup_blocks.skills_catalog),
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
    with suppress(Exception):
        delivered = count_messages_tokens_cached(messages)
        react_delivered_context_tokens.observe(delivered)

        from src.core.llm_config_helper import get_effective_context_window_for_slot

        # The window THIS slot works with (ADR-278) — its own override when an
        # operator set one, else what the model declares. Reading it from the
        # slot rather than from the model name is what lets a cheap ReAct loop
        # and an expensive responder run the same model with two windows.
        window = get_effective_context_window_for_slot("react_agent")
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
    state = await guard_sms_state(state)
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
    # non-consecutive system block for Anthropic to reject. For frequent
    # exchanges (ADR-308, ADR-311) the turn's context follows the question
    # instead, in the shape its provider takes, so the static prompt alone
    # leads, and the history drops by blocks.
    cross_turn = frequent_exchanges(state)
    system_blocks = list(state.get("react_system_blocks") or [])
    from src.domains.agents.services.efficacy_runtime import (
        build_efficacy_block,
        efficacy_context_from_state,
        verifier_available_in_state,
    )

    efficacy_block = await build_efficacy_block(
        efficacy_context_from_state(state),
        run_id=run_id_of(config),
        state=state,
        can_verify=verifier_available_in_state(state),
    )
    if efficacy_block:
        system_blocks.append(efficacy_block)
    coverage_block = requested_outcome_block(state)
    if coverage_block:
        system_blocks.append(coverage_block)
    messages = compose_turn_messages(
        system_blocks,
        _window_messages_for_react(
            state["messages"],
            turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
            blocks=cross_turn,
            turn_started_at=state.get("react_start_time"),
        ),
        context_after_question=cross_turn,
        provider=react_slot_provider() if cross_turn else None,
    )
    # ADR-310: a recovery pass shows the model its draft and its gaps right after
    # the draft's place — composed per call, never written to the thread.
    messages = with_recovery_directives(messages, state.get("react_recovery_passes") or [])

    _observe_delivered_context(messages)

    # Stream the model's reasoning live (thinking models) to the progress UI via
    # the custom channel, while returning the SAME aggregated AIMessage as
    # ``ainvoke`` (tool_calls/content identical — proven by prod POC). On any
    # failure or empty result, fall back to ``ainvoke`` so the loop never breaks.
    from src.infrastructure.llm.reasoning_stream import (
        make_reasoning_emit,
        stream_reasoning_events,
    )

    # The per-node metrics handler every node hands its model call: without it the
    # loop's tokens, cost and cache writes reached the ledger and no Prometheus
    # metric (measured on dev, 2026-10-22). The ledger's callback is kept.
    config = enrich_config_with_node_metadata(config, "react_call_model")

    # ADR-362: the call's cross-turn read points live the provider's extended
    # lifetime when the next turn is minutes away (frequent, a person waiting).
    response: AIMessage | None = None
    with extended_prompt_cache_horizon(extended_cache_horizon(state)):
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

    # ADR-275 (amended): a reply the provider cut at its budget never reaches the
    # thread — the guard decides what this call writes.
    return model_call_update(
        response,
        iteration=iteration,
        # ADR-170: charge this node's COMPUTE time, never wall clock. A node
        # that gets interrupted never returns, so the seconds a user spends
        # deciding on an approval are structurally excluded — which is the whole
        # point: they used to count against the loop's timeout.
        elapsed_seconds=(state.get("react_elapsed_seconds") or 0.0)
        + (time.perf_counter() - node_started),
    )


# ---------------------------------------------------------------------------
# Node 3: react_execute_tools
# ---------------------------------------------------------------------------


@trace_node("react_execute_tools")
@track_metrics(node_name="react_execute_tools", duration_metric=agent_node_duration_seconds)
async def react_execute_tools_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, object]:
    """Execute one checkpointed segment before the next interruptible call."""
    return await execute_checkpointed_batch(state, config, _execute_react_calls)


async def _execute_react_calls(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, object]:
    """Assemble runtime ports for the isolated, typed singleton executor."""
    from src.domains.agents.context.store import get_tool_context_store
    from src.domains.agents.orchestration.parallel_executor import _build_tool_runtime

    ports = CallPorts(
        wrappers=_rebuild_wrapped_tools,
        invoke=invoke_with_settlement,
        runtime=_build_tool_runtime,
        interrupt=interrupt,
        timeout=compute_step_timeout,
        draft=_extract_draft_info,
        result_budget=slot_tool_result_budget("react_agent"),
        store=await get_tool_context_store(),
    )
    result = await execute_call(state, config, ports)
    if result.get("pending_draft_critique"):
        _record_react_metrics(
            state.get("react_iteration", 0), _loop_compute_seconds(state), "draft"
        )
    return result


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
    answered = latest_answered_calls(messages)
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
    # handoff above. A model output the provider CUT never entered the thread
    # (ADR-275, amended): nothing here is an answer either, and the same path serves.
    last_message = state["messages"][-1] if state.get("messages") else None
    final_content = ""
    if isinstance(last_message, AIMessage):
        # Normalize str (most providers) and list[dict] blocks (Gemini 3.x) to text.
        final_content = coerce_content_to_text(last_message.content)

    # Resolved ONCE: the banner the user reads and the result the model is given
    # must name the same stop condition (ADR-248).
    from src.domains.agents.nodes.react_execution import pending_calls

    pending_request, pending = pending_calls(state)
    unfinished = pending_request if pending else last_message
    reason = loop_cut_reason(state, unfinished)
    truncation: dict[str, Any] | None = None
    abandoned: list[ToolMessage] = []
    if reason is not None:
        truncation = {
            "reason": reason,
            "iterations": iteration,
        }
        final_content = ""
        # The loop closes its own books. Pending calls will never run, and an
        # AIMessage whose tool_calls stay unanswered poisons the checkpoint:
        # the provider rejects the WHOLE history on every later turn of the
        # thread (measured 2026-09-02). Answering them makes the history valid
        # by construction and tells the model what it lost, instead of letting
        # it silently re-derive the same work next turn. The turn-start repair
        # stays the safety net for what no node can close — a hard kill. (A cut
        # output leaves none: its calls never entered the thread.)
        abandoned = _abandoned_tool_outputs(state["messages"], unfinished, reason)

    # Prometheus metrics (shared helper — also used by the draft handoff path).
    # COMPUTE time, not wall clock: a turn that waited on a HITL approval would
    # otherwise report the user's thinking time as ReAct latency and skew the
    # dashboards (ADR-170).
    compute_s = _loop_compute_seconds(state)
    tool_s = _loop_tool_seconds(state)
    # ADR-310: what the recovery passes achieved — and, when a pass left no usable
    # answer, the last draft it had taken off the thread, which IS the answer.
    recovery = recovery_report(state, last_message, cut=reason is not None)
    final_content = proven_final_content(state, recovery.pop("final_message", final_content))
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
    react_result.update(recovery)
    react_result.update(requested_final_report(state))
    if abandoned:
        # The same list the log line carries, where a person reading the debug
        # panel can see it: which capabilities the turn asked for and never got
        # is what says whether the budget is calibrated (B8).
        react_result["abandoned_calls"] = [m.name for m in abandoned if m.name]
    update: dict[str, Any] = {"react_agent_result": react_result}
    if abandoned:
        update["messages"] = abandoned
    return update
