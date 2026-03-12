"""
Data Registry Prometheus Metrics.

Defines metrics for monitoring the Data Registry system (rich frontend rendering).
All metrics use appropriate prefixes for easy identification in Grafana.

Metric Categories:
1. Tool Execution: Track tool executions and outcomes
2. Registry: Track items added/removed from registry
3. HITL: Track human-in-the-loop interactions
4. Performance: Track latencies and throughput

Usage:
    from src.infrastructure.observability.metrics_registry import (
        registry_tool_executions_total,
        registry_items_total,
    )

    registry_tool_executions_total.labels(tool="search_contacts", status="success").inc()
    registry_items_total.labels(tool="search_contacts", type="CONTACT").inc()
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# TOOL EXECUTION METRICS
# ============================================================================

registry_tool_executions_total = Counter(
    "registry_tool_executions_total",
    "Total registry-enabled tool executions",
    ["tool", "status"],  # status: success, error
)

registry_tool_execution_duration_seconds = Histogram(
    "registry_tool_execution_duration_seconds",
    "Duration of registry-enabled tool executions",
    ["tool"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ============================================================================
# REGISTRY METRICS
# ============================================================================

registry_items_total = Counter(
    "registry_items_total",
    "Total items added to data registry",
    ["tool", "type"],  # label type: CONTACT, EMAIL, EVENT, DRAFT, etc.
)

registry_size = Gauge(
    "registry_size",
    "Current number of items in data registry per thread",
    ["thread_id"],
)

registry_expired_total = Counter(
    "registry_expired_total",
    "Total items expired/removed from data registry",
    ["type"],
)

# ============================================================================
# HITL (Human-in-the-Loop) METRICS
# ============================================================================

hitl_interrupts_total = Counter(
    "hitl_interrupts_total",
    "Total HITL interruptions triggered",
    ["tool", "reason"],  # reason: plan_approval, write_operation, clarification
)

hitl_resolutions_total = Counter(
    "hitl_resolutions_total",
    "Total HITL resolutions by action",
    ["action"],  # action: approve, refine, reject
)

hitl_wait_duration_seconds = Histogram(
    "hitl_wait_duration_seconds",
    "Time spent waiting for HITL approval",
    ["reason"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],  # Up to 10 minutes
)

# ============================================================================
# SSE STREAMING METRICS
# ============================================================================

sse_events_total = Counter(
    "sse_events_total",
    "Total SSE events emitted",
    ["event_type"],  # event_type: registry_update, content_delta, agent_state, hitl_metadata
)

sse_registry_update_bytes = Histogram(
    "sse_registry_update_bytes",
    "Size of registry_update SSE events in bytes",
    buckets=[100, 500, 1000, 5000, 10000, 50000],
)

# ============================================================================
# QUERY ENGINE METRICS (LocalQueryEngineTool)
# ============================================================================

query_engine_operations_total = Counter(
    "query_engine_operations_total",
    "Total LocalQueryEngine operations by type",
    ["operation", "status"],  # operation: filter, sort, group, similarity, aggregate
)

query_engine_items_processed = Histogram(
    "query_engine_items_processed",
    "Number of items processed by LocalQueryEngine per query",
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
)

query_engine_results_returned = Histogram(
    "query_engine_results_returned",
    "Number of results returned by LocalQueryEngine per query",
    buckets=[0, 1, 5, 10, 25, 50, 100, 250],
)

query_engine_duration_seconds = Histogram(
    "query_engine_duration_seconds",
    "Duration of LocalQueryEngine query execution",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# ============================================================================
# CHECKPOINT/STATE METRICS
# ============================================================================

checkpoints_total = Counter(
    "checkpoints_total",
    "Total PostgresSaver checkpoints created",
    ["thread_id"],
)

checkpoints_table_size_bytes = Gauge(
    "checkpoints_table_size_bytes",
    "Size of checkpoints table in bytes",
)

# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================


def track_tool_execution(
    tool_name: str,
    status: str,
    duration_seconds: float,
    registry_items: dict | None = None,
) -> None:
    """
    Track a registry-enabled tool execution with all relevant metrics.

    Args:
        tool_name: Name of the tool executed
        status: "success" or "error"
        duration_seconds: Execution duration
        registry_items: Optional dict of registry items produced
    """
    registry_tool_executions_total.labels(tool=tool_name, status=status).inc()
    registry_tool_execution_duration_seconds.labels(tool=tool_name).observe(duration_seconds)

    if registry_items:
        for item in registry_items.values():
            registry_items_total.labels(
                tool=tool_name,
                type=item.type.value if hasattr(item, "type") else "unknown",
            ).inc()


def track_hitl_interrupt(tool_name: str, reason: str) -> None:
    """
    Track a HITL interruption.

    Args:
        tool_name: Tool that triggered the interrupt
        reason: Reason for interrupt (plan_approval, write_operation, clarification)
    """
    hitl_interrupts_total.labels(tool=tool_name, reason=reason).inc()


def track_hitl_resolution(action: str, wait_seconds: float, reason: str) -> None:
    """
    Track a HITL resolution.

    Args:
        action: Resolution action (approve, refine, reject)
        wait_seconds: Time user spent before responding
        reason: Original interrupt reason
    """
    hitl_resolutions_total.labels(action=action).inc()
    hitl_wait_duration_seconds.labels(reason=reason).observe(wait_seconds)


def track_sse_event(event_type: str, payload_bytes: int | None = None) -> None:
    """
    Track SSE event emission.

    Args:
        event_type: Type of SSE event (registry_update, content_delta, etc.)
        payload_bytes: Optional size of payload in bytes
    """
    sse_events_total.labels(event_type=event_type).inc()

    if event_type == "registry_update" and payload_bytes:
        sse_registry_update_bytes.observe(payload_bytes)


def track_query_engine_execution(
    operation: str,
    status: str,
    duration_seconds: float,
    items_processed: int,
    results_returned: int,
) -> None:
    """
    Track a LocalQueryEngine query execution with all relevant metrics.

    Args:
        operation: Query operation type (filter, sort, group, similarity, aggregate)
        status: "success" or "error"
        duration_seconds: Execution duration
        items_processed: Number of items scanned
        results_returned: Number of results returned
    """
    query_engine_operations_total.labels(operation=operation, status=status).inc()
    query_engine_duration_seconds.labels(operation=operation).observe(duration_seconds)
    query_engine_items_processed.observe(items_processed)
    query_engine_results_returned.observe(results_returned)


# ============================================================================
# PROACTIVE TASK METRICS
# ============================================================================

proactive_task_processed_total = Counter(
    "proactive_task_processed_total",
    "Total users processed by proactive tasks",
    ["task_type"],  # task_type: interest, birthday, event, summary
)

proactive_task_success_total = Counter(
    "proactive_task_success_total",
    "Total successful proactive notifications sent",
    ["task_type"],
)

proactive_task_failed_total = Counter(
    "proactive_task_failed_total",
    "Total failed proactive task executions",
    ["task_type"],
)

proactive_task_skipped_total = Counter(
    "proactive_task_skipped_total",
    "Total skipped proactive tasks (not eligible, no target, etc.)",
    ["task_type"],
)

proactive_task_duration_seconds = Histogram(
    "proactive_task_duration_seconds",
    "Duration of proactive task batch execution",
    ["task_type"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],  # Up to 10 minutes
)

proactive_notification_channel_total = Counter(
    "proactive_notification_channel_total",
    "Total proactive notifications sent per channel",
    ["task_type", "channel"],  # channel: fcm, sse, archive
)

proactive_tokens_total = Counter(
    "proactive_tokens_total",
    "Total tokens consumed by proactive tasks",
    ["task_type", "token_type"],  # token_type: input, output, cache
)

proactive_cost_eur_total = Counter(
    "proactive_cost_eur_total",
    "Total cost in EUR for proactive tasks",
    ["task_type"],
)

proactive_content_source_total = Counter(
    "proactive_content_source_total",
    "Total content generations by source",
    ["task_type", "source"],  # source: wikipedia, perplexity, llm_reflection
)

proactive_feedback_total = Counter(
    "proactive_feedback_total",
    "Total user feedback on proactive notifications",
    ["task_type", "feedback_type"],  # feedback_type: thumbs_up, thumbs_down, block
)

proactive_eligibility_check_total = Counter(
    "proactive_eligibility_check_total",
    "Total eligibility checks by result",
    [
        "task_type",
        "result",
    ],  # result: eligible, feature_disabled, outside_time_window, quota_exceeded, etc.
)


def track_proactive_task_execution(
    task_type: str,
    processed: int,
    success: int,
    failed: int,
    skipped: int,
    duration_seconds: float,
) -> None:
    """
    Track a proactive task batch execution with all relevant metrics.

    Args:
        task_type: Type of proactive task (interest, birthday, etc.)
        processed: Number of users processed
        success: Number of successful notifications
        failed: Number of failures
        skipped: Number of skipped users
        duration_seconds: Batch execution duration
    """
    proactive_task_processed_total.labels(task_type=task_type).inc(processed)
    proactive_task_success_total.labels(task_type=task_type).inc(success)
    proactive_task_failed_total.labels(task_type=task_type).inc(failed)
    proactive_task_skipped_total.labels(task_type=task_type).inc(skipped)
    proactive_task_duration_seconds.labels(task_type=task_type).observe(duration_seconds)


def track_proactive_notification(
    task_type: str,
    fcm_sent: bool,
    sse_sent: bool,
    archived: bool,
) -> None:
    """
    Track a proactive notification dispatch.

    Args:
        task_type: Type of proactive task
        fcm_sent: Whether FCM was sent successfully
        sse_sent: Whether SSE was published
        archived: Whether message was archived
    """
    if fcm_sent:
        proactive_notification_channel_total.labels(task_type=task_type, channel="fcm").inc()
    if sse_sent:
        proactive_notification_channel_total.labels(task_type=task_type, channel="sse").inc()
    if archived:
        proactive_notification_channel_total.labels(task_type=task_type, channel="archive").inc()


def track_proactive_tokens(
    task_type: str,
    tokens_in: int,
    tokens_out: int,
    tokens_cache: int,
    cost_eur: float,
) -> None:
    """
    Track token usage for a proactive task.

    Args:
        task_type: Type of proactive task
        tokens_in: Input tokens consumed
        tokens_out: Output tokens generated
        tokens_cache: Cached tokens used
        cost_eur: Cost in EUR
    """
    proactive_tokens_total.labels(task_type=task_type, token_type="input").inc(tokens_in)
    proactive_tokens_total.labels(task_type=task_type, token_type="output").inc(tokens_out)
    proactive_tokens_total.labels(task_type=task_type, token_type="cache").inc(tokens_cache)
    proactive_cost_eur_total.labels(task_type=task_type).inc(cost_eur)


def track_proactive_feedback(task_type: str, feedback_type: str) -> None:
    """
    Track user feedback on a proactive notification.

    Args:
        task_type: Type of proactive task
        feedback_type: Type of feedback (thumbs_up, thumbs_down, block)
    """
    proactive_feedback_total.labels(task_type=task_type, feedback_type=feedback_type).inc()
