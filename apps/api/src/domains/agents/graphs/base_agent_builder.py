"""
Base Agent Builder - Generic Template for LangGraph Agents.

Provides a reusable factory function for building LangChain v1.0 agents with
standardized configuration, middleware, and best practices.

This template enables rapid creation of new agents (Gmail, Calendar, Tasks, etc.)
with consistent architecture and minimal boilerplate.

Usage Example (Gmail Agent):
    >>> config = AgentConfig(
    ...     agent_name="emails_agent",
    ...     tools=[send_email_tool, search_email_tool, ...],
    ...     system_prompt=EMAILS_AGENT_SYSTEM_PROMPT.format(datetime=..., context=...),
    ...     # llm_config: omit to use centralized config (LLM_DEFAULTS + DB overrides)
    ...     # or override: llm_config=get_llm_config_for_agent(settings, "emails_agent")
    ...     enable_hitl=True,  # Tools with manifest.permissions.hitl_required=True need approval
    ... )
    >>> emails_agent = build_generic_agent(config)

Best Practices Applied:
    - LangChain v1.0 create_agent() API
    - HumanInTheLoopMiddleware for tool approval
    - ToolRuntime pattern for config/store access
    - Pre-model hook for message history management
    - Automatic metrics and logging
    - Generic, extensible, maintainable
"""

from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import BaseTool

# Phase 8: HumanInTheLoopMiddleware import removed (tool-level HITL deprecated)
from typing_extensions import TypedDict

from src.core.config import settings
from src.core.field_names import FIELD_AGENT_NAME, FIELD_METADATA, FIELD_STATUS
from src.infrastructure.llm import get_llm
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class LLMConfig(TypedDict, total=False):
    """
    LLM configuration for agent.

    Attributes:
        model: Model identifier (e.g., "gpt-4.1-mini", "gpt-4.1-mini-mini").
        temperature: Sampling temperature (0.0-2.0).
        max_tokens: Maximum tokens for output.
        top_p: Nucleus sampling parameter (0.0-1.0).
        frequency_penalty: Frequency penalty (-2.0 to 2.0).
        presence_penalty: Presence penalty (-2.0 to 2.0).
    """

    model: str
    temperature: float
    max_tokens: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float


class AgentConfig(TypedDict, total=False):
    """
    Complete configuration for building a generic agent.

    Required Fields:
        agent_name: Unique identifier for agent (e.g., "contacts_agent", "emails_agent").
        tools: List of LangChain tools (functions decorated with @tool).
        system_prompt: Formatted system prompt string (static, no variables).
        llm_config: LLM configuration dictionary (see LLMConfig).

    Optional Fields:
        enable_hitl: Enable Human-in-the-Loop tool approval (default: True, always enabled).
        pre_model_hook: Custom pre-model hook for message filtering (default: auto-created).
        max_history_messages: Max messages in agent history (default: settings.agent_history_keep_last).
        max_history_tokens: Max tokens in agent history (default: settings.max_tokens_history).
        metadata: Additional metadata for logging/tracing.

    Note:
        HITL tool approval requirements are now determined by tool manifests
        (manifest.permissions.hitl_required), not by configuration patterns.
        The enable_hitl parameter acts as a global kill switch only.

    Example:
        >>> config = AgentConfig(
        ...     agent_name="contacts_agent",
        ...     tools=[search_contacts_tool, list_contacts_tool, get_contact_details_tool],
        ...     system_prompt=CONTACTS_AGENT_SYSTEM_PROMPT.format(datetime=..., context=...),
        ...     llm_config=LLMConfig(
        ...         model="gpt-4.1-mini-mini",
        ...         temperature=0.5,
        ...         max_tokens=10000,
        ...     ),
        ...     enable_hitl=True,  # Tools with manifest.permissions.hitl_required=True need approval
        ... )
    """

    # Required
    agent_name: str
    tools: list[BaseTool]
    system_prompt: str
    llm_config: LLMConfig

    # Optional
    enable_hitl: bool
    pre_model_hook: Callable[[dict], dict] | None
    max_history_messages: int
    max_history_tokens: int
    metadata: dict[str, Any]
    datetime_generator: Callable[[], str] | None  # For dynamic timestamp injection


