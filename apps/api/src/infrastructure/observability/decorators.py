"""
Observability Decorators - Auto-instrumentation for metrics, tracing, and logging.

This module provides decorators to automatically track execution metrics,
eliminating boilerplate code and ensuring consistent instrumentation.

Usage:
    @track_metrics(
        node_name="router",
        duration_metric=agent_node_duration_seconds,
        counter_metric=agent_node_executions_total,
    )
    async def router_node(state, config):
        # Business logic only - metrics tracked automatically
        return result

Phase 3.2 Enhancement:
- track_tool_metrics() now tracks BOTH framework AND business metrics
- Framework metrics: agent_tool_invocations, agent_tool_duration_seconds
- Business metrics: agent_tool_usage_total (with agent_type, outcome labels)
"""

import asyncio
import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar, cast

import structlog
from prometheus_client import Counter, Histogram

P = ParamSpec("P")
T = TypeVar("T")

logger = structlog.get_logger(__name__)


# ============================================================================
# HELPER FUNCTIONS (PHASE 3.2)
# ============================================================================


def extract_agent_type_from_agent_name(agent_name: str) -> str:
    """
    Extract agent_type from agent_name for business metrics.

    Converts "contacts_agent" → "contacts", "emails_agent" → "emails", etc.
    Falls back to agent_name if pattern doesn't match.

    Args:
        agent_name: Full agent name (e.g., "contacts_agent", "context_agent")

    Returns:
        Agent type for business metrics (e.g., "contacts", "context")

    Example:
        >>> extract_agent_type_from_agent_name("contacts_agent")
        "contacts"
        >>> extract_agent_type_from_agent_name("generic_agent")
        "generic"
    """
    # Pattern: "{agent_type}_agent" → extract agent_type
    if agent_name.endswith("_agent"):
        return agent_name[:-6]  # Remove "_agent" suffix
    # Fallback: use full agent_name
    return agent_name


def map_success_to_outcome(success: bool) -> str:
    """
    Map framework success boolean to business outcome string.

    Framework metrics use success="true"/"false".
    Business metrics use outcome="success"/"failure"/"user_rejected".

    Args:
        success: Whether tool execution succeeded (True/False)

    Returns:
        Outcome string for business metrics ("success" or "failure")

    Note:
        "user_rejected" outcome is tracked separately in approval_gate_node (HITL).
        This function only handles tool execution success/failure.
    """
    return "success" if success else "failure"


