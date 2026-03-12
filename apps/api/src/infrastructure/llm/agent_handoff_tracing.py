"""
Agent Handoff Tracing for Langfuse - Phase 3.1.5.3.

Provides utilities to trace multi-agent handoffs and conversation flow visualization:
- source_agent: Agent initiating the handoff
- target_agent: Agent receiving control
- handoff_reason: Why the handoff occurred
- conversation_flow: Sequence of agent transitions

Architecture:
- trace_agent_handoff(): Context manager for wrapping agent invocations
- Integrates with existing subgraph tracing (Phase 3.1.5.1)
- Enriches metadata with handoff-specific information
- Enables Langfuse conversation flow visualization

Best Practices 2025:
- Structured metadata (JSON serialization)
- Hierarchical trace linking (parent_trace_id)
- Duration tracking in milliseconds
- Conversation flow tracking for debugging

Phase: 3.1.5.3 - Multi-Agent Tracing
Date: 2025-11-23
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog

from src.infrastructure.llm.callback_factory import get_callback_factory

logger = structlog.get_logger(__name__)


@contextmanager
def trace_agent_handoff(
    source_agent: str | None,
    target_agent: str,
    handoff_reason: str,
    parent_trace_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Context manager to trace agent handoffs in multi-agent orchestration.

    Captures:
    - Source and target agents
    - Reason for handoff (e.g., "router_decision", "plan_execution", "subgraph_invocation")
    - Handoff duration
    - Success/failure status
    - Conversation flow tracking

    Phase: 3.1.5.3 - Multi-Agent Tracing
    Best Practice: Use this around agent subgraph invocations to track handoffs.

    Args:
        source_agent: Agent initiating the handoff (None if root graph)
        target_agent: Agent receiving control (e.g., "contacts_agent")
        handoff_reason: Reason for handoff (e.g., "router_high_confidence")
        parent_trace_id: Parent trace ID for hierarchical tracing
        metadata: Additional metadata for this handoff

    Yields:
        Context dict containing metadata for the current handoff trace

    Example:
        >>> # In orchestrator invoking contacts_agent
        >>> with trace_agent_handoff(
        ...     source_agent="router",
        ...     target_agent="contacts_agent",
        ...     handoff_reason="high_confidence_routing",
        ...     parent_trace_id=parent_trace_id,
        ... ) as handoff_ctx:
        ...     result = await contacts_agent.invoke(state, config=merged_config)
        ...     handoff_ctx["success"] = True
        ...     handoff_ctx["agent_output"] = result
    """
    # Get callback factory
    factory = get_callback_factory()

    # Initialize handoff trace context
    handoff_ctx: dict[str, Any] = {
        "source_agent": source_agent,
        "target_agent": target_agent,
        "handoff_reason": handoff_reason,
        "parent_trace_id": parent_trace_id,
        "start_time": time.time(),
        "success": False,  # Default to failure, will be set to True on success
        "agent_output": None,
        "error": None,
        **(metadata or {}),
    }

    # Check if Langfuse is enabled (store flag for later use)
    langfuse_enabled = factory is not None and factory.is_enabled()

    if not langfuse_enabled:
        logger.debug(
            "langfuse_disabled_skipping_handoff_trace",
            source_agent=source_agent,
            target_agent=target_agent,
        )

    try:
        # Log handoff start (only if Langfuse enabled)
        if langfuse_enabled:
            logger.info(
                "agent_handoff_start",
                source_agent=source_agent,
                target_agent=target_agent,
                handoff_reason=handoff_reason,
                parent_trace_id=parent_trace_id,
            )

        # Yield context to caller (agent executes here)
        yield handoff_ctx

    except Exception as e:
        # Capture error details
        handoff_ctx["success"] = False
        handoff_ctx["error"] = str(e)
        handoff_ctx["error_type"] = type(e).__name__

        if langfuse_enabled:
            logger.error(
                "agent_handoff_error",
                source_agent=source_agent,
                target_agent=target_agent,
                error=str(e),
                error_type=type(e).__name__,
            )
        raise

    finally:
        # ALWAYS calculate duration (even if Langfuse disabled - needed for tests and debugging)
        end_time = time.time()
        duration_seconds = end_time - handoff_ctx["start_time"]
        duration_ms = duration_seconds * 1000

        handoff_ctx["duration_ms"] = duration_ms
        handoff_ctx["end_time"] = end_time

        # Log handoff completion (only if Langfuse enabled)
        if langfuse_enabled:
            logger.info(
                "agent_handoff_complete",
                source_agent=source_agent,
                target_agent=target_agent,
                success=handoff_ctx["success"],
                duration_ms=round(duration_ms, 2),
                has_error=handoff_ctx.get("error") is not None,
            )

            # Send trace to Langfuse (only if enabled)
            try:
                _send_handoff_trace_to_langfuse(handoff_ctx, factory)
            except Exception as e:
                # Graceful degradation - don't fail agent execution if tracing fails
                logger.warning(
                    "langfuse_handoff_trace_failed",
                    source_agent=source_agent,
                    target_agent=target_agent,
                    error=str(e),
                    error_type=type(e).__name__,
                )


