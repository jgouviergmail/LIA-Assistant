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
    STATE_KEY_INITIATIVE_FOLLOWUPS,
    STATE_KEY_INITIATIVE_ITERATION,
    STATE_KEY_INITIATIVE_RESULTS,
    STATE_KEY_INITIATIVE_SKIPPED_REASON,
    STATE_KEY_INITIATIVE_SUGGESTION,
)
from src.core.field_names import FIELD_RUN_ID
from src.domains.agents.constants import (
    INTENTION_ACTION,
    INTENTION_CONVERSATION,
    STATE_KEY_DETECTED_INTENT,
    STATE_KEY_MESSAGES,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_PLANNER_ITERATION,
    STATE_KEY_RESOLVED_CONTEXT,
    STATE_KEY_RESOLVED_REFERENCES,
    STATE_KEY_ROUTING_HISTORY,
    STATE_KEY_SEMANTIC_VALIDATION,
    STATE_KEY_TURN_TYPE,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.models import MessagesState
from src.domains.agents.utils.state_tracking import track_state_updates
from src.domains.agents.utils.turn_type import normalize_turn_type
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
from src.infrastructure.observability.tracing import trace_node

logger = get_logger(__name__)


# New state keys for v3
STATE_KEY_QUERY_INTELLIGENCE = "query_intelligence"


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

    _router_start = _time.perf_counter()
    messages = state[STATE_KEY_MESSAGES]

    # Extract run_id for logging
    configurable = config.get("configurable", {})
    run_id = configurable.get(FIELD_RUN_ID, "unknown")

    # Get last user message
    last_message = messages[-1] if messages else None
    query = ""
    if last_message and hasattr(last_message, "content"):
        query = coerce_content_to_text(last_message.content)

    logger.info(
        "router_v3_start",
        run_id=run_id,
        query_preview=query[:50] if query else "",
    )

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

        _prefetch_run_id = (config.get("metadata") or {}).get(FIELD_RUN_ID, "unknown")
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
    analyzer_service = get_query_analyzer_service()
    intelligence = await analyzer_service.analyze_full(
        query=query,
        messages=messages,
        state=state,
        config=config,
        original_query=query,  # Preserve user's original query for debug panel
        english_query_task=english_query_task,
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
        reasoning=intelligence.reasoning_trace[:3] if intelligence.reasoning_trace else [],
    )

    # === STEP: Semantic Tool Scoring for Debug Panel ===
    # Calculate semantic similarity scores for ALL tools in detected domains
    # This provides the "all_scores" view (like domain_selection.all_scores_calibrated)
    # The actual tool selection (filtered by intent) is done in the planner
    tool_scores_dict = None
    if intelligence.route_to == "planner" and intelligence.domains:
        try:
            from src.domains.agents.services.tool_selector import get_tool_selector

            selector = await get_tool_selector()
            if selector.is_initialized():
                # Get tools from detected domains (pre-filtered by request context)
                from src.core.context import get_request_tool_manifests, user_mcp_tools_ctx
                from src.domains.agents.registry.domain_taxonomy import is_mcp_domain

                all_manifests = get_request_tool_manifests()
                domain_tool_manifests = [
                    m
                    for m in all_manifests
                    if (m.agent.removesuffix("_agent") if hasattr(m, "agent") else "")
                    in intelligence.domains
                ]

                # User MCP embeddings needed for semantic scoring
                extra_emb = None
                user_ctx = user_mcp_tools_ctx.get()
                if user_ctx and user_ctx.tool_embeddings:
                    has_mcp = any(is_mcp_domain(d) for d in intelligence.domains)
                    if has_mcp:
                        extra_emb = user_ctx.tool_embeddings

                # Calculate scores for domain tools
                if domain_tool_manifests:
                    result = await selector.select_tools(
                        query=intelligence.english_query,
                        available_tools=domain_tool_manifests,
                        extra_embeddings=extra_emb,
                    )
                    tool_scores_dict = {
                        "all_scores": result.all_scores,  # For debug panel (all calibrated scores)
                        "selected_tools": [  # Only tools that passed the > threshold filter
                            {
                                "tool_name": t.tool_name,
                                "score": round(t.score, 3),
                                "confidence": t.confidence,
                            }
                            for t in result.selected_tools
                        ],
                        "top_score": result.top_score,
                        "has_uncertainty": result.has_uncertainty,
                    }
                    logger.info(
                        "router_v3_tool_scores_computed",
                        run_id=run_id,
                        domains=intelligence.domains,
                        tools_scored=len(domain_tool_manifests),
                        top_score=round(result.top_score, 3),
                    )
        except Exception as e:
            logger.warning("router_v3_tool_scoring_failed", run_id=run_id, error=str(e))

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
        "react_iteration": 0,
        "react_start_time": None,
        # Same reason as the keys above: the previous turn's value must not leak
        # into this one. Blocks are rebuilt by react_setup, the compute budget
        # restarts at zero, and the loop guard forgets what the last turn called.
        "react_system_blocks": [],
        "react_elapsed_seconds": 0.0,
        "react_call_digests": {},
        # Store intelligence for planner (as serializable dict for LangGraph checkpointing)
        # Also store the object for in-memory access by streaming service
        STATE_KEY_QUERY_INTELLIGENCE: intelligence.to_serializable_dict(),
        # Keep the object reference for nodes that need methods (to_debug_metrics, etc.)
        "_query_intelligence_obj": intelligence,
        # Store tool selection result for debug panel (semantic similarity of domain tools)
        "tool_selection_result": tool_scores_dict,
        # ADR-070: Inject execution_mode from configurable into state for routing
        "execution_mode": configurable.get("user_execution_mode", "pipeline"),
    }

    # Resolved context for response_node registry filtering.
    # ALWAYS write to state (even None) to clear stale context from previous turns.
    # Without this, a previous turn's resolved_context persists in state and causes
    # the response_node to inject old registry items (e.g., email cards after a photo query).
    if intelligence.resolved_context:
        state_update[STATE_KEY_RESOLVED_CONTEXT] = intelligence.resolved_context.to_dict()
    else:
        state_update[STATE_KEY_RESOLVED_CONTEXT] = None

    # Add resolved references if available
    if intelligence.resolved_references:
        state_update[STATE_KEY_RESOLVED_REFERENCES] = intelligence.resolved_references

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
