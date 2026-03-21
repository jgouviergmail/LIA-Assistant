"""
Generic helpers for invoking LLM with automatic Langfuse instrumentation & metadata enrichment.

This module provides professional, production-ready helpers for invoking LLM
with automatic observability, regardless of how the code is structured.

Architecture:
    - Works with existing code (backward compatible)
    - Automatically enriches RunnableConfig with Langfuse callbacks
    - Extracts session/user context from multiple sources (state, config, kwargs)
    - **Ensures node_name propagates to callbacks for token tracking**
    - Graceful degradation if Langfuse unavailable

Best Practices (2025):
    - Config-based callback injection (LangChain 1.0+)
    - Automatic metadata enrichment with node context
    - Support for both sync and async invocations
    - Thread-safe and production-ready
    - Generic & reusable across all agent types

Critical Fix (Phase 2.1 - RC1/RC4):
    LangGraph automatically sets config["metadata"]["langgraph_node"] when calling nodes,
    but LangChain does NOT propagate this to kwargs["metadata"] during LLM invocations.

    This module ensures metadata["langgraph_node"] is ALWAYS present in kwargs so callbacks
    (MetricsCallbackHandler, TokenTrackingCallback) can extract the correct node_name.

Usage Patterns:

    1. **Direct usage** (recommended for new code):
        >>> config = create_instrumented_config_from_node(
        ...     llm_type="router",
        ...     state=state,
        ...     base_config=config
        ... )
        >>> response = await llm.ainvoke(messages, config=config)

    2. **Wrapper usage** (for existing code):
        >>> response = await invoke_with_instrumentation(
        ...     llm=llm,
        ...     llm_type="router",
        ...     messages=messages,
        ...     state=state,
        ...     config=config
        ... )

Phase: 6 - LLM Observability + Phase 2.1 - Token Tracking Alignment
Date: 2025-11-05
"""

from typing import Any
from uuid import UUID

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.field_names import FIELD_METADATA, FIELD_USER_ID
from src.infrastructure.llm.instrumentation import (
    create_instrumented_config,
    extract_session_user_from_state,
)

logger = structlog.get_logger(__name__)


def _resolve_user_id_for_limit_check(
    explicit_user_id: str | None,
    state: dict[str, Any] | None,
    config: RunnableConfig | None,
) -> UUID | None:
    """Resolve user_id from available sources for usage limit checking.

    Returns None if no valid user UUID found or if user_id is "system"
    (system-level calls not attributable to a user).

    Priority: explicit parameter > state > config metadata.

    Args:
        explicit_user_id: Explicitly passed user_id (may be UUID string or "system").
        state: LangGraph state dict (may contain user_id).
        config: RunnableConfig (may contain user_id in metadata).

    Returns:
        UUID if a valid user_id is found, None otherwise.
    """
    uid_str = explicit_user_id

    if not uid_str and state:
        _, extracted_uid = extract_session_user_from_state(state)
        uid_str = extracted_uid

    if not uid_str and config:
        metadata = config.get("metadata") or {}
        uid_str = metadata.get(FIELD_USER_ID)

    if not uid_str or uid_str == "system":
        return None

    try:
        return UUID(uid_str)
    except (ValueError, AttributeError):
        return None


# ============================================================================
# Metadata Enrichment for Token Tracking (Phase 2.1 - RC1/RC4 Fix)
# ============================================================================