def _send_handoff_trace_to_langfuse(
    handoff_ctx: dict[str, Any],
    factory: Any,
) -> None:
    """
    Send agent handoff trace metadata to Langfuse + Prometheus metrics.

    Integrates with:
    1. Langfuse span API (when available) - for detailed trace visualization
    2. Prometheus metrics (Phase 3.1.6.3) - for aggregated dashboard metrics

    Phase: 3.1.5.3 - Multi-Agent Tracing
    Phase: 3.1.6.3 - Metrics Instrumentation

    Args:
        handoff_ctx: Handoff trace context containing all metadata
        factory: CallbackFactory instance
    """
    # Import Prometheus metrics (lazy import to avoid circular dependencies)
    from src.infrastructure.observability.metrics_langfuse import (
        langfuse_agent_handoffs,
        langfuse_handoff_duration_seconds,
    )

    # Get source and target agents
    source_agent = handoff_ctx["source_agent"] or "root"  # Use "root" for None source
    target_agent = handoff_ctx["target_agent"]

    # Increment agent handoff counter (Phase 3.1.6.3)
    langfuse_agent_handoffs.labels(
        source_agent=source_agent,
        target_agent=target_agent,
    ).inc()

    # Observe handoff duration histogram (Phase 3.1.6.3)
    # Convert milliseconds to seconds (Prometheus convention)
    duration_seconds = handoff_ctx["duration_ms"] / 1000.0
    langfuse_handoff_duration_seconds.labels(
        source_agent=source_agent,
        target_agent=target_agent,
    ).observe(duration_seconds)

    # TODO: Langfuse span API integration (future)
    # Placeholder implementation - will integrate with Langfuse span API when available:
    #
    # Example (when Langfuse span API available):
    # span = factory.create_span(
    #     name=f"{source_agent}_to_{target_agent}",
    #     metadata={
    #         "source_agent": source_agent,
    #         "target_agent": target_agent,
    #         "handoff_reason": handoff_ctx["handoff_reason"],
    #         "success": handoff_ctx["success"],
    #         "duration_ms": handoff_ctx["duration_ms"],
    #         "error": handoff_ctx.get("error"),
    #         "error_type": handoff_ctx.get("error_type"),
    #     },
    #     parent_trace_id=handoff_ctx.get("parent_trace_id"),
    # )

    logger.debug(
        "handoff_trace_metadata_captured",
        source_agent=source_agent,
        target_agent=target_agent,
        success=handoff_ctx["success"],
        duration_ms=handoff_ctx.get("duration_ms"),
        has_error=handoff_ctx.get("error") is not None,
    )


def enrich_handoff_metadata(
    metadata: dict[str, Any],
    source_agent: str | None,
    target_agent: str,
    handoff_reason: str,
    success: bool,
    duration_ms: float,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Enrich RunnableConfig metadata with agent handoff tracing information.

    Adds Phase 3.1.5.3 handoff tracing metadata to existing metadata dict.

    Args:
        metadata: Existing metadata dict (from RunnableConfig)
        source_agent: Source agent name (or None if root)
        target_agent: Target agent name
        handoff_reason: Reason for handoff
        success: Boolean indicating success/failure
        duration_ms: Handoff duration in milliseconds
        error: Error message if failed (optional)

    Returns:
        Enriched metadata dict with handoff tracing fields

    Example:
        >>> metadata = {"langfuse_session_id": "sess_123"}
        >>> enriched = enrich_handoff_metadata(
        ...     metadata,
        ...     source_agent="router",
        ...     target_agent="contacts_agent",
        ...     handoff_reason="high_confidence",
        ...     success=True,
        ...     duration_ms=345.67,
        ... )
        >>> enriched["langfuse_handoff_source"]  # "router"
        >>> enriched["langfuse_handoff_target"]  # "contacts_agent"
        >>> enriched["langfuse_handoff_success"]  # True
    """
    return {
        **metadata,
        "langfuse_handoff_source": source_agent,
        "langfuse_handoff_target": target_agent,
        "langfuse_handoff_reason": handoff_reason,
        "langfuse_handoff_success": success,
        "langfuse_handoff_duration_ms": round(duration_ms, 2),
        "langfuse_handoff_error": error,
    }


def track_conversation_flow(
    state: dict[str, Any],
    agent_name: str,
) -> list[dict[str, Any]]:
    """
    Track conversation flow by maintaining sequence of agent transitions.

    Enables visualization of multi-agent conversation flow in Langfuse dashboard.

    Phase: 3.1.5.3 - Multi-Agent Tracing
    Best Practice: Call this after each agent invocation to build conversation flow.

    Args:
        state: LangGraph state (will be enriched with conversation_flow)
        agent_name: Name of agent that just executed

    Returns:
        Updated conversation flow list

    Example:
        >>> # In agent wrapper node
        >>> flow = track_conversation_flow(state, "contacts_agent")
        >>> # flow = [
        >>> #     {"agent": "router", "timestamp": 1700000000.0},
        >>> #     {"agent": "contacts_agent", "timestamp": 1700000001.5},
        >>> # ]
    """
    # Get existing conversation flow from state
    conversation_flow = state.get("conversation_flow", [])

    # Add current agent to flow
    conversation_flow.append(
        {
            "agent": agent_name,
            "timestamp": time.time(),
        }
    )

    logger.debug(
        "conversation_flow_updated",
        agent_name=agent_name,
        flow_length=len(conversation_flow),
        flow_sequence=[step["agent"] for step in conversation_flow],
    )

    return conversation_flow
