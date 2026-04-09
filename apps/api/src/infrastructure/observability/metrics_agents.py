"""
Prometheus metrics for LangGraph agents and SSE streaming.

Implements comprehensive RED metrics (Rate, Errors, Duration) for:
- SSE streaming performance
- Router decision quality
- LLM token usage and costs
- Agent execution health

Reference: OpenTelemetry Semantic Conventions for LLM Observability
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram

from src.core.field_names import FIELD_AGENT_NAME, FIELD_NODE_NAME, FIELD_TOOL_NAME

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ============================================================================
# PRICING CACHE (delegated to infrastructure/cache/pricing_cache.py)
# ============================================================================
# Re-export functions for backwards compatibility with existing imports.
# Implementation moved to dedicated service for proper separation of concerns.

from src.infrastructure.cache.pricing_cache import (  # noqa: E402, F401
    get_cached_cost as estimate_cost_from_cache,
)

# ============================================================================
# SSE STREAMING PERFORMANCE METRICS
# ============================================================================

sse_streaming_duration_seconds = Histogram(
    "sse_streaming_duration_seconds",
    "Total SSE streaming duration (request to last token)",
    ["intention"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 30.0],
)

sse_time_to_first_token_seconds = Histogram(
    "sse_time_to_first_token_seconds",
    "Time to first token (TTFT) in SSE streaming",
    ["intention"],
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)

sse_tokens_generated_total = Counter(
    "sse_tokens_generated_total",
    "Total tokens generated in SSE streaming",
    ["intention", FIELD_NODE_NAME],
)

sse_streaming_errors_total = Counter(
    "sse_streaming_errors_total",
    "Total SSE streaming errors",
    ["error_type", FIELD_NODE_NAME],
)

# ============================================================================
# ROUTER METRICS
# ============================================================================

router_latency_seconds = Histogram(
    "router_latency_seconds",
    "Router decision latency (time to route)",
    buckets=[0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0],
)

router_decisions_total = Counter(
    "router_decisions_total",
    "Total router decisions",
    ["intention", "confidence_bucket"],  # confidence_bucket: low/medium/high
)

router_fallback_total = Counter(
    "router_fallback_total",
    "Total router fallbacks (low confidence)",
    ["original_intention"],
)

router_data_presumption_total = Counter(
    "router_data_presumption_total",
    "Router decisions based on data availability instead of syntax (RULE #5 violation)",
    [
        "pattern_detected",
        "decision",
    ],  # pattern: "aucun_resultat", "pas_trouve", etc. / decision: conversation, actionable
)

# NOTE: router_confidence_tier_counter removed (redundant with router_decisions_total)
# Use router_decisions_total with confidence_bucket label instead for better consistency

# ============================================================================
# LLM TOKEN USAGE & COST METRICS
# ============================================================================

llm_tokens_consumed_total = Counter(
    "llm_tokens_consumed_total",
    "Total LLM tokens consumed",
    ["model", FIELD_NODE_NAME, "token_type"],  # token_type: prompt_tokens/completion_tokens
)

llm_api_calls_total = Counter(
    "llm_api_calls_total",
    "Total LLM API calls",
    ["model", FIELD_NODE_NAME, "status"],  # status: success/error
)

llm_api_latency_seconds = Histogram(
    "llm_api_latency_seconds",
    "LLM API call latency (optimized for OpenAI GPT-4/gpt-4.1-mini patterns)",
    ["model", FIELD_NODE_NAME],
    # Optimized buckets for OpenAI API patterns (rarely < 500ms, often > 10s for large contexts)
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

llm_cost_total = Counter(
    "llm_cost_total",
    "Cumulative LLM cost in configured currency (USD or EUR)",
    ["model", FIELD_NODE_NAME, "currency"],
)

# ============================================================================
# AGENT NODE METRICS
# ============================================================================

agent_node_executions_total = Counter(
    "agent_node_executions_total",
    "Total agent node executions",
    [FIELD_NODE_NAME, "status"],  # status: success/error
)

agent_node_duration_seconds = Histogram(
    "agent_node_duration_seconds",
    "Agent node execution duration",
    [FIELD_NODE_NAME],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# ============================================================================
# CONTEXT & STATE METRICS
# ============================================================================

agent_context_tokens_gauge = Gauge(
    "agent_context_tokens_gauge",
    "Current context size in tokens",
    [FIELD_NODE_NAME],
)

agent_messages_history_count = Histogram(
    "agent_messages_history_count",
    "Number of messages in conversation history",
    buckets=[1, 3, 5, 10, 20, 50, 100],
)

# ============================================================================
# TASK ORCHESTRATOR METRICS
# ============================================================================

task_orchestrator_plans_created = Counter(
    "task_orchestrator_plans_created_total",
    "Total orchestration plans created",
    ["intention", "agents_count"],
)

# ============================================================================
# CONTACTS API METRICS (provider-agnostic: Google, Apple, future Microsoft)
# ============================================================================

contacts_api_calls = Counter(
    "contacts_api_calls_total",
    "Total Contacts API calls (all providers)",
    [
        "operation",
        "status",
    ],  # operation: search/list/details, status: success/error
    # Note: Removed connector_id_hash label to prevent high cardinality
    # (one series per user would create thousands of time series)
    # Use logs for per-user debugging instead
)

contacts_api_latency = Histogram(
    "contacts_api_latency_seconds",
    "Contacts API call latency (all providers)",
    ["operation"],  # operation: search/list/details
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

contacts_cache_hits = Counter(
    "contacts_cache_hits_total",
    "Contacts cache hits (all providers)",
    ["cache_type"],  # cache_type: contacts/email/calendar/list/search/details
)

contacts_cache_misses = Counter(
    "contacts_cache_misses_total",
    "Contacts cache misses (all providers)",
    ["cache_type"],
)

# Backward-compatible aliases (used in existing imports)
google_contacts_api_calls = contacts_api_calls
google_contacts_api_latency = contacts_api_latency
google_contacts_cache_hits = contacts_cache_hits
google_contacts_cache_misses = contacts_cache_misses

# NOTE: Database metrics are in metrics_database.py, not here
# See: src/infrastructure/observability/metrics_database.py for:
# - db_connection_pool_size, db_connection_pool_overflow, db_connection_pool_checkedout
# - db_query_duration_seconds, db_query_total (if needed)

# ============================================================================
# AGENT TOOL METRICS (LangChain Tools)
# ============================================================================

agent_tool_invocations = Counter(
    "agent_tool_invocations_total",
    "Total agent tool invocations",
    [FIELD_TOOL_NAME, FIELD_AGENT_NAME, "success"],  # success: true/false
)

agent_tool_duration_seconds = Histogram(
    "agent_tool_duration_seconds",
    "Agent tool execution duration",
    [FIELD_TOOL_NAME, FIELD_AGENT_NAME],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

agent_tool_rate_limit_hits = Counter(
    "agent_tool_rate_limit_hits_total",
    "Total agent tool rate limit hits (requests blocked)",
    [FIELD_TOOL_NAME, "user_id_hash", "scope"],  # scope: user/global
)

# ============================================================================
# TASK ORCHESTRATOR ADVANCED METRICS
# ============================================================================

orchestration_plan_agents_distribution = Histogram(
    "orchestration_plan_agents_count",
    "Distribution of agents count per orchestration plan",
    buckets=[1, 2, 3, 4, 5, 10],
)

# ============================================================================
# CONTACTS RESULTS METRICS (provider-agnostic)
# ============================================================================

contacts_results_count = Histogram(
    "contacts_results_count",
    "Number of contacts returned per query (all providers)",
    ["operation"],  # operation: search/list/details
    buckets=[0, 1, 5, 10, 20, 50, 100, 500],
)

# Backward-compatible alias
google_contacts_results_count = contacts_results_count

# ============================================================================
# EMAIL API METRICS (provider-agnostic: Gmail, Apple Mail, future Microsoft)
# ============================================================================

email_api_calls = Counter(
    "email_api_calls_total",
    "Total Email API calls (all providers)",
    [
        "operation",
        "status",
    ],  # operation: search/get_details/send, status: success/error
    # Note: Removed connector_id_hash label to prevent high cardinality
    # (one series per user would create thousands of time series)
    # Use logs for per-user debugging instead
)

email_api_latency = Histogram(
    "email_api_latency_seconds",
    "Email API call latency (all providers)",
    ["operation"],  # operation: search/get_details/send
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

email_cache_hits = Counter(
    "email_cache_hits_total",
    "Email cache hits (all providers)",
    ["cache_type"],  # cache_type: search/details/list
)

email_cache_misses = Counter(
    "email_cache_misses_total",
    "Email cache misses (all providers)",
    ["cache_type"],
)

email_results_count = Histogram(
    "email_results_count",
    "Number of emails returned per query (all providers)",
    ["operation"],  # operation: search/list
    buckets=[0, 1, 5, 10, 20, 50, 100, 500],
)

# Backward-compatible aliases (used in existing imports)
gmail_api_calls = email_api_calls
gmail_api_latency = email_api_latency
gmail_cache_hits = email_cache_hits
gmail_cache_misses = email_cache_misses
gmail_results_count = email_results_count

# ============================================================================
# BUSINESS METRICS - FEATURE ADOPTION
# ============================================================================

contacts_queries_by_type = Counter(
    "contacts_queries_by_type_total",
    "Contacts queries by search type",
    ["query_type"],  # query_type: name_search, email_search, phone_search, list_all
)

# ============================================================================
# END-TO-END PERFORMANCE METRICS
# ============================================================================
# TODO: Implement e2e_request_duration_with_agents instrumentation in chat router

e2e_request_duration_with_agents = Histogram(
    "e2e_request_duration_seconds",
    "End-to-end request duration (router → agents → response) with agents complexity tracking",
    ["intention", "agents_bucket"],  # agents_bucket: single, few_2-3, many_4+
    # Optimized for multi-agent orchestration latency patterns
    buckets=[0.5, 1, 2, 5, 10, 20, 30, 60, 120],
)

# ============================================================================
# AGENT QUALITY METRICS
# ============================================================================
# Note: Agent success rate is a DERIVED METRIC calculated in PromQL, not instrumented in code.
#
# PromQL Query (for Grafana dashboards):
# ```promql
# # Agent success rate (1h rolling window)
# sum by (agent_name) (rate(agent_node_executions_total{status="success"}[1h]))
# /
# sum by (agent_name) (rate(agent_node_executions_total[1h]))
# ```
#
# Rationale:
# - Gauges for derived metrics create confusion and maintenance burden
# - PromQL is the correct place for rate calculations and rolling windows
# - Existing agent_node_executions_total counter already provides raw data
# - See docs/monitoring/metrics.md for dashboard configuration

# ============================================================================
# CONVERSATION & CHECKPOINT METRICS
# ============================================================================

checkpoint_load_duration_seconds = Histogram(
    "checkpoint_load_duration_seconds",
    "Time to load checkpoint from PostgreSQL",
    [FIELD_NODE_NAME],  # Generic "checkpoint_load" or specific node if available
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

checkpoint_save_duration_seconds = Histogram(
    "checkpoint_save_duration_seconds",
    "Time to save checkpoint to PostgreSQL",
    [FIELD_NODE_NAME],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

checkpoint_size_bytes = Histogram(
    "checkpoint_size_bytes",
    "Size of checkpoint payload in bytes (extended for long conversations)",
    [FIELD_NODE_NAME],
    # Extended buckets to handle conversations exceeding 100KB
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000],
)

# Phase 3.3 - Checkpoint Operations & Error Tracking
checkpoint_operations_total = Counter(
    "checkpoint_operations_total",
    "Total checkpoint operations by type and outcome",
    ["operation", "status"],  # operation: save/load/list, status: success/error
)

checkpoint_errors_total = Counter(
    "checkpoint_errors_total",
    "Total checkpoint errors by error type",
    [
        "error_type",
        "operation",
    ],  # error_type: db_connection/serialization/timeout, operation: save/load/list
)

conversation_resets_total = Counter(
    "conversation_resets_total",
    "Total conversation resets by users",
    # Note: user_id_hash label removed to prevent high cardinality
    # Use Prometheus recording rules for per-user aggregations if needed
)

conversation_created_total = Counter(
    "conversation_created_total",
    "Total conversations created (lazy creation)",
)

conversation_reactivated_total = Counter(
    "conversation_reactivated_total",
    "Total soft-deleted conversations reactivated",
)

conversation_message_archived_total = Counter(
    "conversation_message_archived_total",
    "Total messages archived to conversation_messages table",
    ["role"],  # user, assistant, system
)

# ============================================================================
# CONVERSATION REPOSITORY MIGRATION METRICS (Phase 3 Refactoring)
# ============================================================================

conversation_repository_queries_total = Counter(
    "conversation_repository_queries_total",
    "Query count by implementation version (legacy vs optimized)",
    ["version"],  # "legacy" or "v2"
)

conversation_messages_query_duration_seconds = Histogram(
    "conversation_messages_query_duration_seconds",
    "Query duration for message retrieval with token summaries",
    ["version"],  # "legacy" or "v2"
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

conversation_repository_errors_total = Counter(
    "conversation_repository_errors_total",
    "Errors in repository layer by version",
    ["version", "error_type"],
)

# ============================================================================
# MULTI-DOMAIN COMPOSITION METRICS
# ============================================================================

domain_handlers_registered_total = Counter(
    "domain_handlers_registered_total",
    "Total domain handlers registered",
    ["domain"],  # domain: contacts, emails, calendar, etc.
)

multi_domain_composition_total = Counter(
    "multi_domain_composition_total",
    "Total multi-domain composition operations",
    ["composition_mode", "domain_count"],  # composition_mode: mono/multi/hierarchical
)

multi_domain_formatting_duration_seconds = Histogram(
    "multi_domain_formatting_duration_seconds",
    "Duration of multi-domain formatting for LLM context",
    ["domain_count"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

domain_detection_total = Counter(
    "domain_detection_total",
    "Domain detection results",
    ["domain", "detected"],  # detected: true/false
)

domain_normalization_errors_total = Counter(
    "domain_normalization_errors_total",
    "Errors during domain normalization",
    ["domain", "error_type"],
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_confidence_bucket(confidence: float) -> str:
    """
    Categorize confidence score into buckets.

    Args:
        confidence: Confidence score (0.0 to 1.0)

    Returns:
        Bucket label: "low", "medium", or "high"
    """
    if confidence < 0.6:
        return "low"
    elif confidence < 0.8:
        return "medium"
    else:
        return "high"


# Removed: normalize_model_name() - now imported from src.core.llm_utils (see top of file)


async def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
    db: AsyncSession | None = None,
) -> float:
    """
    Estimate LLM API cost in configured currency (EUR by default).

    DEPRECATED: This function name is misleading - it returns EUR if settings.default_currency == "EUR".
    Use AsyncPricingService.calculate_token_cost() directly for new code.

    Pricing is retrieved from llm_model_pricing table via AsyncPricingService.
    Returns 0.0 if pricing not found.

    Args:
        model: LLM model name (e.g., "gpt-4.1-mini", "o1-mini")
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cached_tokens: Number of cached input tokens (optional, default 0)
        db: Optional AsyncSession for dependency injection (for testing)

    Returns:
        Estimated cost in configured currency (0.0 if pricing not found)

    Example:
        >>> cost = await estimate_cost_usd("gpt-4.1-mini", 1000, 500)
        >>> print(f"Cost: {cost:.6f}")
        Cost: 0.005813  # EUR if default_currency = EUR
    """
    try:
        import structlog

        from src.core.config import settings
        from src.domains.llm.pricing_service import AsyncPricingService

        logger = structlog.get_logger(__name__)

        # Use provided session or create new one
        if db is not None:
            # Use injected session (testing path)
            pricing_service = AsyncPricingService(
                db=db,
                cache_ttl_seconds=settings.llm_pricing_cache_ttl_seconds,
            )
            cost_usd, cost_eur = await pricing_service.calculate_token_cost(
                model=model,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )
        else:
            # Production path: create own session
            from src.infrastructure.database import get_db_context

            async with get_db_context() as db_session:
                pricing_service = AsyncPricingService(
                    db=db_session,
                    cache_ttl_seconds=settings.llm_pricing_cache_ttl_seconds,
                )
                cost_usd, cost_eur = await pricing_service.calculate_token_cost(
                    model=model,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    cached_tokens=cached_tokens,
                )

        # Return cost in configured currency (EUR by default)
        return cost_eur if settings.default_currency.upper() == "EUR" else cost_usd

    except Exception as e:
        # Database error or import error, return 0.0
        import structlog

        logger = structlog.get_logger(__name__)
        logger.error(
            "cost_estimation_failed",
            model=model,
            error=str(e),
            fallback_cost=0.0,
        )
        return 0.0


# ============================================================================
# TOOL CONTEXT RESOLUTION METRICS
# ============================================================================
# Context resolution for multi-turn conversations
# Instrumented in: domains/agents/services/context_resolution_service.py:resolve_context()

context_resolution_attempts_total = Counter(
    "context_resolution_attempts_total",
    "Total context resolution attempts by turn type",
    ["turn_type"],  # action/reference/conversational
)

context_resolution_confidence_score = Histogram(
    "context_resolution_confidence_score",
    "Context resolution confidence scores distribution",
    ["turn_type"],  # action/reference/conversational
    buckets=[0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0],
)

context_resolution_turn_type_distribution_total = Counter(
    "context_resolution_turn_type_distribution_total",
    "Distribution of turn types detected in conversations",
    ["turn_type"],  # action/reference/conversational
)


# ============================================================================
# MCP (Model Context Protocol) METRICS — evolution F2
# ============================================================================
# Instrumented in: infrastructure/mcp/tool_adapter.py (MCPToolAdapter._arun)
# Reference: docs/technical/MCP_INTEGRATION.md

mcp_tool_invocations_total = Counter(
    "mcp_tool_invocations_total",
    "Total MCP tool invocations",
    ["server_name", "tool_name", "status"],  # status: success/error
)

mcp_tool_duration_seconds = Histogram(
    "mcp_tool_duration_seconds",
    "MCP tool execution duration",
    ["server_name", "tool_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

mcp_server_health = Gauge(
    "mcp_server_health",
    "MCP server connection status (1=healthy, 0=down)",
    ["server_name"],
)

mcp_connection_errors_total = Counter(
    "mcp_connection_errors_total",
    "MCP server connection errors",
    ["server_name", "error_type"],
)

# ADR-062: MCP ReAct Sub-Agent metrics
mcp_react_invocations_total = Counter(
    "mcp_react_invocations_total",
    "MCP ReAct sub-agent invocations",
    ["server_name", "status"],  # status: success/error
)

mcp_react_iterations_histogram = Histogram(
    "mcp_react_iterations_histogram",
    "Number of ReAct iterations per MCP task",
    ["server_name"],
    buckets=[1, 2, 3, 5, 8, 10, 15],
)

# ADR-062: Initiative Phase metrics
initiative_evaluations_total = Counter(
    "initiative_evaluations_total",
    "Initiative phase evaluations",
    ["decision"],  # "act" | "skip" | "prefilter_skip"
)

initiative_actions_executed_total = Counter(
    "initiative_actions_executed_total",
    "Initiative actions executed",
    ["tool_name"],
)

initiative_duration_seconds = Histogram(
    "initiative_duration_seconds",
    "Initiative phase total duration",
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0],
)

context_resolution_duration_seconds = Histogram(
    "context_resolution_duration_seconds",
    "Time spent resolving context per turn type",
    ["turn_type"],  # action/reference/conversational
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# ============================================================================
# HITL (HUMAN-IN-THE-LOOP) TOOL APPROVAL METRICS
# ============================================================================
# Note: tool_approvals_total removed - legacy button-based HITL replaced by conversational flow

# ============================================================================
# HITL CLASSIFICATION METRICS (Phase 1.2 - Conversational HITL)
# ============================================================================

hitl_classification_method_total = Counter(
    "hitl_classification_method_total",
    "HITL response classification by method (fast-path pattern vs LLM fallback)",
    ["method", "decision"],  # method: fast_path/llm, decision: APPROVE/REJECT/EDIT/AMBIGUOUS
)

hitl_classification_duration_seconds = Histogram(
    "hitl_classification_duration_seconds",
    "HITL classification latency (pattern matching + LLM inference time)",
    ["method"],  # fast_path/llm
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

hitl_classification_confidence = Histogram(
    "hitl_classification_confidence",
    "Confidence score distribution for HITL LLM classifications",
    ["decision"],  # APPROVE/REJECT/EDIT/AMBIGUOUS
    buckets=[0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
)

hitl_clarification_requests_total = Counter(
    "hitl_clarification_requests_total",
    "Total clarification requests sent to users (ambiguous or low confidence responses)",
    ["reason"],  # reason: ambiguous_decision/low_confidence/unclear_edit
)

hitl_classification_demoted_total = Counter(
    "hitl_classification_demoted_total",
    "HITL classifications demoted due to low confidence or validation issues",
    ["from_decision", "to_decision", "reason"],  # e.g., EDIT → AMBIGUOUS (low_confidence)
)

hitl_security_events_total = Counter(
    "hitl_security_events_total",
    "Security events detected in HITL flows (DoS attempts, abuse, rate limits)",
    [
        "event_type",
        "severity",
    ],  # event_type: max_actions_exceeded/rate_limit_exceeded, severity: low/medium/high
)

# ============================================================================
# HITL RESUMPTION METRICS
# ============================================================================

hitl_resumption_total = Counter(
    "hitl_resumption_total",
    "HITL graph resumption attempts after user approval",
    ["strategy", "status"],  # strategy: conversational/button, status: success/error
)

hitl_resumption_duration_seconds = Histogram(
    "hitl_resumption_duration_seconds",
    "HITL graph resumption duration (from approval decision to completion)",
    ["strategy"],  # conversational/button
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
)

# ============================================================================
# HITL USER BEHAVIOR METRICS
# ============================================================================
# NOTE: All 3 metrics below are instrumented in hitl_orchestrator.py:
# - hitl_user_response_time_seconds: _track_response_time_metrics() ligne 261-304
# - hitl_edit_decisions_total: _build_edit_decision() ligne 250-253
# - hitl_tool_rejections_by_reason: _build_reject_decision() ligne 143-147

hitl_user_response_time_seconds = Histogram(
    "hitl_user_response_time_seconds",
    "Time between HITL tool approval request and user response",
    ["decision"],  # approve/reject/edit
    buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600],  # 1s to 1h
)

hitl_edit_decisions_total = Counter(
    "hitl_edit_decisions_total",
    "Total EDIT decisions with parameter modification tracking",
    [FIELD_TOOL_NAME, "param_modified"],  # Track which params are most often corrected by users
)

hitl_tool_rejections_by_reason = Counter(
    "hitl_tool_rejections_by_reason_total",
    "Tool rejections categorized by inferred reason",
    [FIELD_TOOL_NAME, "rejection_type"],  # rejection_type: explicit_no/timeout/error
)

# ============================================================================
# HITL USER BEHAVIOR METRICS (Sprint 1 - Phase 1.2)
# ============================================================================

hitl_clarification_fallback_total = Counter(
    "hitl_clarification_fallback_total",
    "Total HITL classifications that fell back to CLARIFY decision",
    ["reason"],
    # Tracks when classifier cannot make confident decision
    # High rate indicates classifier needs improvement
    # Reason labels: low_confidence, ambiguous_input, llm_error
)

# ============================================================================
# HITL QUESTION GENERATION STREAMING METRICS
# ============================================================================
# Phase: HITL Streaming Question Generation (TTFT Optimization)
# Purpose: Track performance of streaming LLM question generation vs blocking

hitl_question_ttft_seconds = Histogram(
    "hitl_question_ttft_seconds",
    "Time to first token for HITL question generation (user-perceived latency)",
    ["type"],  # label values: plan_approval, tool_confirmation
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
    # Critical UX metric: User perceives latency based on first token
    # Target: P95 < 500ms (vs 2-4s blocking)
)

hitl_question_generation_duration_seconds = Histogram(
    "hitl_question_generation_duration_seconds",
    "Total duration of HITL question generation",
    ["streaming"],  # Label: "true" or "false"
    buckets=(0.1, 0.5, 1.0, 2.0, 4.0, 8.0),
    # Tracks streaming and blocking (for comparison)
    # Total duration similar, but TTFT drastically different
)

hitl_question_tokens_per_second = Histogram(
    "hitl_question_tokens_per_second",
    "Token generation rate for HITL questions",
    ["type"],  # label values: plan_approval, tool_confirmation
    buckets=(10, 25, 50, 100, 200),
    # Detects degradation in LLM provider performance
    # Baseline: ~100 tokens/sec for gpt-4.1-mini-mini
)

# Phase 1 HITL Streaming (OPTIMPLAN) - Fallback metrics
hitl_streaming_fallback_total = Counter(
    "hitl_streaming_fallback_total",
    "Total HITL streaming fallbacks due to errors",
    ["type", "error_type"],
    # label type: plan_approval, tool_confirmation, clarification
    # label error_type: LLMError, TimeoutError, ConnectionError, etc.
    # Tracks streaming failures requiring fallback to word split
    # Target: < 1% fallback rate in production
)

hitl_edit_actions_total = Counter(
    "hitl_edit_actions_total",
    "Total HITL EDIT actions by type and agent",
    ["edit_type", "agent_type"],
    # edit_type: params_modified, tool_changed, full_rewrite, minor_adjustment
    # Tracks how users modify agent proposals
)

hitl_rejection_type_total = Counter(
    "hitl_rejection_type_total",
    "Total HITL rejections by inferred type and agent",
    ["rejection_type", "agent_type"],
    # rejection_type: explicit_no, low_confidence, implicit_no
    # Categorizes why users reject agent proposals
)

# ============================================================================
# DATA REGISTRY + HITL INTEGRATION METRICS (LOT 4)
# ============================================================================
# Phase: Data Registry LOT 4 - HITL Integration
# Purpose: Track HITL interrupts with data registry items for rich rendering

registry_hitl_interrupts_total = Counter(
    "registry_hitl_interrupts_total",
    "Total HITL interrupts with data registry context",
    ["type", "has_registry_items"],
    # label type: plan_approval, tool_confirmation, clarification, draft_critique
    # label has_registry_items: "true" or "false"
    # Tracks how many HITL interrupts include registry items for rich rendering
)

registry_hitl_registry_items_per_interrupt = Histogram(
    "registry_hitl_registry_items_per_interrupt",
    "Number of data registry items included in HITL metadata",
    ["type"],
    buckets=(0, 1, 2, 5, 10, 20, 50),
    # Tracks distribution of registry items per HITL interrupt
    # Helps identify if interrupts have too many/few items
)

# ============================================================================
# HITL QUALITY METRICS
# ============================================================================
# Note: hitl_fast_path_accuracy_total removed - fast-path pattern matching no longer used (LLM-only classification)

# ============================================================================
# PLANNER METRICS (Phase 5 - Multi-Agent Orchestration)
# ============================================================================

planner_plans_created_total = Counter(
    "planner_plans_created_total",
    "Total execution plans created by planner LLM",
    ["execution_mode"],  # execution_mode: sequential/parallel
)

# ============================================================================
# PLANNER TOKEN COUNTING METRICS (Phase A - Reliability Improvement)
# ============================================================================

planner_token_count = Histogram(
    "planner_token_count",
    "Distribution of token counts for planner prompts",
    buckets=[1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 15000, 20000],
)

planner_fallback_triggered_total = Counter(
    "planner_fallback_triggered_total",
    "Total fallback strategy triggers due to token overflow",
    [
        "from_level",
        "to_level",
    ],  # from_level/to_level: full_catalogue/filtered_catalogue/reduced_descriptions/etc
)

planner_plans_rejected_total = Counter(
    "planner_plans_rejected_total",
    "Total execution plans rejected by validator",
    ["reason"],  # reason: validation_failed/budget_exceeded/too_many_steps/cycle_detected
)

planner_errors_total = Counter(
    "planner_errors_total",
    "Total planner errors",
    [
        "error_type"
    ],  # error_type: json_parse_error/pydantic_validation_error/validation_error/unknown_error
)

planner_retries_total = Counter(
    "planner_retries_total",
    "Total planner retry attempts after validation errors",
    [
        "retry_attempt",
        "validation_error_type",
    ],  # retry_attempt: 1/2/3, validation_error_type: invalid_step_reference/missing_tool/etc
)

planner_retry_success_total = Counter(
    "planner_retry_success_total",
    "Total successful planner retries (plan became valid after retry)",
    ["retry_attempt"],  # Which attempt succeeded (1, 2, etc)
)

planner_retry_exhausted_total = Counter(
    "planner_retry_exhausted_total",
    "Total planner retries exhausted without success after max attempts",
    ["final_error_type"],  # The validation error type that persisted after all retries
)

# Note: orchestration_plan_agents_distribution already defined at line 212
# Duplicate removed to prevent metric redefinition bug

# Note: task_orchestrator_plans_created already defined at line 145

# ============================================================================
# DOMAIN FILTERING METRICS (Phase 3 - 2025-11-11)
# ============================================================================
# Metrics for multi-domain dynamic filtering (80-90% token reduction)

planner_domain_filtering_active = Gauge(
    "planner_domain_filtering_active",
    "Domain filtering status flag (1=enabled, 0=disabled)",
)

planner_catalogue_size_tools = Histogram(
    "planner_catalogue_size_tools",
    "Distribution of tool count loaded in planner catalogue",
    [
        "filtering_applied",
        "domains_loaded",
    ],  # filtering_applied: true/false, domains_loaded: contacts/contacts+email/all
    buckets=[1, 3, 5, 8, 10, 15, 20, 30, 50],  # Optimized for 1-50 tools range
)

planner_domain_confidence_score = Histogram(
    "planner_domain_confidence_score",
    "Router confidence score for domain detection (used for planner filtering)",
    ["fallback_triggered"],  # fallback_triggered: true/false (confidence < threshold)
    buckets=[0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0],  # Confidence score buckets
)

planner_domain_filtering_cache_hits = Counter(
    "planner_domain_filtering_cache_hits_total",
    "Cache hits/misses for filtered catalogues (TTL 5min)",
    ["cache_status", "domains"],  # cache_status: hit/miss, domains: contacts/contacts+email/etc
)

# ============================================================================
# LLM JSON PARSING METRICS (2025-11-19)
# ============================================================================
# Metrics for tracking JSON parsing success/failure from LLM responses

agent_llm_json_parse_success_total = Counter(
    "agent_llm_json_parse_success_total",
    "Successful JSON parsing from LLM responses",
    ["context"],  # context: hierarchical_stage1, hierarchical_stage2, planner, hitl_classifier
)

agent_llm_json_parse_errors_total = Counter(
    "agent_llm_json_parse_errors_total",
    "Failed JSON parsing from LLM responses",
    [
        "context",
        "error_type",
    ],  # error_type: empty_response, decode_error, type_mismatch, missing_fields
)

# ============================================================================
# HITL PLAN-LEVEL APPROVAL METRICS (Phase 8 - 2025-11-09)
# ============================================================================
# Metrics for plan-level HITL approval gate (before execution)
# Replaces problematic tool-level HITL that interrupted mid-execution

hitl_plan_approval_requests = Counter(
    "hitl_plan_approval_requests_total",
    "Total plan approval requests sent to users",
    ["strategy"],  # strategy: ManifestBasedStrategy/CostThresholdStrategy/etc
)

hitl_plan_approval_latency = Histogram(
    "hitl_plan_approval_latency_seconds",
    "Time from approval request to user decision",
    # Buckets optimized for human response time
    # Users typically respond within 1-60 seconds for plan review
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

hitl_plan_decisions = Counter(
    "hitl_plan_decisions_total",
    "Plan approval decisions by type",
    ["decision"],  # decision: APPROVE/REJECT/EDIT/REPLAN
)

hitl_plan_modifications = Counter(
    "hitl_plan_modifications_total",
    "Plan modifications by type during EDIT workflow",
    ["modification_type"],  # modification_type: edit_params/remove_step/reorder_steps
)

hitl_plan_approval_question_duration = Histogram(
    "hitl_plan_approval_question_duration_seconds",
    "Time to generate plan approval question with LLM",
    # Buckets optimized for LLM generation time
    # Expected: 0.5-3s for question generation
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

hitl_plan_approval_question_fallback = Counter(
    "hitl_plan_approval_question_fallback_total",
    "Plan approval questions that fell back to static message",
    ["error_type"],  # error_type: timeout/llm_error/validation_error/etc
)

# ============================================================================
# HITL FOR_EACH BULK OPERATION METRICS
# ============================================================================
# Metrics for for_each bulk operation approval (before execution)
# Tracks user decision time and outcomes for bulk mutations

hitl_for_each_approval_latency = Histogram(
    "hitl_for_each_approval_latency_seconds",
    "Time from for_each approval request to user decision",
    # Buckets optimized for human response time (similar to plan approval)
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

hitl_for_each_decisions = Counter(
    "hitl_for_each_decisions_total",
    "For-each approval decisions by outcome",
    ["decision"],  # decision: confirm/cancel
)

# FOR_EACH HITL Pre-Execution Metrics (2026-01-19)
# Tracks pre-execution of provider steps for accurate HITL count display

hitl_for_each_pre_execution_duration = Histogram(
    "hitl_for_each_pre_execution_duration_seconds",
    "Duration of provider step pre-execution for HITL count",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

hitl_for_each_pre_execution_total = Counter(
    "hitl_for_each_pre_execution_total",
    "Pre-execution attempts by outcome",
    ["outcome"],  # outcome: success/failure
)

hitl_for_each_items_counted = Histogram(
    "hitl_for_each_items_counted",
    "Number of items counted during pre-execution",
    buckets=[1, 2, 5, 10, 20, 50, 100],
)

planner_for_each_auto_corrections = Counter(
    "planner_for_each_auto_corrections_total",
    "Auto-corrections of for_each attributes by type",
    ["correction_type"],  # correction_type: misplaced_attribute, invalid_type, max_exceeded
)

# ============================================================================
# PLAN EXECUTION METRICS (ADR-005)
# ============================================================================

langgraph_plan_steps_skipped_total = Counter(
    "langgraph_plan_steps_skipped_total",
    "Total steps skipped due to conditional branching (ADR-005)",
    [
        "plan_type",
        "skip_reason",
    ],  # plan_type: contacts/etc, skip_reason: fallback_branch/success_branch
)

langgraph_plan_wave_filtered_total = Counter(
    "langgraph_plan_wave_filtered_total",
    "Total waves that had steps filtered before execution (ADR-005)",
    ["plan_type", "filter_type"],  # filter_type: partial/complete
)

langgraph_plan_execution_efficiency = Histogram(
    "langgraph_plan_execution_efficiency_ratio",
    "Ratio of executed steps to total planned steps (measures branching efficiency)",
    ["plan_type"],
    buckets=[0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ============================================================================
# PLAN VALIDATION METRICS (ADR-006)
# ============================================================================

langgraph_plan_validation_warnings_total = Counter(
    "langgraph_plan_validation_warnings_total",
    "Total soft validation warnings issued for inefficient plan patterns (ADR-006)",
    ["warning_type", "plan_type"],  # warning_type: list_contacts_without_query, etc.
)

langgraph_tool_safeguard_applied_total = Counter(
    "langgraph_tool_safeguard_applied_total",
    "Total tool safeguards applied at runtime to prevent resource waste (ADR-006)",
    [FIELD_TOOL_NAME, "safeguard_type"],  # safeguard_type: limit_cap_no_query, etc.
)

# ============================================================================
# SEMANTIC VALIDATION METRICS (Phase 2 OPTIMPLAN - 2025-11-25)
# ============================================================================
# Metrics for semantic validation of execution plans
# Validates that plans semantically match user intent before approval

semantic_validation_total = Counter(
    "semantic_validation_total",
    "Total semantic validations performed",
    ["result"],  # result: valid/invalid/timeout/error
)

semantic_validation_duration_seconds = Histogram(
    "semantic_validation_duration_seconds",
    "Duration of semantic validation (includes LLM call)",
    # Buckets optimized for fast validation
    # Target: P95 < 2s, timeout at 1s
    buckets=[0.1, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0],
)

semantic_validation_timeout_total = Counter(
    "semantic_validation_timeout_total",
    "Semantic validations that timed out (optimistic fallback)",
    # Tracks timeout frequency to detect performance issues
    # High timeout rate indicates LLM or network issues
)

semantic_validation_issues_detected = Counter(
    "semantic_validation_issues_detected_total",
    "Semantic issues detected by type",
    ["issue_type"],  # issue_type: cardinality_mismatch/missing_dependency/etc
)

semantic_validation_clarification_requests = Counter(
    "semantic_validation_clarification_requests_total",
    "Plans requiring user clarification",
    # Tracks ambiguous requests requiring clarification flow
    # High rate may indicate poor planner prompt or complex queries
)

# ============================================================================
# CONTEXT RESOLUTION METRICS (LEGACY - REPLACED)
# ============================================================================
# NOTE: Old context resolution metrics removed - replaced by new metrics in section 550-579
# Old instrumentation in router_node.py migrated to context_resolution_service.py
# - context_resolution_total → context_resolution_attempts_total (better naming)
# - turn_type_total → context_resolution_turn_type_distribution_total (better naming)
# - context_resolution_confidence → context_resolution_confidence_score (better naming)
# - context_resolution_duration_seconds → kept, moved to section 574-579 (turn_type labels)
# Removed unused: context_reference_detected_total, context_items_resolved_total


# ============================================================================
# PLAN EDITOR METRICS (Phase 3 OPTIMPLAN - 2025-11-26)
# ============================================================================
# Metrics for EnhancedPlanEditor and SecurePlanEditor
# Tracks EDIT operations, schema validation, and security (injection detection)

plan_edit_operations_total = Counter(
    "plan_edit_operations_total",
    "Total plan edit operations by type",
    ["operation"],  # operation: edit_params/remove_step/reorder_steps
    # Tracks user modification patterns for UX optimization
    # High edit_params rate may indicate poor default parameters
)

plan_edit_schema_validation_failures_total = Counter(
    "plan_edit_schema_validation_failures_total",
    "Schema validation failures during plan edits",
    ["tool_name"],  # tool_name: search_contacts_tool/send_email/etc
    # Tracks tools with most validation failures
    # High failure rate indicates unclear parameter schemas
)

plan_edit_injection_blocked_total = Counter(
    "plan_edit_injection_blocked_total",
    "Injection patterns blocked during plan edits (security metric)",
    ["pattern"],  # pattern: dunder_attribute/eval_call/exec_call/import_statement/etc
    # SECURITY: Tracks attempted injection attacks
    # Any non-zero value should trigger security review
)

plan_edit_undo_operations_total = Counter(
    "plan_edit_undo_operations_total",
    "Total undo operations on plan edits",
    # Tracks usage of undo feature
    # High rate may indicate UX issues with edit flow
)


# ============================================================================
# HITL REJECTION METRICS (Phase 3 OPTIMPLAN - 2025-11-26)
# ============================================================================
# Metrics for dedicated REJECT flow (not error flow)
# Distinguishes user rejection from system errors

hitl_rejection_total = Counter(
    "hitl_rejection_total",
    "Total HITL rejections by reason category",
    ["reason_category"],
    # reason_category: explicit_rejection/timeout/modification_failed/etc
    # Tracks why users reject plans
    # High rate may indicate poor plan generation
)

hitl_rejection_response_tokens_total = Counter(
    "hitl_rejection_response_tokens_total",
    "Tokens generated for rejection response messages",
    # Tracks token usage for rejection responses
    # Used for cost analysis of rejection flow
)


# ============================================================================
# DATA REGISTRY COMMAND API METRICS (LOT 4.2 - 2025-11-26)
# ============================================================================
# Metrics for Data Registry Command API (deferred actions: drafts, events, contacts)
# Tracks draft lifecycle: creation → critique → confirm/edit/cancel → execute

registry_drafts_created_total = Counter(
    "registry_drafts_created_total",
    "Total drafts created by type",
    ["draft_type"],
    # draft_type: email, event, contact, task, note
    # Tracks draft creation rate per type
    # High rate indicates active user engagement with deferred actions
)

registry_drafts_executed_total = Counter(
    "registry_drafts_executed_total",
    "Total drafts executed after user confirmation",
    ["draft_type", "outcome"],
    # draft_type: email, event, contact
    # outcome: success, error
    # Tracks execution success rate per draft type
    # Low success rate may indicate integration issues
)

registry_draft_actions_total = Counter(
    "registry_draft_actions_total",
    "Total draft actions by type and action",
    ["draft_type", "action"],
    # draft_type: email, event, contact
    # action: confirm, edit, cancel
    # Tracks user behavior patterns with drafts
    # High cancel rate may indicate poor draft quality
)

registry_draft_lifecycle_duration_seconds = Histogram(
    "registry_draft_lifecycle_duration_seconds",
    "Time from draft creation to final action (confirm/cancel)",
    ["draft_type", "final_action"],
    buckets=[5, 15, 30, 60, 120, 300, 600, 1800, 3600],
    # draft_type: email, event, contact
    # final_action: confirmed, cancelled, expired
    # Tracks how long users take to review drafts
    # Very long durations may indicate abandoned drafts
)

registry_draft_edit_iterations_total = Counter(
    "registry_draft_edit_iterations_total",
    "Total edit iterations per draft before final action",
    ["draft_type"],
    # Tracks how many times users edit before confirming
    # High iteration count indicates poor initial draft quality
)

registry_draft_critique_questions_total = Counter(
    "registry_draft_critique_questions_total",
    "Total HITL critique questions generated for drafts",
    ["draft_type"],
    # Tracks HITL engagement with drafts
    # Should correlate with drafts_created_total
)


# ============================================================================
# ADAPTIVE RE-PLANNER METRICS (INTELLIPLANNER Phase E - 2025-12-03)
# ============================================================================
# Metrics for AdaptiveRePlanner - intelligent recovery from execution failures
# Tracks triggers, decisions, and recovery strategies

adaptive_replanner_triggers_total = Counter(
    "adaptive_replanner_triggers_total",
    "Total re-planning triggers detected by type",
    ["trigger"],
    # trigger: empty_results, partial_empty, partial_failure, reference_error, dependency_error, timeout, none
    # Tracks what failure patterns occur most frequently
    # High empty_results rate may indicate poor search criteria in plans
)

adaptive_replanner_decisions_total = Counter(
    "adaptive_replanner_decisions_total",
    "Total re-planning decisions by type",
    ["decision"],
    # decision: proceed, retry_same, replan_modified, replan_new, escalate_user, abort
    # Tracks recovery strategy effectiveness
    # High abort rate indicates unrecoverable failure patterns
)

adaptive_replanner_attempts_total = Counter(
    "adaptive_replanner_attempts_total",
    "Total re-planning attempts (retries)",
    ["attempt_number"],
    # attempt_number: 1, 2, 3, etc.
    # Tracks how many retries are needed before success
    # Ideally most successes at attempt 1
)

adaptive_replanner_recovery_success_total = Counter(
    "adaptive_replanner_recovery_success_total",
    "Successful recoveries by strategy",
    ["strategy"],
    # strategy: broaden_search, alternative_source, reduce_scope, skip_optional, add_verification
    # Tracks which recovery strategies are most effective
)


# ============================================================================
# ReAct Execution Mode (ADR-070)
# ============================================================================
react_agent_executions_total = Counter(
    "react_agent_executions_total",
    "Total ReAct agent node executions",
    ["status"],  # success, error, timeout
)
react_agent_iterations = Histogram(
    "react_agent_iterations",
    "ReAct agent iteration count distribution",
    buckets=[1, 2, 3, 5, 8, 10, 15],
)
react_agent_duration_seconds = Histogram(
    "react_agent_duration_seconds",
    "ReAct agent total execution duration",
    buckets=[1, 2, 5, 10, 30, 60, 120],
)
react_agent_tools_called_total = Counter(
    "react_agent_tools_called_total",
    "Tools called by ReAct agent",
    ["tool_name"],
)
react_agent_hitl_interrupts_total = Counter(
    "react_agent_hitl_interrupts_total",
    "HITL interrupts triggered in ReAct mode",
    ["tool_name", "decision"],  # decision: approve, reject
)
