"""
Centralized state tracking for LangGraph nodes.

This module consolidates the `_track_state_updates` function that was duplicated
across 6+ node files. It provides Prometheus metrics and structured logging for
LangGraph state mutations.

Usage:
    from src.domains.agents.utils.state_tracking import track_state_updates

    def my_node(state: MessagesState, config: RunnableConfig) -> dict:
        updated_state = {"key": "value"}
        track_state_updates(state, updated_state, "my_node", context_id)
        return updated_state
"""

from typing import Any

import structlog

from src.domains.agents.models import MessagesState
from src.infrastructure.observability.metrics_langgraph import (
    calculate_state_size,
    langgraph_state_size_bytes,
    langgraph_state_updates_total,
)

logger = structlog.get_logger(__name__)


def track_state_updates(
    state: MessagesState,
    updated_state: dict[str, Any],
    node_name: str,
    context_id: str | None = None,
    plan_id: str | None = None,
    additional_context: dict[str, Any] | None = None,
) -> None:
    """
    Track state updates and size for LangGraph observability.

    Centralizes state tracking to avoid duplication across multiple node files.
    Records Prometheus metrics for state key updates and state size, plus
    structured logging for debugging.

    Args:
        state: Current state before update (used to calculate merged state size)
        updated_state: State updates to be returned from the node
        node_name: Name of the node (e.g., "task_orchestrator", "approval_gate")
        context_id: Optional identifier for logging (run_id, draft_id, etc.)
        plan_id: Optional plan identifier (used by approval_gate_node)
        additional_context: Optional extra context for logging

    Metrics tracked:
        - langgraph_state_updates_total: Counter per (node_name, key)
        - langgraph_state_size_bytes: Histogram per node_name

    Example:
        >>> track_state_updates(
        ...     state=current_state,
        ...     updated_state={"agent_results": results, "routing_history": history},
        ...     node_name="task_orchestrator",
        ...     context_id=run_id,
        ... )

        >>> # With plan_id (approval_gate_node)
        >>> track_state_updates(
        ...     state=current_state,
        ...     updated_state={"execution_plan": plan},
        ...     node_name="approval_gate",
        ...     plan_id=plan.plan_id,
        ... )
    """
    # Track each state key update
    for key in updated_state.keys():
        langgraph_state_updates_total.labels(
            node_name=node_name,
            key=key,
        ).inc()

    # Calculate and track state size after merge
    merged_state = {**state, **updated_state}
    state_size = calculate_state_size(merged_state)
    langgraph_state_size_bytes.labels(node_name=node_name).observe(state_size)

    # Build log context
    log_context: dict[str, Any] = {
        "state_size_bytes": state_size,
        "updated_keys": list(updated_state.keys()),
    }
    if context_id:
        log_context["context_id"] = context_id
    if plan_id:
        log_context["plan_id"] = plan_id
    if additional_context:
        log_context.update(additional_context)

    # Structured logging with context
    logger.debug(f"{node_name}_state_updated", **log_context)
