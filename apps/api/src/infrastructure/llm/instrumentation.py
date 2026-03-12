"""
Generic LLM instrumentation utilities for Langfuse observability.

This module provides professional, generic helper functions for instrumenting
LangChain/LangGraph components with Langfuse callbacks according to 2025 best practices.

Architecture:
    - Config-based callback injection (LangChain 1.0+ pattern)
    - Automatic metadata enrichment
    - Support for distributed tracing
    - Thread-safe and production-ready
    - Generic: works with any LangChain/LangGraph component

Best Practices (2025):
    - Pass callbacks via RunnableConfig, not llm.callbacks
    - Use metadata for user/session tracking
    - Support distributed tracing with trace_id
    - Graceful degradation if Langfuse unavailable

Usage:
    >>> # Create instrumented config for LLM invoke
    >>> config = create_instrumented_config(
    ...     llm_type="router",
    ...     session_id="conv_123",
    ...     user_id="user_456",
    ...     metadata={"intent": "contacts_search"}
    ... )
    >>> response = llm.invoke(messages, config=config)

    >>> # Add callbacks to existing config
    >>> config = {"recursion_limit": 50}
    >>> config = enrich_config_with_callbacks(
    ...     config,
    ...     llm_type="planner",
    ...     session_id="conv_123"
    ... )

Integration Points:
    - LLM Factory (src/infrastructure/llm/factory.py)
    - Agent Service (src/domains/agents/api/service.py)
    - All LangGraph nodes

References:
    - LangChain RunnableConfig: https://python.langchain.com/docs/concepts/runnables
    - Langfuse Callbacks: https://langfuse.com/docs/integrations/langchain/tracing
    - Best Practices 2025: https://langfuse.com/guides/cookbook/integration_langchain

Phase: 6 - LLM Observability
Date: 2025-11-04
"""

import uuid
from typing import Any

import structlog
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.callbacks.manager import BaseCallbackManager
from langchain_core.runnables import RunnableConfig

from src.core.field_names import FIELD_CONVERSATION_ID, FIELD_USER_ID
from src.infrastructure.llm.callback_factory import get_callback_factory

logger = structlog.get_logger(__name__)


# =============================================================================
# CALLBACK MERGING HELPERS (Extracted for reduced complexity)
# =============================================================================


def _get_langfuse_handler_class() -> type:
    """
    Dynamically import LangFuse handler class.

    Returns:
        LangFuseCallbackHandler class or NoneType if not available
    """
    try:
        from langfuse.langchain import CallbackHandler as LangFuseCallbackHandler

        return LangFuseCallbackHandler
    except ImportError:
        return type(None)


def _check_langfuse_exists(
    callbacks: list[BaseCallbackHandler] | BaseCallbackManager | None,
    langfuse_class: type,
) -> bool:
    """
    Check if LangFuse handler already exists in callbacks.

    Args:
        callbacks: Existing callbacks (None, BaseCallbackManager, or list)
        langfuse_class: LangFuse handler class for isinstance checks

    Returns:
        True if LangFuse handler found
    """
    if callbacks is None:
        return False

    if isinstance(callbacks, BaseCallbackManager):
        return any(isinstance(cb, langfuse_class) for cb in callbacks.handlers)

    if isinstance(callbacks, list):
        return any(isinstance(cb, langfuse_class) for cb in callbacks)

    return False


def _extract_handlers(
    callbacks: list[BaseCallbackHandler] | BaseCallbackManager | None,
) -> list[BaseCallbackHandler]:
    """
    Extract handlers list from various callback types.

    Args:
        callbacks: Callbacks (None, BaseCallbackManager, or list)

    Returns:
        List of handlers (empty list if None)
    """
    if callbacks is None:
        return []

    if isinstance(callbacks, BaseCallbackManager):
        return list(callbacks.handlers)

    if isinstance(callbacks, list):
        return callbacks

    return []


def _filter_langfuse_handlers(
    handlers: list[BaseCallbackHandler],
    langfuse_class: type,
) -> list[BaseCallbackHandler]:
    """
    Filter out LangFuse handlers from a list.

    Args:
        handlers: List of callback handlers
        langfuse_class: LangFuse handler class

    Returns:
        Filtered list without LangFuse handlers
    """
    return [cb for cb in handlers if not isinstance(cb, langfuse_class)]