def build_generic_agent(config: AgentConfig) -> Any:
    """
    Build a LangChain v1.0 agent with standardized configuration and best practices.

    This factory function creates agents with:
    - Automatic HITL middleware (if enabled)
    - Pre-model hook for message history management
    - ToolRuntime pattern for config/store access
    - Consistent logging and metrics
    - Generic, reusable architecture

    Architecture (LangChain v1.0 ReAct):
        Agent Loop (internal to create_agent):
        1. LLM generates tool_calls
        2. HumanInTheLoopMiddleware intercepts (if tool matches pattern)
        3. Middleware emits interrupt() → pauses graph
        4. User approves via Command(resume={"decisions": [...]})
        5. Middleware processes decision (approve/edit/reject)
        6. Tools execute (if approved)
        7. Agent receives results and continues

    Args:
        config: AgentConfig dictionary with all agent configuration.

    Returns:
        Compiled LangChain agent ready to be wrapped in a parent graph node.

    Raises:
        ValueError: If required config fields are missing.
        TypeError: If tools list is empty or invalid.

    Example (Contacts Agent):
        >>> config = AgentConfig(
        ...     agent_name="contacts_agent",
        ...     tools=[search_contacts_tool, list_contacts_tool, get_contact_details_tool,
        ...            resolve_reference, set_current_item, get_context_state, list_active_domains],
        ...     system_prompt=CONTACTS_AGENT_SYSTEM_PROMPT.format(
        ...         current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ...         context_instructions="...",
        ...     ),
        ...     # llm_config: omit to use centralized config (LLM_DEFAULTS + DB overrides)
        ...     # or override: llm_config=get_llm_config_for_agent(settings, "contacts_agent")
        ...     enable_hitl=True,  # Always enabled
        ... )
        >>> contacts_agent = build_generic_agent(config)

    Example (Gmail Agent):
        >>> config = AgentConfig(
        ...     agent_name="emails_agent",
        ...     tools=[send_email_tool, search_email_tool, ...],
        ...     system_prompt=EMAILS_AGENT_SYSTEM_PROMPT.format(...),
        ...     # llm_config: omit to use centralized config (LLM_DEFAULTS + DB overrides)
        ...     enable_hitl=True,
        ... )
        >>> emails_agent = build_generic_agent(config)

    Usage in graph.py:
        >>> # In graph.py - wrap agent in node function
        >>> contacts_agent_runnable = build_generic_agent(contacts_config)
        >>>
        >>> async def contacts_agent_node(state, config):
        ...     result = await contacts_agent_runnable.ainvoke(state, config)
        ...     # Store agent results for response_node
        ...     return {"messages": result["messages"], "agent_results": {...}}
        >>>
        >>> graph.add_node("contacts_agent", contacts_agent_node)

    Notes:
        - Store and checkpointer are propagated from parent graph.compile(store=..., checkpointer=...)
        - Agent is a subgraph that can be wrapped in a function node (recommended pattern)
        - HITL interrupts bubble to parent graph automatically
        - Tools use ToolRuntime for unified config/store access
    """
    # Validate required fields
    required_fields = ["agent_name", "tools", "system_prompt", "llm_config"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required config field: {field}")

    agent_name = config["agent_name"]
    tools = config["tools"]
    system_prompt_template = config["system_prompt"]
    llm_config = config["llm_config"]

    # Optional fields (HITL is always enabled)
    enable_hitl = config.get("enable_hitl", True)

    # Validate tools
    if not tools or not isinstance(tools, list):
        raise TypeError(f"Agent '{agent_name}': tools must be a non-empty list")

    logger.info(
        "building_generic_agent",
        agent_name=agent_name,
        tools_count=len(tools),
        llm_model=llm_config.get("model"),
    )

    # Get LLM with config override from AgentConfig
    # Map agent_name to LLMType for factory
    # New unified agent names (domain_agent pattern) - 2026-01 refactoring
    llm_type_map = {
        # New unified names (domain_agent pattern)
        "contact_agent": "contact_agent",
        "email_agent": "email_agent",
        "event_agent": "event_agent",
        "file_agent": "file_agent",
        "task_agent": "task_agent",
        "query_agent": "query_agent",
        "weather_agent": "weather_agent",
        "wikipedia_agent": "wikipedia_agent",
        "perplexity_agent": "perplexity_agent",
        "place_agent": "place_agent",
        "route_agent": "route_agent",
        "brave_agent": "brave_agent",
        "web_search_agent": "web_search_agent",
        "web_fetch_agent": "web_fetch_agent",
        "browser_agent": "browser_agent",
        # Backward compatibility aliases (deprecated - will be removed in v4)
        "contacts_agent": "contact_agent",
        "emails_agent": "email_agent",
        "calendar_agent": "event_agent",
        "drive_agent": "file_agent",
        "tasks_agent": "task_agent",
        "places_agent": "place_agent",
        "routes_agent": "route_agent",
    }
    llm_type = llm_type_map.get(agent_name, "contact_agent")

    # Pass llm_config to factory for override support
    # This allows per-agent customization of model, temperature, max_tokens, etc.
    llm = get_llm(llm_type, config_override=llm_config)

    logger.debug(
        "llm_created_with_config",
        agent_name=agent_name,
        llm_type=llm_type,
        model=llm_config.get("model"),
        temperature=llm_config.get("temperature"),
        has_config_override=bool(llm_config),
    )

    # P0 Migration - Chantier 7: LangChain Middleware Stack
    # Phase 8: HITL moved to plan-level (approval_gate_node) - tool-level HITL removed
    # Now using LangChain middleware for retry and summarization
    #
    # Middleware order (applied to each LLM call):
    # 1. ModelRetryMiddleware - Retry on transient failures
    # 2. SummarizationMiddleware - Context compression approaching limits
    # 3. MessageHistoryMiddleware - Message filtering for LLM input
    from src.infrastructure.llm.middleware_config import create_agent_middleware_stack

    middleware = create_agent_middleware_stack(agent_name)

    logger.info(
        "agent_middleware_configured",
        agent_name=agent_name,
        middleware_count=len(middleware),
        note="P0 Migration: LangChain middleware (Retry, Summarization) + MessageHistory",
    )

    # Configure Message History Middleware (LangChain v1.0 pattern)
    # Replaces legacy pre_model_hook with v1.0-compliant middleware
    # This filters messages for LLM input while preserving full state for tools
    max_history_messages = config.get("max_history_messages", settings.agent_history_keep_last)
    max_history_tokens = config.get("max_history_tokens", settings.max_tokens_history)

    from src.domains.agents.middleware import MessageHistoryMiddleware

    history_middleware = MessageHistoryMiddleware(
        keep_last_n=max_history_messages,
        max_tokens=max_history_tokens,
    )
    middleware.append(history_middleware)

    logger.debug(
        "message_history_middleware_configured",
        agent_name=agent_name,
        max_history_messages=max_history_messages,
        max_history_tokens=max_history_tokens,
    )

    # Apply dynamic datetime injection if generator provided
    # This ensures timestamps are fresh on each invocation, not frozen at build time
    datetime_generator = config.get("datetime_generator")
    if datetime_generator and "{current_datetime}" in system_prompt_template:
        # Inject fresh datetime at build time using safe replacement
        # IMPORTANT: Use replace() instead of format() to avoid KeyError
        # on literal braces in prompt (e.g., JSON examples like {{"success": true}})
        # NOTE: For truly per-invocation timestamps, we would need custom middleware
        # This POC injects at agent build time (better than app startup, good enough for MVP)
        system_prompt = system_prompt_template.replace("{current_datetime}", datetime_generator())
        logger.info(
            "dynamic_datetime_injected",
            agent_name=agent_name,
            generator_name=(
                datetime_generator.__name__ if hasattr(datetime_generator, "__name__") else "lambda"
            ),
            datetime_value=datetime_generator(),
        )
    else:
        system_prompt = system_prompt_template
        if datetime_generator:
            logger.warning(
                "datetime_generator_provided_but_no_placeholder",
                agent_name=agent_name,
                prompt_preview=system_prompt_template[:100],
            )

    # Create LangChain v1.0 agent with create_agent
    # This is the official v1.0 API for building ReAct agents
    #
    # CRITICAL (Phase 5 - HITL Fix):
    # Pass checkpointer and store to create_agent() to enable HITL middleware
    # interrupts. Without checkpointer, middleware cannot persist interrupt state
    # and interrupts are lost/ignored.
    from src.domains.agents.registry import get_global_registry

    registry = get_global_registry()
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware if middleware else None,
        checkpointer=registry.get_checkpointer(),  # Enable HITL interrupt persistence
        store=registry.get_store(),  # Enable tool context management
    )

    logger.info(
        "generic_agent_built_successfully",
        agent_name=agent_name,
        tools_count=len(tools),
        llm_model=llm_config.get("model"),
        hitl_enabled=enable_hitl,
        middleware_count=len(middleware),
    )

    return agent