def enrich_config_with_node_metadata(
    config: RunnableConfig | None,
    node_name: str,
) -> RunnableConfig:
    """
    Enrich RunnableConfig to ensure node_name propagates to LLM callbacks.

    **Critical for Token Tracking Alignment (Phase 2.1 - RC1/RC4)**

    Problem:
        LangGraph automatically sets config["metadata"]["langgraph_node"] when
        invoking nodes, but LangChain does NOT propagate config["metadata"] into
        kwargs["metadata"] during nested LLM invocations (.ainvoke, .with_structured_output).

        Result: MetricsCallbackHandler receives kwargs["metadata"] = {} (empty),
        leading to node_name="unknown" in all token tracking metrics.

    Solution:
        This helper explicitly ensures metadata["langgraph_node"] exists and is
        accessible to callbacks. Called before EVERY LLM invocation.

    Architecture:
        - **Generic & Reusable**: Works for ALL agent types (router, response, planner, etc.)
        - **Centralized**: Single source of truth for metadata enrichment
        - **Backward Compatible**: Preserves existing metadata, doesn't break anything
        - **Type-Safe**: Properly typed RunnableConfig

    Usage Pattern (Best Practice 2025):
        ```python
        # In any node that calls LLM
        def my_node(state: State, config: RunnableConfig) -> dict:
            # Extract node name from config (set by LangGraph)
            node_name = config.get(FIELD_METADATA, {}).get("langgraph_node", "unknown")

            # Enrich config for LLM invocation
            enriched_config = enrich_config_with_node_metadata(config, node_name)

            # LLM call with enriched config
            llm = get_llm("my_llm")
            result = await llm.ainvoke(messages, config=enriched_config)
            # Callbacks now receive kwargs["metadata"]["langgraph_node"] = "my_node"
        ```

    Integration Points:
        1. **get_structured_output()**: Automatically enriches before llm.ainvoke()
        2. **Direct LLM calls**: Manual enrichment before llm.ainvoke()
        3. **create_instrumented_config_from_node()**: Integrated in this helper

    Args:
        config: Original RunnableConfig from node (may be None)
        node_name: Node identifier ("router", "response", "planner", "contacts_agent", etc.)

    Returns:
        Enriched RunnableConfig with guaranteed metadata["langgraph_node"]

    Validation:
        - If config is None, creates new config with metadata
        - If config lacks "metadata", adds it
        - Always sets/overrides "langgraph_node" to ensure correctness

    Example - From router node:
        >>> config = {"metadata": {"run_id": "123"}}
        >>> enriched = enrich_config_with_node_metadata(config, "router")
        >>> assert enriched["metadata"]["langgraph_node"] == "router"
        >>> assert enriched["metadata"]["run_id"] == "123"  # Preserved

    Example - From config with LangGraph metadata:
        >>> config = {"metadata": {"langgraph_node": "router_v1", "other": "data"}}
        >>> enriched = enrich_config_with_node_metadata(config, "router")
        >>> assert enriched["metadata"]["langgraph_node"] == "router"  # Overridden
        >>> assert enriched["metadata"]["other"] == "data"  # Preserved

    References:
        - Root Cause Analysis: docs/agents/TOKEN_TRACKING_ROOT_CAUSE_ANALYSIS.md
        - LangChain Callbacks: https://python.langchain.com/docs/concepts/callbacks/
        - ADR-015: Token Tracking Architecture V2
    """
    # Initialize config if None
    if config is None:
        config = {}

    # Ensure metadata key exists
    if "metadata" not in config:
        config["metadata"] = {}  # type: ignore[typeddict-item]

    # Set langgraph_node (override if exists to ensure correctness)
    # This ensures callbacks receive the correct node_name
    config["metadata"]["langgraph_node"] = node_name  # type: ignore[typeddict-item]

    # **Phase 2.1 - CRITICAL FIX**: Add MetricsCallbackHandler with correct node_name
    # The MetricsCallbackHandler must be created per-invocation, not per-LLM
    # This is the ONLY way to get dynamic node_name tracking in LangChain
    from src.infrastructure.observability.callbacks import MetricsCallbackHandler

    # Get existing callbacks from config
    existing_callbacks = config.get("callbacks", [])
    if existing_callbacks is None:
        existing_callbacks = []
    elif not isinstance(existing_callbacks, list):
        # Handle AsyncCallbackManager or other types - convert to list
        existing_callbacks = list(getattr(existing_callbacks, "handlers", [existing_callbacks]))

    # **Phase 2.1.5 - BREAKTHROUGH**: The Problem Was REVERSED!
    #
    # Critical Discovery:
    #   - The DB was UNDER-COUNTING (not LangFuse/Prometheus over-counting)
    #   - TokenTrackingCallback was FILTERED here -> DB lost ALL tokens
    #   - LangFuse/Prometheus were counting correctly
    #   - Result: DB=5,760 vs LangFuse=28,860 (5x seemed like over-counting but was correct)
    #
    # Root Cause:
    #   1. service.py adds TokenTrackingCallback at graph-level
    #   2. Each node calls enrich_config_with_node_metadata()
    #   3. This function FILTERED TokenTrackingCallback (line 202 BEFORE this fix)
    #   4. Result: NO LLM call was tracked in the DB
    #   5. DB showed nearly 0 tokens while LangFuse/Prometheus counted everything correctly
    #
    # Handlers to Filter:
    #   - MetricsCallbackHandler: YES (replace with new node_name at each node)
    #   - TokenTrackingCallback: NO (must persist to accumulate tokens in DB)
    #   - LangFuseCallbackHandler: NO (must persist, deduplication via instrumentation.py)
    #
    # Solution:
    #   Filter ONLY MetricsCallbackHandler
    #   Preserve TokenTracking (DB accumulation) and LangFuse (tracing)

    filtered_callbacks = [
        cb
        for cb in existing_callbacks
        if not isinstance(
            cb,
            MetricsCallbackHandler,
        )
    ]

    # Add MetricsCallbackHandler with the correct node_name for this invocation
    # Note: We pass llm=None because we don't have access to it here, but that's OK
    # The callback will still extract model_name from the response
    metrics_callback = MetricsCallbackHandler(node_name=node_name, llm=None)
    config["callbacks"] = filtered_callbacks + [metrics_callback]

    # Phase 2.1.2 - Debug logging for callback deduplication validation
    logger.debug(
        "config_enriched_with_node_metadata",
        node_name=node_name,
        has_other_metadata=len(config.get("metadata", {})) > 1,  # type: ignore[arg-type]
        callbacks_before_filter=len(existing_callbacks),
        callbacks_after_filter=len(filtered_callbacks),
        callbacks_final=len(config["callbacks"]),
        callback_types=[type(cb).__name__ for cb in config["callbacks"]],
        filtered_count=len(existing_callbacks) - len(filtered_callbacks),
        msg=(
            f"Callback deduplication: {len(existing_callbacks)} -> {len(filtered_callbacks)} "
            f"(removed {len(existing_callbacks) - len(filtered_callbacks)}) + 1 new MetricsCallback = "
            f"{len(config['callbacks'])} total"
        ),
    )

    return config