def _merge_callbacks(
    existing_callbacks: list[BaseCallbackHandler] | BaseCallbackManager | None,
    new_callbacks: list[BaseCallbackHandler],
    has_existing_langfuse: bool,
    langfuse_class: type,
    llm_type: str,
) -> list[BaseCallbackHandler]:
    """
    Merge existing and new callbacks with LangFuse deduplication.

    Strategy:
        - If LangFuse exists in existing: skip adding new LangFuse, keep existing
        - If LangFuse doesn't exist: filter old LangFuse (if any) and add new

    Args:
        existing_callbacks: Current callbacks from config
        new_callbacks: New callbacks to add
        has_existing_langfuse: Whether LangFuse exists in existing_callbacks
        langfuse_class: LangFuse handler class
        llm_type: LLM type for logging

    Returns:
        Merged callback list
    """
    # Filter new callbacks if LangFuse already exists
    if has_existing_langfuse:
        callbacks_to_add = _filter_langfuse_handlers(new_callbacks, langfuse_class)
        if len(callbacks_to_add) != len(new_callbacks):
            logger.debug(
                "langfuse_handler_already_exists_skipping_duplicate",
                llm_type=llm_type,
                new_callbacks_before=len(new_callbacks),
                new_callbacks_after=len(callbacks_to_add),
            )
    else:
        callbacks_to_add = new_callbacks

    # Extract and optionally filter existing handlers
    existing_handlers = _extract_handlers(existing_callbacks)

    if has_existing_langfuse:
        # Keep all existing (LangFuse already there, we skipped adding new one)
        filtered_handlers = existing_handlers
    else:
        # Filter old LangFuse handlers (we're adding a new one)
        filtered_handlers = _filter_langfuse_handlers(existing_handlers, langfuse_class)

    # Merge
    merged = filtered_handlers + callbacks_to_add

    logger.debug(
        "callbacks_merged",
        llm_type=llm_type,
        existing_count=len(existing_handlers),
        filtered_count=len(filtered_handlers),
        new_count=len(callbacks_to_add),
        total_count=len(merged),
        has_existing_langfuse=has_existing_langfuse,
    )

    return merged


# =============================================================================
# MAIN INSTRUMENTATION FUNCTIONS
# =============================================================================