def create_agent_wrapper_node(
    agent_runnable: Any,
    agent_name: str,
    agent_constant: str,
) -> Any:
    """
    Generic agent wrapper factory with callback propagation.

    Phase 6 - LLM Observability: Creates wrapper nodes that ensure
    callbacks (Metrics, Langfuse, TokenTracking) propagate from parent
    graph to agent subgraphs for complete instrumentation coverage.

    CRITICAL: Solves RC3 (Generic agents callbacks not propagated).
    Without this wrapper, agent subgraphs created via create_agent()
    are isolated and don't receive parent callbacks, causing:
    - Missing Langfuse traces (54% tokens lost)
    - Incomplete token tracking in database
    - No Prometheus metrics for agent LLM calls

    Args:
        agent_runnable: Compiled agent graph from build_generic_agent()
        agent_name: Human-readable name for logging (e.g., "contacts_agent")
        agent_constant: Constant identifier from constants.py (e.g., AGENT_CONTACT)

    Returns:
        Async node function ready for graph.add_node()

    Architecture:
        Parent Graph Config:
            callbacks: [MetricsCallback, LangfuseCallback, TokenTrackingCallback]
            metadata: {langfuse_session_id, langfuse_user_id, ...}

        → Agent Wrapper (this function)

        → Agent Subgraph Invocation (with merged config)
            callbacks: [parent callbacks]  ← PROPAGATED
            metadata: {parent metadata + subgraph tag}  ← MERGED

        → LLM Calls inside agent
            → Callbacks triggered ✅
            → Metrics emitted (Prometheus, DB, Langfuse) ✅

    Usage:
        >>> # Build agent
        >>> contacts_agent_runnable = build_contacts_agent()
        >>>
        >>> # Create wrapper with callback propagation
        >>> contacts_agent_node = create_agent_wrapper_node(
        ...     contacts_agent_runnable,
        ...     "contacts_agent",
        ...     AGENT_CONTACT
        ... )
        >>>
        >>> # Add to graph
        >>> graph.add_node("contacts_agent", contacts_agent_node)

    LangGraph v1.0 Compliance:
        - Subgraphs are isolated by design (checkpointer/store separate)
        - Callbacks must be explicitly propagated via config merge
        - Metadata must be preserved to maintain Langfuse trace hierarchy

    References:
        - RC3 Root Cause Analysis (docs/TOKEN_ALIGNMENT_ANALYSIS.md)
        - ADR-015: Token Tracking Architecture V2
        - LangGraph v1.0 Subgraph Pattern: https://langchain-ai.github.io/langgraph/how-tos/subgraph/
    """
    import structlog
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.constants import (
        NODE_RESPONSE,
        STATE_KEY_AGENT_RESULTS,
        STATE_KEY_CURRENT_TURN_ID,
        STATE_KEY_MESSAGES,
        make_agent_result_key,
    )
    from src.domains.agents.models import MessagesState
    from src.domains.agents.utils.state_tracking import track_state_updates
    from src.infrastructure.observability.metrics_langgraph import (
        langgraph_node_transitions_total,
        langgraph_subgraph_duration_seconds,
        langgraph_subgraph_invocations_total,
        langgraph_subgraph_tool_calls_total,
    )

    logger = structlog.get_logger(__name__)

    async def agent_wrapper_node(state: MessagesState, config: RunnableConfig) -> dict:
        """
        Agent wrapper with deep callback + metadata propagation.

        Ensures:
        1. Parent callbacks reach agent subgraph LLM calls
        2. Parent metadata (Langfuse trace_id) preserved
        3. Agent results stored in state
        4. Complete instrumentation (DB, Prometheus, Langfuse)
        """
        import time

        # PHASE 2.5 - P4: Track subgraph invocation start time
        start_time = time.perf_counter()

        # Extract parent callbacks and metadata
        parent_callbacks = config.get("callbacks", []) if config else []
        parent_metadata = config.get(FIELD_METADATA, {}) if config else {}

        try:
            if parent_callbacks or parent_metadata:
                # 🔥 DEEP MERGE: Preserve existing config + propagate parent context
                # CRITICAL: Do NOT overwrite subgraph config, append callbacks and merge metadata
                merged_config = {
                    **config,  # Base config (recursion_limit, configurable, etc.)
                    "callbacks": parent_callbacks,  # Propagate to subgraph
                    FIELD_METADATA: {
                        **config.get(FIELD_METADATA, {}),  # Existing subgraph metadata (if any)
                        **parent_metadata,  # Parent metadata (Langfuse trace_id, session_id, user_id)
                        # 🔥 TAG: Identifier subgraph for Langfuse filtering
                        "subgraph": agent_constant,
                        "parent_node": "main_graph",
                        # Override internal node name ("agent") with domain agent name
                        # so TokenTrackingCallback records under the correct name
                        # in the debug panel (same pattern as ReactSubAgentRunner)
                        "node_name_override": agent_constant,
                    },
                }

                # Invoke agent with merged config
                # LangChain runtime will merge parent callbacks with subgraph's own callbacks (if any)
                result = await agent_runnable.ainvoke(state, merged_config)

                logger.debug(
                    "agent_wrapper_executed_with_callbacks",
                    agent=agent_constant,
                    callbacks_count=len(parent_callbacks),
                    metadata_keys=list(parent_metadata.keys()),
                    subgraph_tagged=True,
                )
            else:
                # No callbacks to propagate (shouldn't happen in production)
                result = await agent_runnable.ainvoke(state, config)

                logger.warning(
                    "agent_wrapper_no_callbacks",
                    agent=agent_constant,
                    message="No parent callbacks found - metrics may be incomplete",
                )

            # PHASE 2.5 - P4: Track successful subgraph invocation
            duration = time.perf_counter() - start_time
            langgraph_subgraph_invocations_total.labels(
                agent_name=agent_constant,
                status="success",
            ).inc()
            langgraph_subgraph_duration_seconds.labels(
                agent_name=agent_constant,
            ).observe(duration)

            # PHASE 2.5 - P4: Track tool calls from result messages
            # Count ToolMessage occurrences in the result (indicates ReAct tool invocations)
            from langchain_core.messages import ToolMessage

            tool_calls = 0
            for msg in result.get(STATE_KEY_MESSAGES, []):
                if isinstance(msg, ToolMessage):
                    tool_calls += 1
                    # Extract tool name from ToolMessage.name if available
                    tool_name = getattr(msg, "name", "unknown")
                    langgraph_subgraph_tool_calls_total.labels(
                        agent_name=agent_constant,
                        tool_name=tool_name,
                    ).inc()

            logger.debug(
                "subgraph_execution_tracked",
                agent=agent_constant,
                duration_seconds=duration,
                tool_calls=tool_calls,
                status="success",
            )

            # Record domain agent LLM token usage in TrackingContext for debug panel.
            # Isolated subgraphs (with their own checkpointer) do NOT propagate parent
            # callbacks, so TokenTrackingCallback never fires for domain agent LLM calls.
            # We extract usage_metadata from result AIMessages and record explicitly.
            from langchain_core.messages import AIMessage

            from src.core.context import current_tracker

            tracker = current_tracker.get()
            if tracker:
                duration_ms = duration * 1000
                for msg in result.get(STATE_KEY_MESSAGES, []):
                    if isinstance(msg, AIMessage) and getattr(msg, "usage_metadata", None):
                        usage = msg.usage_metadata
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)
                        # Extract cached tokens from input_token_details
                        input_details = usage.get("input_token_details", {})
                        cached_tokens = (
                            (input_details.get("cache_read", 0) or 0) if input_details else 0
                        )
                        # Subtract cached from input (same logic as TokenExtractor)
                        net_input = input_tokens - cached_tokens
                        # Extract model name from response_metadata
                        model_name = "unknown"
                        resp_meta = getattr(msg, "response_metadata", None)
                        if resp_meta:
                            model_name = resp_meta.get("model_name", "unknown")

                        await tracker.record_node_tokens(
                            node_name=agent_constant,
                            model_name=model_name,
                            prompt_tokens=net_input,
                            completion_tokens=output_tokens,
                            cached_tokens=cached_tokens,
                            duration_ms=duration_ms,
                        )
                        logger.info(
                            "domain_agent_tokens_recorded",
                            agent=agent_constant,
                            model=model_name,
                            input_tokens=net_input,
                            output_tokens=output_tokens,
                            cached_tokens=cached_tokens,
                            duration_ms=round(duration_ms, 1),
                        )
                        # Use full duration for first call only, zero for subsequent
                        # (duration covers the entire agent execution, not individual calls)
                        duration_ms = 0.0

        except Exception as e:
            # PHASE 2.5 - P4: Track failed subgraph invocation
            duration = time.perf_counter() - start_time
            langgraph_subgraph_invocations_total.labels(
                agent_name=agent_constant,
                status="error",
            ).inc()
            langgraph_subgraph_duration_seconds.labels(
                agent_name=agent_constant,
            ).observe(duration)

            logger.error(
                "subgraph_execution_failed",
                agent=agent_constant,
                duration_seconds=duration,
                error=str(e),
            )

            # Re-raise to let graph handle error
            raise

        # Store agent results for response_node synthesis
        agent_results = state.get(STATE_KEY_AGENT_RESULTS, {})
        turn_id = state.get(STATE_KEY_CURRENT_TURN_ID, 0)
        composite_key = make_agent_result_key(turn_id, agent_constant)

        agent_results[composite_key] = {
            FIELD_AGENT_NAME: agent_constant,
            FIELD_STATUS: "success",
            "data": (
                result.get(STATE_KEY_MESSAGES, [])[-1].content
                if result.get(STATE_KEY_MESSAGES)
                else None
            ),
        }

        # PHASE 2.5 - LangGraph Observability: Track static edge transition
        # Agent wrappers always transition to NODE_RESPONSE (see graph.py add_edge())
        langgraph_node_transitions_total.labels(
            from_node=agent_constant,
            to_node=NODE_RESPONSE,
        ).inc()

        state_update = {
            STATE_KEY_MESSAGES: result.get(STATE_KEY_MESSAGES, []),
            STATE_KEY_AGENT_RESULTS: agent_results,
        }

        # FIX: Propagate registry updates from subgraph to parent state
        # This ensures StandardToolOutput registry items are persisted
        if "registry" in result:
            state_update["registry"] = result["registry"]
            logger.debug(
                "agent_wrapper_registry_propagated",
                agent=agent_constant,
                items_count=len(result["registry"]),
            )

        # PHASE 2.5 - LangGraph Observability: Track state updates
        track_state_updates(state, state_update, agent_constant, agent_constant)

        return state_update

    # Set function name for better stack traces and debugging
    agent_wrapper_node.__name__ = f"{agent_name}_wrapper_node"

    return agent_wrapper_node