def create_instrumented_config_from_node(
    llm_type: str,
    state: dict[str, Any] | None = None,
    base_config: RunnableConfig | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RunnableConfig:
    """
    Create instrumented RunnableConfig for LLM invocation from node context.

    This is the recommended helper for LangGraph nodes that need to invoke LLM
    with automatic Langfuse observability. It extracts session/user from state
    and creates a fully instrumented config.

    Best Practice Pattern (2025):
        ```python
        def my_node(state: State, config: RunnableConfig) -> dict:
            # Create instrumented config from state
            llm_config = create_instrumented_config_from_node(
                llm_type="router",
                state=state,
                base_config=config  # Preserve existing config (recursion_limit, etc.)
            )

            # Invoke with instrumented config
            llm = get_llm("router")
            response = await llm.ainvoke(messages, config=llm_config)
            return {FIELD_RESULT: response}
        ```

    Args:
        llm_type: LLM type identifier (e.g., "router", "planner")
        state: LangGraph state dict (for session_id/user_id extraction)
        base_config: Existing RunnableConfig to preserve (e.g., recursion_limit)
        session_id: Override session_id (if not in state)
        user_id: Override user_id (if not in state)
        tags: Additional tags for filtering
        metadata: Additional metadata

    Returns:
        Instrumented RunnableConfig ready for llm.invoke()

    Example - From LangGraph node:
        >>> def router_node(state: State, config: RunnableConfig) -> dict:
        ...     llm_config = create_instrumented_config_from_node(
        ...         llm_type="router",
        ...         state=state,
        ...         base_config=config,
        ...         metadata={"intention": state.get("intention")}
        ...     )
        ...     llm = get_llm("router")
        ...     response = await llm.ainvoke(messages, config=llm_config)
        ...     return {"next": "planner"}

    Example - With explicit session/user:
        >>> llm_config = create_instrumented_config_from_node(
        ...     llm_type="planner",
        ...     session_id="conv_123",
        ...     user_id="user_456",
        ...     tags=["complex_query"],
        ...     base_config=config
        ... )
    """
    # Extract session/user from state if not provided
    extracted_session_id = session_id
    extracted_user_id = user_id

    if state and (not session_id or not user_id):
        state_session_id, state_user_id = extract_session_user_from_state(state)
        extracted_session_id = extracted_session_id or state_session_id
        extracted_user_id = extracted_user_id or state_user_id

    # If still not available, try to extract from base_config.configurable
    if base_config:
        configurable = base_config.get("configurable", {})
        if not extracted_session_id:
            # Note: Using string literal to avoid circular imports (infrastructure shouldn't depend on agents.constants)
            extracted_session_id = configurable.get("thread_id") or configurable.get("session_id")
        if not extracted_user_id:
            extracted_user_id = configurable.get(FIELD_USER_ID)

    # Build enriched metadata
    enriched_metadata = {
        "node_invocation": True,
        **(metadata or {}),
    }

    # Create instrumented config
    instrumented_config = create_instrumented_config(
        llm_type=llm_type,
        session_id=extracted_session_id,
        user_id=str(extracted_user_id) if extracted_user_id else None,
        tags=tags,
        metadata=enriched_metadata,
        trace_name=f"{llm_type}_node_call",
        base_config=base_config,
    )

    # **Phase 2.1 - Token Tracking Alignment Fix**
    # Extract node_name from base_config (set by LangGraph automatically)
    node_name = None
    if base_config:
        node_name = base_config.get(FIELD_METADATA, {}).get("langgraph_node")

    # If no node_name in config, use llm_type as fallback
    # This ensures we always have a meaningful node_name for metrics
    if not node_name:
        node_name = llm_type

    # Enrich config to ensure metadata["langgraph_node"] propagates to callbacks
    # This is CRITICAL for token tracking - without it, callbacks receive empty metadata
    instrumented_config = enrich_config_with_node_metadata(instrumented_config, node_name)

    logger.debug(
        "instrumented_config_created_from_node",
        llm_type=llm_type,
        node_name=node_name,
        node_name_source=(
            "base_config"
            if base_config and base_config.get(FIELD_METADATA, {}).get("langgraph_node")
            else "llm_type_fallback"
        ),
        session_id=extracted_session_id,
        user_id=extracted_user_id,
        has_base_config=base_config is not None,
    )

    return instrumented_config


async def invoke_with_instrumentation(
    llm: BaseChatModel,
    llm_type: str,
    messages: Any,
    state: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    **invoke_kwargs: Any,
) -> Any:
    """
    Invoke LLM with automatic Langfuse instrumentation (async wrapper).

    This helper wraps llm.ainvoke() and automatically creates an instrumented
    config with Langfuse callbacks. Useful for existing code that doesn't
    manually create configs.

    Best Practice:
        Prefer create_instrumented_config_from_node() + direct llm.ainvoke()
        for better control. Use this helper only for quick retrofitting.

    Args:
        llm: LLM instance to invoke
        llm_type: LLM type identifier
        messages: Messages to send to LLM
        state: LangGraph state (for session/user extraction)
        config: Base RunnableConfig to preserve
        session_id: Override session_id
        user_id: Override user_id
        **invoke_kwargs: Additional kwargs for llm.ainvoke()

    Returns:
        LLM response (same as llm.ainvoke())

    Example:
        >>> # Existing code
        >>> llm = get_llm("router")
        >>> response = await llm.ainvoke(messages)

        >>> # Add instrumentation without refactoring
        >>> response = await invoke_with_instrumentation(
        ...     llm=llm,
        ...     llm_type="router",
        ...     messages=messages,
        ...     state=state,
        ...     config=config
        ... )
    """
    # === USAGE LIMIT GUARD (Layer 2: centralized LLM-level enforcement) ===
    if getattr(settings, "usage_limits_enabled", False):
        resolved_uid = _resolve_user_id_for_limit_check(user_id, state, config)
        if resolved_uid:
            from src.domains.usage_limits.service import UsageLimitService

            _limit_check = await UsageLimitService.check_user_allowed(resolved_uid)
            if not _limit_check.allowed:
                from src.core.exceptions import raise_usage_limit_exceeded
                from src.infrastructure.observability.metrics_usage_limits import (
                    usage_limit_enforcement_total,
                )

                usage_limit_enforcement_total.labels(
                    layer="llm_invoke", limit_type=_limit_check.exceeded_limit or "unknown"
                ).inc()
                logger.warning(
                    "llm_invocation_blocked_usage_limit",
                    user_id=str(resolved_uid),
                    llm_type=llm_type,
                    limit=_limit_check.exceeded_limit,
                )
                raise_usage_limit_exceeded(
                    _limit_check.exceeded_limit,
                    _limit_check.blocked_reason,
                )
    # === END USAGE LIMIT GUARD ===

    # Create instrumented config
    instrumented_config = create_instrumented_config_from_node(
        llm_type=llm_type,
        state=state,
        base_config=config,
        session_id=session_id,
        user_id=user_id,
    )

    # Merge invoke_kwargs with instrumented config
    final_kwargs = {**invoke_kwargs, "config": instrumented_config}

    # Invoke LLM with instrumented config
    return await llm.ainvoke(messages, **final_kwargs)


def invoke_sync_with_instrumentation(
    llm: BaseChatModel,
    llm_type: str,
    messages: Any,
    state: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    **invoke_kwargs: Any,
) -> Any:
    """
    Invoke LLM with automatic Langfuse instrumentation (sync wrapper).

    Synchronous version of invoke_with_instrumentation() for sync code.

    Args:
        llm: LLM instance to invoke
        llm_type: LLM type identifier
        messages: Messages to send to LLM
        state: LangGraph state (for session/user extraction)
        config: Base RunnableConfig to preserve
        session_id: Override session_id
        user_id: Override user_id
        **invoke_kwargs: Additional kwargs for llm.invoke()

    Returns:
        LLM response (same as llm.invoke())

    Example:
        >>> response = invoke_sync_with_instrumentation(
        ...     llm=llm,
        ...     llm_type="router",
        ...     messages=messages,
        ...     state=state
        ... )
    """
    # Create instrumented config
    instrumented_config = create_instrumented_config_from_node(
        llm_type=llm_type,
        state=state,
        base_config=config,
        session_id=session_id,
        user_id=user_id,
    )

    # Merge invoke_kwargs with instrumented config
    final_kwargs = {**invoke_kwargs, "config": instrumented_config}

    # Invoke LLM with instrumented config
    return llm.invoke(messages, **final_kwargs)