def create_instrumented_config(
    llm_type: str,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    trace_name: str | None = None,
    trace_id: str | None = None,
    parent_trace_id: str | None = None,
    subgraph_name: str | None = None,
    depth: int = 0,
    base_config: RunnableConfig | None = None,
) -> RunnableConfig:
    """
    Create instrumented RunnableConfig with Langfuse callbacks (2025 best practice).

    This is the recommended way to instrument LangChain/LangGraph components in 2025.
    Creates a complete RunnableConfig with callbacks, metadata, and optional base config.

    Best Practice Pattern:
        llm.invoke(messages, config=create_instrumented_config(...))

    Args:
        llm_type: LLM type identifier (e.g., "router", "planner", "contacts_agent")
        session_id: Conversation/session identifier for grouping traces
        user_id: User identifier for user-level analytics
        tags: Additional tags beyond llm_type (auto-added: llm_type, provider, model)
        metadata: Additional metadata beyond auto-enriched fields
        trace_name: Human-readable trace name (defaults to "{llm_type}_call")
        trace_id: Custom trace ID for distributed tracing (auto-generated if None)
        parent_trace_id: Parent trace ID for nested subgraph hierarchy (Phase 3.1.5)
        subgraph_name: Subgraph identifier for hierarchical tracing (Phase 3.1.5)
        depth: Trace depth level for nested subgraphs (0=root, 1=child, etc.) (Phase 3.1.5)
        base_config: Existing config to merge with (e.g., {"recursion_limit": 50})

    Returns:
        RunnableConfig with callbacks and metadata ready for invoke()

    Example - Basic Usage:
        >>> config = create_instrumented_config(
        ...     llm_type="router",
        ...     session_id="conv_123",
        ...     user_id="user_456",
        ...     metadata={"intent": "search"}
        ... )
        >>> response = llm.invoke(messages, config=config)

    Example - With Base Config:
        >>> base = {"recursion_limit": 50, "max_concurrency": 10}
        >>> config = create_instrumented_config(
        ...     llm_type="planner",
        ...     session_id="conv_123",
        ...     base_config=base
        ... )
        >>> response = graph.invoke(state, config=config)

    Example - Distributed Tracing:
        >>> parent_trace_id = factory.generate_trace_id()
        >>> # Use same trace_id for all related operations
        >>> config1 = create_instrumented_config("router", trace_id=parent_trace_id)
        >>> config2 = create_instrumented_config("planner", trace_id=parent_trace_id)

    Example - Subgraph Tracing (Phase 3.1.5):
        >>> # Root graph invocation
        >>> root_config = create_instrumented_config(
        ...     llm_type="orchestrator",
        ...     session_id="conv_123",
        ...     depth=0
        ... )
        >>> # Subgraph invocation with parent context
        >>> subgraph_config = create_instrumented_config(
        ...     llm_type="contacts_agent",
        ...     session_id="conv_123",
        ...     parent_trace_id=root_trace_id,
        ...     subgraph_name="contacts_subgraph",
        ...     depth=1
        ... )
    """
    # Start with base config or empty dict
    config: RunnableConfig = dict(base_config) if base_config else {}

    # Auto-enrich tags with llm_type
    enriched_tags = [llm_type]
    if tags:
        enriched_tags.extend(tags)

    # Auto-enrich metadata with llm_type and observability context
    # IMPORTANT: Metadata is always added, even if Langfuse is disabled
    # This allows tests to validate metadata enrichment without Langfuse
    enriched_metadata = {
        "llm_type": llm_type,
        "instrumentation_version": "1.0.0",
        **(metadata or {}),
    }

    # Langfuse v3.x: Add special metadata keys for session/user/tags context
    if session_id:
        enriched_metadata["langfuse_session_id"] = session_id
    if user_id:
        enriched_metadata["langfuse_user_id"] = user_id
    if enriched_tags:
        enriched_metadata["langfuse_tags"] = enriched_tags

    # Default trace name to "{llm_type}_call" if not provided
    final_trace_name = trace_name or f"{llm_type}_call"
    enriched_metadata["langfuse_trace_name"] = final_trace_name

    # Add trace_id to metadata if provided (for distributed tracing)
    if trace_id:
        enriched_metadata["langfuse_trace_id"] = trace_id

    # Phase 3.1.5: Add subgraph tracing metadata for nested trace hierarchy
    if parent_trace_id:
        enriched_metadata["langfuse_parent_trace_id"] = parent_trace_id
    if subgraph_name:
        enriched_metadata["langfuse_subgraph_name"] = subgraph_name
    # Always add depth for trace hierarchy visualization
    enriched_metadata["langfuse_trace_depth"] = depth

    # Instrument Prometheus metrics for subgraph tracing (Phase 3.1.6.3)
    try:
        from src.infrastructure.observability.metrics_langfuse import (
            langfuse_subgraph_invocations,
            langfuse_trace_depth,
        )

        # Track trace depth distribution (always, even at root level)
        langfuse_trace_depth.labels(
            depth_level=str(depth),
        ).observe(depth)

        # Track subgraph invocations (only if subgraph_name provided)
        if subgraph_name:
            langfuse_subgraph_invocations.labels(
                subgraph_name=subgraph_name,
                status="invoked",  # Will be updated to success/error by callbacks
            ).inc()
    except Exception:
        # Graceful degradation - metrics failure shouldn't break instrumentation
        pass

    # Add metadata to config (always, even if Langfuse disabled)
    config["metadata"] = enriched_metadata

    # Get callback factory
    factory = get_callback_factory()

    # Log factory state at DEBUG level (avoid pollution in production logs)
    logger.debug(
        "enrich_config_factory_check",
        llm_type=llm_type,
        factory_exists=factory is not None,
        factory_enabled=factory.is_enabled() if factory else False,
    )

    if not factory or not factory.is_enabled():
        logger.warning(
            "langfuse_disabled_skipping_instrumentation",
            llm_type=llm_type,
            factory_exists=factory is not None,
        )
        return config

    try:
        # Create Langfuse callbacks (v3.9+: singleton handler, NO parameters)
        # Context is passed ONLY via config["metadata"] with special keys:
        # - langfuse_session_id, langfuse_user_id, langfuse_tags, langfuse_trace_name
        callbacks = factory.create_callbacks()

        # Log callbacks created at DEBUG level (avoid pollution in production logs)
        logger.debug(
            "langfuse_callbacks_created",
            llm_type=llm_type,
            callbacks_count=len(callbacks),
            trace_name=final_trace_name,
            session_id=session_id,
            user_id=user_id,
            tags_count=len(enriched_tags),
        )

        # Merge callbacks using helper functions (Phase 2.1.2/2.1.3 deduplication)
        langfuse_class = _get_langfuse_handler_class()
        existing_callbacks = config.get("callbacks")
        has_existing_langfuse = _check_langfuse_exists(existing_callbacks, langfuse_class)

        # Handle unknown callback types gracefully
        if existing_callbacks is not None and not isinstance(
            existing_callbacks, BaseCallbackManager | list
        ):
            logger.warning(
                "unknown_callback_type_in_config",
                callback_type=type(existing_callbacks).__name__,
                llm_type=llm_type,
            )
            config["callbacks"] = callbacks
        else:
            config["callbacks"] = _merge_callbacks(
                existing_callbacks=existing_callbacks,
                new_callbacks=callbacks,
                has_existing_langfuse=has_existing_langfuse,
                langfuse_class=langfuse_class,
                llm_type=llm_type,
            )

        # Add tags to config
        config["tags"] = enriched_tags

        # Note: metadata already added to config at line 184 (before factory check)
        # This ensures metadata is present even when Langfuse is disabled

        # Log final config (callbacks is guaranteed to be a list after _merge_callbacks)
        merged_callbacks = config["callbacks"]
        logger.debug(
            "instrumented_config_created",
            llm_type=llm_type,
            session_id=session_id,
            trace_name=final_trace_name,
            callbacks_count=len(merged_callbacks) if isinstance(merged_callbacks, list) else 0,
        )

        return config

    except Exception as e:
        logger.error(
            "instrumentation_failed",
            error=str(e),
            error_type=type(e).__name__,
            llm_type=llm_type,
        )
        # Graceful degradation: return base config without callbacks
        return config