def track_metrics(
    *,
    node_name: str,
    duration_metric: Histogram | None = None,
    counter_metric: Counter | None = None,
    log_execution: bool = True,
    log_errors: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to automatically track execution metrics for agent nodes and functions.

    Automatically handles:
    - Execution duration (histogram)
    - Success/error counters
    - Structured logging (optional)
    - Async and sync functions

    Args:
        node_name: Name of the node/function for metric labels
        duration_metric: Prometheus Histogram to observe duration (optional)
        counter_metric: Prometheus Counter to increment (optional)
        log_execution: Whether to log execution start/completion (default: True)
        log_errors: Whether to log errors (default: True)

    Returns:
        Decorated function with automatic metrics tracking

    Example:
        >>> from src.infrastructure.observability.metrics_agents import (
        ...     agent_node_duration_seconds,
        ...     agent_node_executions_total,
        ... )
        >>>
        >>> @track_metrics(
        ...     node_name="router",
        ...     duration_metric=agent_node_duration_seconds,
        ...     counter_metric=agent_node_executions_total,
        ... )
        >>> async def router_node(state, config):
        ...     # Just implement business logic!
        ...     return {"next_node": "planner"}

    Notes:
        - Metrics are only recorded if provided (pass None to skip)
        - Works with both async and sync functions
        - Errors are re-raised after logging/metrics
        - Thread-safe and async-safe
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Detect if function is async
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start_time = time.time()

                if log_execution:
                    logger.debug(
                        "node_execution_started",
                        node_name=node_name,
                        func_name=func.__name__,
                    )

                try:
                    # Execute function
                    result = await func(*args, **kwargs)  # type: ignore[misc]

                    # Record success metric
                    if counter_metric:
                        counter_metric.labels(node_name=node_name, status="success").inc()

                    if log_execution:
                        logger.debug(
                            "node_execution_completed",
                            node_name=node_name,
                            func_name=func.__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                        )

                    return cast(T, result)

                except Exception as e:
                    # Record error metric
                    if counter_metric:
                        counter_metric.labels(node_name=node_name, status="error").inc()

                    if log_errors:
                        logger.error(
                            "node_execution_failed",
                            node_name=node_name,
                            func_name=func.__name__,
                            error=str(e),
                            error_type=type(e).__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                            exc_info=True,
                        )

                    # Re-raise exception
                    raise

                finally:
                    # Always record duration
                    if duration_metric:
                        duration = time.time() - start_time
                        duration_metric.labels(node_name=node_name).observe(duration)

            return async_wrapper  # type: ignore[return-value]

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start_time = time.time()

                if log_execution:
                    logger.debug(
                        "node_execution_started",
                        node_name=node_name,
                        func_name=func.__name__,
                    )

                try:
                    # Execute function
                    result = func(*args, **kwargs)

                    # Record success metric
                    if counter_metric:
                        counter_metric.labels(node_name=node_name, status="success").inc()

                    if log_execution:
                        logger.debug(
                            "node_execution_completed",
                            node_name=node_name,
                            func_name=func.__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                        )

                    return result

                except Exception as e:
                    # Record error metric
                    if counter_metric:
                        counter_metric.labels(node_name=node_name, status="error").inc()

                    if log_errors:
                        logger.error(
                            "node_execution_failed",
                            node_name=node_name,
                            func_name=func.__name__,
                            error=str(e),
                            error_type=type(e).__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                            exc_info=True,
                        )

                    # Re-raise exception
                    raise

                finally:
                    # Always record duration
                    if duration_metric:
                        duration = time.time() - start_time
                        duration_metric.labels(node_name=node_name).observe(duration)

            return sync_wrapper

    return decorator


def track_tool_metrics(
    *,
    tool_name: str,
    agent_name: str,
    duration_metric: Histogram | None = None,
    counter_metric: Counter | None = None,
    log_execution: bool = True,
    log_errors: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to automatically track execution metrics for agent tools.

    Similar to @track_metrics but adapted for tools with different label structure:
    - Uses tool_name + agent_name labels instead of node_name
    - Uses success="true"/"false" instead of status="success"/"error"

    Phase 3.2 Enhancement:
    - Now tracks BOTH framework metrics AND business metrics
    - Framework: agent_tool_invocations, agent_tool_duration_seconds
    - Business: agent_tool_usage_total (with agent_type, outcome labels)

    Automatically handles:
    - Execution duration (histogram)
    - Success/failure counters (framework + business)
    - Structured logging (optional)
    - Async and sync functions

    Args:
        tool_name: Name of the tool for metric labels (e.g., "search_contacts")
        agent_name: Name of the agent owning the tool (e.g., "contacts_agent")
        duration_metric: Prometheus Histogram to observe duration (optional)
        counter_metric: Prometheus Counter to increment (optional)
        log_execution: Whether to log execution start/completion (default: True)
        log_errors: Whether to log errors (default: True)

    Returns:
        Decorated function with automatic metrics tracking

    Example:
        >>> from src.infrastructure.observability.metrics_agents import (
        ...     agent_tool_duration_seconds,
        ...     agent_tool_invocations,
        ... )
        >>>
        >>> @track_tool_metrics(
        ...     tool_name="search_contacts",
        ...     agent_name="contacts_agent",
        ...     duration_metric=agent_tool_duration_seconds,
        ...     counter_metric=agent_tool_invocations,
        ... )
        >>> async def search_contacts_tool(query: str, runtime: ToolRuntime):
        ...     # Just implement business logic!
        ...     return search_results

    Notes:
        - Metrics are only recorded if provided (pass None to skip)
        - Works with both async and sync functions
        - Errors are re-raised after logging/metrics
        - Thread-safe and async-safe
        - Business metrics tracked via lazy import (graceful degradation)
    """

    # Lazy import of business metrics (Phase 3.2)
    # Graceful degradation: if import fails, only framework metrics are tracked
    try:
        from src.infrastructure.observability.metrics_business import (
            agent_tool_usage_total,
        )

        business_metrics_available = True
    except ImportError:
        logger.warning(
            "business_metrics_import_failed",
            msg="agent_tool_usage_total not available, only framework metrics will be tracked",
        )
        business_metrics_available = False

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        # Detect if function is async
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start_time = time.time()

                if log_execution:
                    logger.debug(
                        "tool_execution_started",
                        tool_name=tool_name,
                        agent_name=agent_name,
                        func_name=func.__name__,
                    )

                try:
                    # Execute function
                    result = await func(*args, **kwargs)  # type: ignore[misc]

                    # Record success metrics (FRAMEWORK)
                    if counter_metric:
                        counter_metric.labels(
                            tool_name=tool_name, agent_name=agent_name, success="true"
                        ).inc()

                    # Record success metrics (BUSINESS - Phase 3.2)
                    if business_metrics_available:
                        agent_type = extract_agent_type_from_agent_name(agent_name)
                        outcome = map_success_to_outcome(success=True)
                        agent_tool_usage_total.labels(
                            agent_type=agent_type, tool_name=tool_name, outcome=outcome
                        ).inc()

                    if log_execution:
                        logger.debug(
                            "tool_execution_completed",
                            tool_name=tool_name,
                            agent_name=agent_name,
                            func_name=func.__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                        )

                    return cast(T, result)

                except Exception as e:
                    # Record error metrics (FRAMEWORK)
                    if counter_metric:
                        counter_metric.labels(
                            tool_name=tool_name, agent_name=agent_name, success="false"
                        ).inc()

                    # Record error metrics (BUSINESS - Phase 3.2)
                    if business_metrics_available:
                        agent_type = extract_agent_type_from_agent_name(agent_name)
                        outcome = map_success_to_outcome(success=False)
                        agent_tool_usage_total.labels(
                            agent_type=agent_type, tool_name=tool_name, outcome=outcome
                        ).inc()

                    if log_errors:
                        logger.error(
                            "tool_execution_failed",
                            tool_name=tool_name,
                            agent_name=agent_name,
                            func_name=func.__name__,
                            error=str(e),
                            error_type=type(e).__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                            exc_info=True,
                        )

                    # Re-raise exception
                    raise

                finally:
                    # Always record duration
                    if duration_metric:
                        duration = time.time() - start_time
                        duration_metric.labels(tool_name=tool_name, agent_name=agent_name).observe(
                            duration
                        )

            return async_wrapper  # type: ignore[return-value]

        else:

            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start_time = time.time()

                if log_execution:
                    logger.debug(
                        "tool_execution_started",
                        tool_name=tool_name,
                        agent_name=agent_name,
                        func_name=func.__name__,
                    )

                try:
                    # Execute function
                    result = func(*args, **kwargs)

                    # Record success metrics (FRAMEWORK)
                    if counter_metric:
                        counter_metric.labels(
                            tool_name=tool_name, agent_name=agent_name, success="true"
                        ).inc()

                    # Record success metrics (BUSINESS - Phase 3.2)
                    if business_metrics_available:
                        agent_type = extract_agent_type_from_agent_name(agent_name)
                        outcome = map_success_to_outcome(success=True)
                        agent_tool_usage_total.labels(
                            agent_type=agent_type, tool_name=tool_name, outcome=outcome
                        ).inc()

                    if log_execution:
                        logger.debug(
                            "tool_execution_completed",
                            tool_name=tool_name,
                            agent_name=agent_name,
                            func_name=func.__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                        )

                    return result

                except Exception as e:
                    # Record error metrics (FRAMEWORK)
                    if counter_metric:
                        counter_metric.labels(
                            tool_name=tool_name, agent_name=agent_name, success="false"
                        ).inc()

                    # Record error metrics (BUSINESS - Phase 3.2)
                    if business_metrics_available:
                        agent_type = extract_agent_type_from_agent_name(agent_name)
                        outcome = map_success_to_outcome(success=False)
                        agent_tool_usage_total.labels(
                            agent_type=agent_type, tool_name=tool_name, outcome=outcome
                        ).inc()

                    if log_errors:
                        logger.error(
                            "tool_execution_failed",
                            tool_name=tool_name,
                            agent_name=agent_name,
                            func_name=func.__name__,
                            error=str(e),
                            error_type=type(e).__name__,
                            duration_ms=int((time.time() - start_time) * 1000),
                            exc_info=True,
                        )

                    # Re-raise exception
                    raise

                finally:
                    # Always record duration
                    if duration_metric:
                        duration = time.time() - start_time
                        duration_metric.labels(tool_name=tool_name, agent_name=agent_name).observe(
                            duration
                        )

            return sync_wrapper

    return decorator
