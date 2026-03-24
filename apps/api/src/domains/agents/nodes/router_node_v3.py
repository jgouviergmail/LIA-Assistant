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

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_RUN_ID
from src.domains.agents.constants import (
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
from src.infrastructure.observability.decorators import track_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_node_executions_total,
    get_confidence_bucket,
    router_decisions_total,
)
from src.infrastructure.observability.tracing import trace_node

logger = get_logger(__name__)


# New state keys for v3
STATE_KEY_QUERY_INTELLIGENCE = "query_intelligence"


@trace_node("router_v3")
@track_metrics(node_name="router_v3")
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
    from src.domains.agents.services.query_analyzer_service import (
        get_query_analyzer_service,
    )

    messages = state[STATE_KEY_MESSAGES]

    # Extract run_id for logging
    configurable = config.get("configurable", {})
    run_id = configurable.get(FIELD_RUN_ID, "unknown")

    # Get last user message
    last_message = messages[-1] if messages else None
    query = ""
    if last_message and hasattr(last_message, "content"):
        query = (
            last_message.content
            if isinstance(last_message.content, str)
            else str(last_message.content)
        )

    logger.info(
        "router_v3_start",
        run_id=run_id,
        query_preview=query[:50] if query else "",
    )

    # Semantic pivot: translate query to English for optimal domain detection
    # Domain descriptions are in English (e.g., "Events, meetings, schedules, appointments")
    # Without translation, LLM may fail to connect "rdv" → "appointments" → event domain
    # SemanticPivotService is cached in Redis (TTL 5min) for performance
    from src.domains.agents.services.semantic_pivot_service import translate_to_english

    english_query_for_analysis = await translate_to_english(query, base_config=config)

    logger.info(
        "router_v3_semantic_pivot",
        run_id=run_id,
        original_query=query[:50] if query else "",
        english_query=english_query_for_analysis[:50] if english_query_for_analysis else "",
    )

    # Get QueryAnalyzerService and analyze with full intelligence
    # Memory facts retrieval is now internalized in analyze_full()
    # Pass English query for better domain detection against English descriptions
    # Also pass original_query for debug panel display (user's actual input in their language)
    analyzer_service = get_query_analyzer_service()
    intelligence = await analyzer_service.analyze_full(
        query=english_query_for_analysis,
        messages=messages,
        state=state,
        config=config,
        original_query=query,  # Preserve user's original query for debug panel
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
        intention="action" if intelligence.route_to == "planner" else "conversation",
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

    # Build state update
    state_update = {
        STATE_KEY_ROUTING_HISTORY: state.get(STATE_KEY_ROUTING_HISTORY, []) + [router_output],
        STATE_KEY_TURN_TYPE: intelligence.turn_type,
        STATE_KEY_DETECTED_INTENT: intelligence.immediate_intent,
        # Clear per-turn state
        STATE_KEY_PLAN_APPROVED: None,
        STATE_KEY_PLAN_REJECTION_REASON: None,
        STATE_KEY_VALIDATION_RESULT: None,
        STATE_KEY_SEMANTIC_VALIDATION: None,  # Clear so pattern learning works per-turn
        STATE_KEY_PLANNER_ITERATION: 0,
        # STREAMING FIX 2026-01: Clear persisted content_final_replacement from previous turn
        # Root cause: PostgreSQL checkpointer persists this value between turns.
        # If previous turn had HTML injection (truthy value), streaming service
        # skips tokens in _process_messages_chunk (line 780-781) before response_node
        # has a chance to update the value. Clearing at turn start prevents this.
        "content_final_replacement": None,
        # Store intelligence for planner (as serializable dict for LangGraph checkpointing)
        # Also store the object for in-memory access by streaming service
        STATE_KEY_QUERY_INTELLIGENCE: intelligence.to_serializable_dict(),
        # Keep the object reference for nodes that need methods (to_debug_metrics, etc.)
        "_query_intelligence_obj": intelligence,
        # Store tool selection result for debug panel (semantic similarity of domain tools)
        "tool_selection_result": tool_scores_dict,
    }

    # Add resolved context if available
    # Convert to dict for state compatibility (response_node expects dict)
    # smart_planner_service uses intelligence.resolved_context (object) for to_llm_context()
    if intelligence.resolved_context:
        state_update[STATE_KEY_RESOLVED_CONTEXT] = intelligence.resolved_context.to_dict()

    # Add resolved references if available
    if intelligence.resolved_references:
        state_update[STATE_KEY_RESOLVED_REFERENCES] = intelligence.resolved_references

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