def enrich_config_with_callbacks(
    config: RunnableConfig,
    llm_type: str,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    trace_name: str | None = None,
    trace_id: str | None = None,
    parent_trace_id: str | None = None,
    subgraph_name: str | None = None,
    depth: int = 0,
) -> RunnableConfig:
    """
    Add Langfuse callbacks to existing RunnableConfig (in-place enrichment).

    Use this when you already have a config dict and want to add observability.
    This is a convenience wrapper around create_instrumented_config with base_config.

    Args:
        config: Existing RunnableConfig to enrich
        llm_type: LLM type identifier
        session_id: Session/conversation identifier
        user_id: User identifier
        tags: Additional tags for filtering
        metadata: Additional metadata
        trace_name: Human-readable trace name
        trace_id: Custom trace ID for distributed tracing
        parent_trace_id: Parent trace ID for nested subgraph hierarchy (Phase 3.1.5)
        subgraph_name: Subgraph identifier for hierarchical tracing (Phase 3.1.5)
        depth: Trace depth level for nested subgraphs (Phase 3.1.5)

    Returns:
        Enriched config (same reference as input, modified in-place)

    Example:
        >>> config = {"recursion_limit": 50}
        >>> config = enrich_config_with_callbacks(
        ...     config,
        ...     llm_type="planner",
        ...     session_id="conv_123"
        ... )
        >>> # config now has callbacks, metadata, tags
        >>> response = graph.invoke(state, config=config)
    """
    return create_instrumented_config(
        llm_type=llm_type,
        session_id=session_id,
        user_id=user_id,
        tags=tags,
        metadata=metadata,
        trace_name=trace_name,
        trace_id=trace_id,
        parent_trace_id=parent_trace_id,
        subgraph_name=subgraph_name,
        depth=depth,
        base_config=config,
    )


