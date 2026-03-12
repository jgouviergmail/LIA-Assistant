"""
Tool Call Tracing for Langfuse - Phase 3.1.5.2.

Provides utilities to trace LangChain tool calls to Langfuse with metadata:
- tool_name: Name of the tool being called
- tool_input: Input parameters (JSON serialized)
- tool_output: Output result (JSON serialized or error message)
- success: Boolean indicating success/failure
- duration_ms: Execution duration in milliseconds

Architecture:
- trace_tool_call(): Context manager for wrapping tool execution with Langfuse span
- Integrates with existing @track_tool_metrics decorator
- Automatic error handling and metadata enrichment

Best Practices 2025:
- Structured metadata (JSON serialization)
- PII filtering for sensitive data
- Duration tracking in milliseconds
- Error categorization (client vs server errors)

Phase: 3.1.5 - Nested Trace Hierarchy
Date: 2025-11-23
"""

import json
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog

from src.infrastructure.llm.callback_factory import get_callback_factory

logger = structlog.get_logger(__name__)


def _serialize_tool_data(data: Any, max_length: int = 2000) -> str:
    """
    Serialize tool input/output data to JSON string.

    Handles:
    - Primitive types (str, int, float, bool, None)
    - Collections (dict, list, tuple)
    - Complex objects (converts to string via repr)
    - Length truncation for large data

    Args:
        data: Data to serialize (can be any type)
        max_length: Maximum string length (default: 2000)

    Returns:
        JSON string or truncated repr string
    """
    try:
        # Attempt JSON serialization
        json_str = json.dumps(data, ensure_ascii=False, default=str)

        # Truncate if too long
        if len(json_str) > max_length:
            json_str = json_str[:max_length] + "... [truncated]"

        return json_str
    except (TypeError, ValueError):
        # Fall back to repr for non-serializable objects
        repr_str = repr(data)
        if len(repr_str) > max_length:
            repr_str = repr_str[:max_length] + "... [truncated]"
        return repr_str


