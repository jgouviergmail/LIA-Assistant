"""
Router Node - INTELLIGENT.

Architecture v3.2 - Intelligence, Autonomy, Relevance.

Responsibilities:
1. Call QueryAnalyzerService.analyze_full()
2. Update state with rich analysis
3. Return routing decision with reasoning

All INTELLIGENCE is in QueryAnalyzerService (unified service).
This node is intentionally simple (~80 lines instead of legacy ~1430 lines).
"""

import asyncio
from contextlib import suppress
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    EXECUTION_MODE_AUTO,
    EXECUTION_MODE_CHOICES,
    EXECUTION_MODE_JUDGEMENT_CANCEL_GRACE_SECONDS,
    EXECUTION_MODE_PIPELINE,
    STATE_KEY_INITIATIVE_FOLLOWUPS,
    STATE_KEY_INITIATIVE_ITERATION,
    STATE_KEY_INITIATIVE_RESULTS,
    STATE_KEY_INITIATIVE_SKIPPED_REASON,
    STATE_KEY_INITIATIVE_SUGGESTION,
)
from src.core.exchange_rhythm import effective_exchange_rhythm
from src.core.run_config import run_id_of
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.constants import (
    INTENTION_ACTION,
    INTENTION_CONVERSATION,
    STATE_KEY_CLARIFICATION_FIELD,
    STATE_KEY_CLARIFICATION_RESPONSE,
    STATE_KEY_COMPLETED_STEPS,
    STATE_KEY_DETECTED_INTENT,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_MESSAGES,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_PLANNING_RESULT,
    STATE_KEY_RESOLVED_CONTEXT,
    STATE_KEY_ROUTING_HISTORY,
    STATE_KEY_SEMANTIC_VALIDATION,
    STATE_KEY_TURN_TYPE,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.context.runtime_context import (
    executed_mode_of,
    runtime_context_if_running,
)
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.effects.decisions import note_engine
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.draft_sequence import draft_turn_reset
from src.domains.agents.nodes.router_tool_scoring import score_tools_for_turn
from src.domains.agents.services.analysis.jev_execution_mode import judge_request_shape
from src.domains.agents.services.engine_resolution import EngineReason, resolve_engine
from src.domains.agents.sms.state_policy import guard_sms_state
from src.domains.agents.utils.react_budget import react_turn_reset
from src.domains.agents.utils.state_tracking import track_state_updates
from src.domains.agents.utils.turn_type import normalize_turn_type
from src.infrastructure.async_utils import cancel_and_wait
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics import router_confidence_score
from src.infrastructure.observability.metrics_agents import (
    agent_node_duration_seconds,
    agent_node_executions_total,
    get_confidence_bucket,
    router_data_presumption_total,
    router_decisions_total,
    router_fallback_total,
    router_latency_seconds,
)
from src.infrastructure.observability.metrics_langgraph import execution_mode_resolutions_total
from src.infrastructure.observability.tracing import trace_node

logger = get_logger(__name__)


# New state keys for v3
STATE_KEY_QUERY_INTELLIGENCE = "query_intelligence"


def _requested_execution_mode() -> str:
    """What the run was asked to run in (ADR-070), from the typed context.

    Read through the run-scoped context rather than ``config["configurable"]``
    (ADR-231): the mode is a user preference the chokepoint owns, not LangGraph
    plumbing. Outside a run — a direct call from a unit test or a script — the
    canonical default applies, which is what the previous bag lookup did whenever
    the key was absent.

    Returns:
        The requested mode, as stored.
    """
    context = runtime_context_if_running()
    return context.requested_execution_mode if context is not None else EXECUTION_MODE_PIPELINE


def _start_shape_judgement(query: str) -> asyncio.Task[EngineReason] | None:
    """The decision provider's judgement of the request's shape (ADR-390).

    Started beside the analysis (~0.2 s against ~3 s), and only where a choice is
    left to make — an « auto » turn on an instance that runs the loop — so nothing
    else is judged, and nothing else is billed.

    Args:
        query: The person's words.

    Returns:
        The owned task, or None when no judgement is needed.
    """
    if _requested_execution_mode() != EXECUTION_MODE_AUTO or not settings.react_agent_enabled:
        return None
    return asyncio.create_task(judge_request_shape(query), name="execution_mode_shape")


async def _abandon_shape_judgement(judgement: asyncio.Task[EngineReason] | None) -> None:
    """Cancel a judgement nothing will read, and wait for it to close."""
    if judgement is not None and not judgement.done():
        await cancel_and_wait(
            judgement, timeout_seconds=EXECUTION_MODE_JUDGEMENT_CANCEL_GRACE_SECONDS
        )


async def _settle_turn_engine(
    intelligence: QueryIntelligence, judgement: asyncio.Task[EngineReason] | None
) -> str:
    """The mode the turn's state carries, settling its engine when one plans it.

    A turn the router sends to planning gets ONE engine, published twice: into the
    state, which the routing edge reads, and on the context's holder, which tools,
    registers and metric labels read (``executed_mode_of``). The engine comes from
    ``resolve_engine``; the shape judgement is awaited only when the rule needs it.
    A turn that already runs (a resumed one, a compacted replay) keeps its engine.
    A conversation turn has no engine: its state says what the door answers.

    Args:
        intelligence: The turn's analysis.
        judgement: The shape judgement an « auto » turn started, if any.

    Returns:
        The engine in force for a planned turn, else what the door answers.
    """
    requested = _requested_execution_mode()
    context = runtime_context_if_running()
    if not intelligence.requires_planner():
        return executed_mode_of(context) if context is not None else requested
    loop_enabled = settings.react_agent_enabled
    resolution = resolve_engine(
        requested, intelligence, EngineReason.NO_DECISION, loop_enabled=loop_enabled
    )
    if resolution.reason is EngineReason.NO_DECISION and judgement is not None:
        resolution = resolve_engine(
            requested, intelligence, await judgement, loop_enabled=loop_enabled
        )
    if context is not None:
        in_force = context.turn_engine.settle(resolution.engine)
        if in_force != resolution.engine:
            logger.info("turn_engine_kept", engine=in_force, proposed=resolution.engine)
            return in_force
        note_engine(in_force, resolution.reason.value)
    execution_mode_resolutions_total.labels(
        requested=requested if requested in EXECUTION_MODE_CHOICES else "other",
        engine=resolution.engine,
        reason=resolution.reason.value,
    ).inc()
    return resolution.engine


def _resolve_exchange_rhythm() -> str:
    """The run's exchange rhythm (ADR-311), from the typed context.

    Read ONCE per turn, here: the ReAct loop reads the state the router writes,
    and a HITL resumption re-enters the interrupted node rather than the router,
    so a turn keeps the rhythm it started with — the tools bound at setup and the
    layout of every later call cannot disagree. Outside a run, the instance
    default applies.

    Returns:
        ``"frequent"`` or ``"occasional"``.
    """
    context = runtime_context_if_running()
    if context is not None:
        return context.exchange_rhythm.value
    return effective_exchange_rhythm(None).value


@trace_node("router_v3")
# duration_metric only: success/error executions are counted manually inside the
# node (agent_node_executions_total) — adding counter_metric here would double-count.
@track_metrics(node_name="router_v3", duration_metric=agent_node_duration_seconds)
async def router_node_v3(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Router node v3.2 - Simplified and Intelligent.

    ~80 lines instead of ~1430 lines.
    All intelligence is in QueryAnalyzerService (unified).

    Flow:
    1. Get QueryAnalyzerService
    2. Call analyze_full() (memory facts retrieval internalized)
    3. Build RouterOutput
    4. Update state with rich analysis

    The heavy lifting is done by QueryAnalyzerService.analyze_full():
    - Memory facts retrieval (internalized)
    - Intent detection
    - Domain selection
    - Context resolution
    - Goal inference
    - Routing decision
    """
    import time as _time

    from src.domains.agents.services.query_analyzer_service import (
        get_query_analyzer_service,
    )

    state = await guard_sms_state(state)
    _router_start = _time.perf_counter()
    messages = state[STATE_KEY_MESSAGES]

    # Extract run_id for logging
    run_id = run_id_of(config, "unknown")

    # Get last user message
    last_message = messages[-1] if messages else None
    query = ""
    if last_message and hasattr(last_message, "content"):
        query = coerce_content_to_text(last_message.content)

    logger.info(
        "router_v3_start",
        run_id=run_id,
        query_chars=len(query),  # counts only: the person's words never reach INFO
    )

    # Fence the generation BEFORE any asynchronous query analysis. A purge
    # while the model works must never be followed by lazy state recreation.
    from src.domains.agents.analysis.efficacy_context import EfficacyAnalysis
    from src.domains.agents.services.efficacy_runtime import (
        attach_efficacy_analysis,
        capture_efficacy_context,
    )

    efficacy_start = await capture_efficacy_context(EfficacyAnalysis(), config)

    # Latency lot R2 (2026-07): start the response-context prefetch (memory,
    # RAG, journal, portrait, psyche) at the earliest point of the turn so it
    # overlaps the router's own LLM cascade. The QI-dependent system-RAG
    # injection is deferred (query_intelligence does not exist yet) — the
    # response node resolves it inline with the fresh intelligence. Keyed on
    # the METADATA run_id: the same source initiative_node and response_node
    # use, so the registry pop matches. When this flag is off, the
    # initiative-node start (idempotent) keeps the historical behaviour.
    if settings.response_context_prefetch_at_router_enabled:
        from src.domains.agents.services.response_context import (
            start_response_context_prefetch,
        )

        _prefetch_run_id = run_id_of(config, "unknown")
        start_response_context_prefetch(state, config, _prefetch_run_id, include_system_rag=False)

    # Semantic pivot: translate query to English for optimal domain detection.
    # Domain descriptions are in English (e.g., "Events, meetings, schedules,
    # appointments") — without translation the LLM may fail to connect
    # "rdv" → "appointments" → event domain. Redis-cached (TTL 5min).
    # Latency lot R1 (2026-07): launched as a concurrent task and awaited by
    # analyze_full AFTER its memory-resolution phase (data-independent: memory
    # embeds the ORIGINAL query). translate_to_english never raises — it falls
    # back to the original query internally (result logged there as
    # `semantic_pivot_translation`).
    # Latency lot R3 (2026-07, ships dark): semantic_pivot_enabled=False skips
    # the pivot call entirely — the analyzer receives the original query and
    # its own english_query output feeds the downstream English matching.
    english_query_task: asyncio.Task[str] | None = None
    if settings.semantic_pivot_enabled:
        from src.domains.agents.services.semantic_pivot_service import (
            translate_to_english,
        )

        english_query_task = asyncio.create_task(
            translate_to_english(query, base_config=config),
            name=f"semantic_pivot_{run_id}",
        )

    # Get QueryAnalyzerService and analyze with full intelligence
    # Memory facts retrieval is now internalized in analyze_full()
    # The English query (better domain detection against English descriptions)
    # is awaited inside analyze_full; original_query is preserved for the
    # debug panel display (user's actual input in their language).
    # ADR-390: an « auto » turn's shape is judged meanwhile; the judgement is read
    # when the engine is settled, or cancelled and awaited — never left running.
    shape_judgement = _start_shape_judgement(query)
    analyzer_service = get_query_analyzer_service()
    try:
        intelligence = await analyzer_service.analyze_full(
            query=query,
            messages=messages,
            state=state,
            config=config,
            original_query=query,  # Preserve user's original query for debug panel
            english_query_task=english_query_task,
        )
        execution_mode = await _settle_turn_engine(intelligence, shape_judgement)
    finally:
        await _abandon_shape_judgement(shape_judgement)

    from dataclasses import replace

    intelligence = replace(
        intelligence,
        efficacy_context=attach_efficacy_analysis(efficacy_start, intelligence.efficacy_analysis),
    )

    # Log reasoning trace
    logger.info(
        "query_intelligence_result",
        run_id=run_id,
        intent=intelligence.immediate_intent,
        confidence=intelligence.immediate_confidence,
        user_goal=intelligence.user_goal.value,
        domains=intelligence.domains,
        turn_type=intelligence.turn_type,
        route_to=intelligence.route_to,
        reasoning_steps=len(intelligence.reasoning_trace or []),
    )

    # === STEP: Semantic tool scoring — the planner's domain scores and the
    # global relevance order the ReAct loop binds by (ADR-293), from ONE embedding.
    tool_scores_dict = await score_tools_for_turn(intelligence, run_id)

    # Build RouterOutput
    router_output = RouterOutput(
        intention=(
            INTENTION_ACTION if intelligence.route_to == "planner" else INTENTION_CONVERSATION
        ),
        confidence=intelligence.confidence,
        context_label=intelligence.primary_domain,
        next_node=intelligence.route_to,
        domains=intelligence.domains,
        reasoning="; ".join(intelligence.reasoning_trace[:3]),
    )

    # Update metrics
    agent_node_executions_total.labels(node_name="router_v3", status="success").inc()
    router_decisions_total.labels(
        intention=router_output.intention,
        confidence_bucket=get_confidence_bucket(intelligence.confidence),
    ).inc()

    # Router-specific metrics (dashboard 07 panels). Wrapped defensively:
    # the router is on the hot path for every chat turn, so metric failures
    # must never propagate.
    with suppress(Exception):
        router_latency_seconds.observe(_time.perf_counter() - _router_start)
        router_confidence_score.labels(intention=router_output.intention).observe(
            float(intelligence.confidence)
        )
        # Fallback tracking: low-bucket confidence or explicit fallback flag.
        # Reuses the shared bucketizer so the threshold stays in lockstep with
        # `router_decisions_total{confidence_bucket}`.
        if get_confidence_bucket(intelligence.confidence) == "low" or getattr(
            intelligence, "fallback_triggered", False
        ):
            router_fallback_total.labels(original_intention=router_output.intention).inc()
        # Data-presumption: pattern detection in QueryAnalyzerService
        patterns = getattr(intelligence, "data_presumption_patterns", None)
        if patterns:
            for pattern in patterns:
                router_data_presumption_total.labels(
                    pattern_detected=pattern, decision=router_output.intention
                ).inc()

    # === ADR-117 Lot 3: repair cancellation aftermath at TURN START ===
    # A cancelled/killed run can leave an AIMessage with UNANSWERED
    # tool_calls in the checkpoint (POC-3): it poisons strict providers on
    # the next turn. At router time every prior message belongs to a
    # finished turn, so repairing here is safe — unlike the messages
    # reducer, where dangling tool_calls are a legitimate mid-run state.
    # (HITL resumptions resume the interrupted node via Command(resume) and
    # never re-enter the router, so pending approvals are unaffected.)
    from src.domains.agents.utils.message_filters import sanitize_stale_dangling_tool_calls

    _dangling_ops = sanitize_stale_dangling_tool_calls(state.get("messages", []))

    # Build state update.
    # turn_type is normalized to the lowercase canonical form so state
    # consumers (response_node, task_orchestrator, …) can compare against
    # TURN_TYPE_* constants without worrying about the UPPERCASE legacy form
    # emitted by QueryIntelligence.
    state_update = {
        STATE_KEY_ROUTING_HISTORY: state.get(STATE_KEY_ROUTING_HISTORY, []) + [router_output],
        STATE_KEY_TURN_TYPE: normalize_turn_type(intelligence.turn_type),
        STATE_KEY_DETECTED_INTENT: intelligence.immediate_intent,
        # Clear per-turn state
        STATE_KEY_PLAN_APPROVED: None,
        STATE_KEY_PLAN_REJECTION_REASON: None,
        STATE_KEY_VALIDATION_RESULT: None,
        STATE_KEY_SEMANTIC_VALIDATION: None,  # Clear so pattern learning works per-turn
        STATE_KEY_PLANNER_ITERATION: 0,
        # A clarification belongs to the turn that asked it: left in the
        # checkpoint, the next turn's planner read it as a REPLAN of the
        # previous plan carrying a stale answer. A HITL resume re-enters
        # the clarification node, never this one, so the answer still
        # reaches the planner of its own turn.
        STATE_KEY_CLARIFICATION_RESPONSE: None,
        STATE_KEY_CLARIFICATION_FIELD: None,
        STATE_KEY_NEEDS_REPLAN: False,
        # A plan, its step results and the planner's verdict belong to
        # the turn that made them: kept in the checkpoint, every later
        # turn restated the plan's failures as its own (the honesty
        # directive), learned from a plan it never ran (pattern
        # learning) and was judged on a verdict it never had.
        STATE_KEY_EXECUTION_PLAN: None,
        STATE_KEY_COMPLETED_STEPS: {},
        STATE_KEY_PLANNING_RESULT: None,
        # Initiative phase reset (ADR-062): must reset per-turn to avoid
        # max_iterations skip on subsequent turns (checkpoint persists state)
        STATE_KEY_INITIATIVE_ITERATION: 0,
        STATE_KEY_INITIATIVE_RESULTS: [],
        STATE_KEY_INITIATIVE_SKIPPED_REASON: None,
        STATE_KEY_INITIATIVE_SUGGESTION: None,
        STATE_KEY_INITIATIVE_FOLLOWUPS: None,
        # STREAMING FIX 2026-01: Clear persisted content_final_replacement from previous turn
        # Root cause: PostgreSQL checkpointer persists this value between turns.
        # If previous turn had HTML injection (truthy value), streaming service
        # skips tokens in _process_messages_chunk (line 780-781) before response_node
        # has a chance to update the value. Clearing at turn start prevents this.
        "content_final_replacement": None,
        # ADR-070: Clear ReAct state from previous turn.
        # Without this, a conversation turn following a ReAct turn would hit the
        # react_bypass in response_node and replay the previous ReAct response.
        "react_agent_result": None,
        "react_tool_names": [],
        "react_hitl_map": {},
        "react_start_time": None,
        # Same reason as the keys above: the previous turn's value must not leak
        # into this one. Blocks are rebuilt by react_setup.
        "react_system_blocks": [],
        # The loop's ACCUMULATORS (iterations, reasoning seconds, tool seconds,
        # productive iterations, call digests) restart from ONE declaration that
        # lives next to the predicate reading them. This list used to name them
        # one by one and missed two added later — measured 2026-09-11, 913.8 s of
        # tool time carried by the checkpoint, every ReAct turn of the thread
        # dead at iteration 1 (react_budget.react_turn_reset).
        **react_turn_reset(),
        # ADR-288: a new turn starts with no draft under review — the previous
        # review was abandoned with its interrupt (draft_sequence.draft_turn_reset).
        **draft_turn_reset(),
        # Store intelligence for planner (as serializable dict for LangGraph checkpointing)
        # Also store the object for in-memory access by streaming service
        STATE_KEY_QUERY_INTELLIGENCE: intelligence.to_serializable_dict(),
        # Keep the object reference for nodes that need methods (to_debug_metrics, etc.)
        "_query_intelligence_obj": intelligence,
        # Store tool selection result for debug panel (semantic similarity of domain tools)
        "tool_selection_result": tool_scores_dict,
        # ADR-070: the engine that plans the turn, for the routing edge (and, on
        # the context's holder, for every other reader); the request for a turn
        # no engine plans.
        "execution_mode": execution_mode,
        # ADR-311: what the ReAct loop shapes its prompt for, fixed for the turn.
        "exchange_rhythm": _resolve_exchange_rhythm(),
    }

    # Resolved context for response_node registry filtering.
    # ALWAYS write to state (even None) to clear stale context from previous turns.
    # Without this, a previous turn's resolved_context persists in state and causes
    # the response_node to inject old registry items (e.g., email cards after a photo query).
    if intelligence.resolved_context:
        state_update[STATE_KEY_RESOLVED_CONTEXT] = intelligence.resolved_context.to_dict()
    else:
        state_update[STATE_KEY_RESOLVED_CONTEXT] = None

    # ADR-117 Lot 3: apply the dangling-tool_calls repair operations through
    # the messages reducer (same-id replacement / RemoveMessage).
    if _dangling_ops:
        state_update["messages"] = _dangling_ops
        logger.warning(
            "router_sanitized_stale_dangling_tool_calls",
            run_id=run_id,
            operations=len(_dangling_ops),
        )

    logger.info(
        "router_v3_complete",
        run_id=run_id,
        next_node=router_output.next_node,
        domains=intelligence.domains,
        turn_type=intelligence.turn_type,
        tool_selection_result_present=tool_scores_dict is not None,
        tool_selection_tools_count=(
            len(tool_scores_dict.get("all_scores", {})) if tool_scores_dict else 0
        ),
    )

    # LangGraph state observability (F006): emit per-key update counters and the
    # merged state size for the router node, matching response_node /
    # task_orchestrator_node. Single CC-neutral call — no new branches.
    track_state_updates(state, state_update, "router_v3", run_id)

    return state_update


def get_router_v3_edge(
    state: MessagesState,
) -> str:
    """
    Edge function for router v3.

    Determines the next node based on RouterOutput in routing_history.
    """
    routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])
    if not routing_history:
        return "response"

    last_output = routing_history[-1]
    if hasattr(last_output, "next_node") and last_output.next_node:
        return last_output.next_node

    return "response"


# Alias for backward compatibility
router_node = router_node_v3