def create_subgraph_config(
    llm_type: str,
    parent_config: RunnableConfig,
    subgraph_name: str,
    metadata: dict[str, Any] | None = None,
) -> RunnableConfig:
    """
    Create instrumented config for subgraph invocation with automatic parent trace context.

    This helper automatically propagates parent trace context (session_id, user_id, trace_id)
    from parent config to subgraph, increments depth, and adds subgraph-specific metadata.

    Phase: 3.1.5 - Nested Trace Hierarchy
    Best Practice: Use this for all subgraph invocations to maintain trace hierarchy.

    Args:
        llm_type: LLM type identifier for subgraph (e.g., "contacts_agent", "emails_agent")
        parent_config: Parent graph's RunnableConfig (contains parent context)
        subgraph_name: Human-readable subgraph identifier
        metadata: Additional subgraph-specific metadata

    Returns:
        RunnableConfig with parent context + subgraph metadata

    Example:
        >>> # In orchestrator node invoking contacts subgraph
        >>> parent_config = config  # From orchestrator's invoke(state, config=config)
        >>> subgraph_config = create_subgraph_config(
        ...     llm_type="contacts_agent",
        ...     parent_config=parent_config,
        ...     subgraph_name="contacts_search",
        ...     metadata={"query": "find john@example.com"}
        ... )
        >>> result = contacts_subgraph.invoke(state, config=subgraph_config)

    Automatic Context Propagation:
        - session_id (from parent metadata["langfuse_session_id"])
        - user_id (from parent metadata["langfuse_user_id"])
        - parent_trace_id (from parent metadata["langfuse_trace_id"])
        - depth (parent depth + 1)
    """
    # Extract parent metadata
    parent_metadata = parent_config.get("metadata", {})

    # Extract parent context
    session_id = parent_metadata.get("langfuse_session_id")
    user_id = parent_metadata.get("langfuse_user_id")
    parent_trace_id = parent_metadata.get("langfuse_trace_id")
    parent_depth = parent_metadata.get("langfuse_trace_depth", 0)
    parent_tags = parent_metadata.get("langfuse_tags", [])

    # Increment depth for subgraph
    subgraph_depth = parent_depth + 1

    # Merge parent tags with subgraph tag
    enriched_tags = parent_tags.copy() if isinstance(parent_tags, list) else []
    enriched_tags.append(f"subgraph:{subgraph_name}")

    # Generate unique trace_id for this subgraph to enable further nesting
    # This allows child subgraphs to reference this subgraph as their parent
    subgraph_trace_id = f"trace_{subgraph_name}_{uuid.uuid4().hex[:8]}"

    # Create subgraph config with parent context
    return create_instrumented_config(
        llm_type=llm_type,
        session_id=session_id,
        user_id=user_id,
        tags=enriched_tags,
        metadata=metadata,
        trace_name=f"{subgraph_name}_subgraph",
        trace_id=subgraph_trace_id,  # Unique trace ID for this subgraph
        parent_trace_id=parent_trace_id,  # Parent's trace ID
        subgraph_name=subgraph_name,
        depth=subgraph_depth,
        base_config=parent_config,  # Preserve other config like recursion_limit
    )


def extract_session_user_from_state(state: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Extract session_id and user_id from LangGraph state (generic helper).

    This helper provides a standard way to extract observability identifiers
    from LangGraph state, supporting common field naming conventions.

    Supports Multiple Naming Conventions:
        - session_id, thread_id, conversation_id
        - user_id, userId

    Args:
        state: LangGraph state dict

    Returns:
        Tuple of (session_id, user_id) - None if not found

    Example:
        >>> state = {"thread_id": "conv_123", "user_id": "user_456"}
        >>> session_id, user_id = extract_session_user_from_state(state)
        >>> config = create_instrumented_config(
        ...     llm_type="router",
        ...     session_id=session_id,
        ...     user_id=user_id
        ... )
    """
    # Extract session_id (multiple naming conventions)
    # Note: Using string literals for session_id/thread_id to avoid circular imports (infrastructure shouldn't depend on agents.constants)
    session_id = (
        state.get("session_id") or state.get("thread_id") or state.get(FIELD_CONVERSATION_ID)
    )

    # Extract user_id (multiple naming conventions)
    user_id = state.get(FIELD_USER_ID) or state.get("userId")

    return session_id, user_id


# Note: create_distributed_trace_context() function has been removed.
# This function was never used in the codebase (0 references found).
# Distributed tracing is handled via RunnableConfig propagation instead.
# Removed on 2025-11-07 as part of dead code elimination (Decision 1: API INTERNE).