def create_agent_config_from_settings(
    agent_name: str,
    tools: list[BaseTool],
    system_prompt: str,
    enable_hitl: bool | None = None,
    datetime_generator: Callable[[], str] | None = None,
) -> AgentConfig:
    """
    Create AgentConfig for a specific agent type.

    Reads LLM configuration from LLM_DEFAULTS (code constants) + DB overrides (cache),
    NOT from .env settings. The `settings` parameter is no longer used for LLM config.

    Args:
        agent_name: Agent identifier (e.g., "contacts_agent", "weather_agent").
        tools: List of LangChain tools for this agent.
        system_prompt: Formatted system prompt string (can contain {current_datetime} placeholder).
        enable_hitl: Override HITL enabled (default: True, always enabled).
        datetime_generator: Optional callable that returns formatted datetime string.
                          If provided and system_prompt contains {current_datetime},
                          the timestamp will be injected at agent build time.

    Returns:
        AgentConfig dictionary ready for build_generic_agent().

    Raises:
        ValueError: If agent_name is not recognized in LLM_DEFAULTS.

    Note:
        HITL tool approval requirements are now determined by tool manifests
        (manifest.permissions.hitl_required), not by configuration patterns.
        The enable_hitl parameter acts as a global kill switch only.

    Example:
        >>> config = create_agent_config_from_settings(
        ...     agent_name="contacts_agent",
        ...     tools=[search_contacts_tool, list_contacts_tool],
        ...     system_prompt=CONTACTS_AGENT_SYSTEM_PROMPT.format(...),
        ...     datetime_generator=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ... )
        >>> agent = build_generic_agent(config)
    """
    from src.core.llm_config_helper import get_llm_config_for_agent

    # Resolve effective config: LLM_DEFAULTS (code) → DB override (cache)
    agent_config = get_llm_config_for_agent(settings, agent_name)

    llm_config = LLMConfig(
        model=agent_config.model,
        temperature=agent_config.temperature,
        max_tokens=agent_config.max_tokens,
        top_p=agent_config.top_p,
        frequency_penalty=agent_config.frequency_penalty,
        presence_penalty=agent_config.presence_penalty,
    )

    config = AgentConfig(
        agent_name=agent_name,
        tools=tools,
        system_prompt=system_prompt,
        llm_config=llm_config,
        enable_hitl=enable_hitl if enable_hitl is not None else True,  # HITL always enabled
        datetime_generator=datetime_generator,
    )

    return config


__all__ = [
    "AgentConfig",
    "LLMConfig",
    "build_generic_agent",
    "create_agent_config_from_settings",
    "create_agent_wrapper_node",  # Phase 6: Generic wrapper for callback propagation
]