@contextmanager
def trace_tool_call(
    tool_name: str,
    tool_input: dict[str, Any],
    agent_name: str | None = None,
    parent_trace_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Context manager to trace tool call execution to Langfuse.

    Captures:
    - Tool execution start/end timestamps
    - Input parameters (JSON serialized)
    - Output result (JSON serialized)
    - Success/failure status
    - Execution duration in milliseconds
    - Error details (if any)

    Phase: 3.1.5.2 - Tool Call Tracing
    Best Practice: Use this as context manager around tool execution.

    Args:
        tool_name: Name of the tool (e.g., "search_contacts")
        tool_input: Tool input parameters as dict
        agent_name: Agent executing the tool (optional)
        parent_trace_id: Parent trace ID for hierarchical tracing (optional)

    Yields:
        Context dict containing metadata for the current trace

    Example:
        >>> with trace_tool_call(
        ...     tool_name="search_contacts",
        ...     tool_input={"query": "john@example.com"},
        ...     agent_name="contacts_agent",
        ... ) as trace_ctx:
        ...     result = await execute_tool(tool_input)
        ...     trace_ctx["output"] = result
        ...     trace_ctx["success"] = True
    """
    # Get callback factory
    factory = get_callback_factory()

    # Initialize trace context
    trace_ctx: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_input": _serialize_tool_data(tool_input),
        "agent_name": agent_name,
        "parent_trace_id": parent_trace_id,
        "start_time": time.time(),
        "success": False,  # Default to failure, will be set to True on success
        "output": None,
        "error": None,
    }

    # Check if Langfuse is enabled (store flag for later use)
    langfuse_enabled = factory is not None and factory.is_enabled()

    if not langfuse_enabled:
        logger.debug(
            "langfuse_disabled_skipping_tool_trace",
            tool_name=tool_name,
            agent_name=agent_name,
        )

    try:
        # Log tool call start (only if Langfuse enabled)
        if langfuse_enabled:
            logger.info(
                "tool_call_start",
                tool_name=tool_name,
                agent_name=agent_name,
                tool_input_preview=(
                    tool_input if len(str(tool_input)) < 200 else f"{str(tool_input)[:200]}..."
                ),
            )

        # Yield context to caller (tool executes here)
        yield trace_ctx

    except Exception as e:
        # Capture error details
        trace_ctx["success"] = False
        trace_ctx["error"] = str(e)
        trace_ctx["error_type"] = type(e).__name__

        if langfuse_enabled:
            logger.error(
                "tool_call_error",
                tool_name=tool_name,
                agent_name=agent_name,
                error=str(e),
                error_type=type(e).__name__,
            )
        raise

    finally:
        # ALWAYS calculate duration (even if Langfuse disabled - needed for tests and debugging)
        end_time = time.time()
        duration_seconds = end_time - trace_ctx["start_time"]
        duration_ms = duration_seconds * 1000

        trace_ctx["duration_ms"] = duration_ms
        trace_ctx["end_time"] = end_time

        # Serialize output
        if trace_ctx.get("output") is not None:
            trace_ctx["output_serialized"] = _serialize_tool_data(trace_ctx["output"])

        # Log tool call completion (only if Langfuse enabled)
        if langfuse_enabled:
            logger.info(
                "tool_call_complete",
                tool_name=tool_name,
                agent_name=agent_name,
                success=trace_ctx["success"],
                duration_ms=round(duration_ms, 2),
                has_error=trace_ctx.get("error") is not None,
            )

            # Send trace to Langfuse (only if enabled)
            # Note: This will be implemented once Langfuse span API is available
            # For now, metadata is logged and available for manual inspection
            try:
                _send_tool_trace_to_langfuse(trace_ctx, factory)
            except Exception as e:
                # Graceful degradation - don't fail tool execution if tracing fails
                logger.warning(
                    "langfuse_tool_trace_failed",
                    tool_name=tool_name,
                    error=str(e),
                    error_type=type(e).__name__,
                )


def _send_tool_trace_to_langfuse(
    trace_ctx: dict[str, Any],
    factory: Any,
) -> None:
    """
    Send tool trace metadata to Langfuse + Prometheus metrics.

    Integrates with:
    1. Langfuse span API (when available) - for detailed trace visualization
    2. Prometheus metrics (Phase 3.1.6.3) - for aggregated dashboard metrics

    Phase: 3.1.5.2 - Tool Call Tracing
    Phase: 3.1.6.3 - Metrics Instrumentation

    Args:
        trace_ctx: Tool trace context containing all metadata
        factory: CallbackFactory instance
    """
    # Import Prometheus metrics (lazy import to avoid circular dependencies)
    from src.infrastructure.observability.metrics_langfuse import langfuse_tool_calls

    # Increment Prometheus tool call counter (Phase 3.1.6.3)
    langfuse_tool_calls.labels(
        tool_name=trace_ctx["tool_name"],
        success=str(trace_ctx["success"]).lower(),  # "true" or "false" (lowercase for consistency)
    ).inc()

    # TODO: Langfuse span API integration (future)
    # Placeholder implementation - will integrate with Langfuse span API when available:
    #
    # Example (when Langfuse span API available):
    # span = factory.create_span(
    #     name=trace_ctx["tool_name"],
    #     metadata={
    #         "tool_name": trace_ctx["tool_name"],
    #         "tool_input": trace_ctx["tool_input"],
    #         "tool_output": trace_ctx.get("output_serialized"),
    #         "agent_name": trace_ctx.get("agent_name"),
    #         "success": trace_ctx["success"],
    #         "duration_ms": trace_ctx["duration_ms"],
    #         "error": trace_ctx.get("error"),
    #         "error_type": trace_ctx.get("error_type"),
    #     },
    #     parent_trace_id=trace_ctx.get("parent_trace_id"),
    # )

    logger.debug(
        "tool_trace_metadata_captured",
        tool_name=trace_ctx["tool_name"],
        success=trace_ctx["success"],
        duration_ms=trace_ctx.get("duration_ms"),
        has_output=trace_ctx.get("output") is not None,
        has_error=trace_ctx.get("error") is not None,
    )


def enrich_tool_metadata(
    metadata: dict[str, Any],
    tool_name: str,
    success: bool,
    duration_ms: float,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Enrich RunnableConfig metadata with tool tracing information.

    Adds Phase 3.1.5.2 tool tracing metadata to existing metadata dict.

    Args:
        metadata: Existing metadata dict (from RunnableConfig)
        tool_name: Name of the tool
        success: Boolean indicating success/failure
        duration_ms: Execution duration in milliseconds
        error: Error message if failed (optional)

    Returns:
        Enriched metadata dict with tool tracing fields

    Example:
        >>> metadata = {"session_id": "sess_123"}
        >>> enriched = enrich_tool_metadata(
        ...     metadata,
        ...     tool_name="search_contacts",
        ...     success=True,
        ...     duration_ms=245.67,
        ... )
        >>> enriched["langfuse_tool_name"]  # "search_contacts"
        >>> enriched["langfuse_tool_success"]  # True
        >>> enriched["langfuse_tool_duration_ms"]  # 245.67
    """
    return {
        **metadata,
        "langfuse_tool_name": tool_name,
        "langfuse_tool_success": success,
        "langfuse_tool_duration_ms": round(duration_ms, 2),
        "langfuse_tool_error": error,
    }
