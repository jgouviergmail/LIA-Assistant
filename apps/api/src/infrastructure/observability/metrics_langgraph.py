"""
Prometheus metrics for LangGraph framework-level observability.

Implements comprehensive LangGraph-specific metrics beyond node-level tracking:
- Graph execution lifecycle (start, completion, errors)
- Node transitions and conditional routing decisions
- State management (updates, payload sizes)
- SubGraph invocations (contacts_agent, emails_agent)
- Streaming event distribution

Complements existing metrics_agents.py (node-level) with framework-level insights.

Phase: PHASE 2.5 - LangGraph Observability
Created: 2025-11-22
"""

from prometheus_client import Counter, Histogram

# ============================================================================
# GRAPH EXECUTION METRICS
# ============================================================================

langgraph_graph_executions_total = Counter(
    "langgraph_graph_executions_total",
    "Total graph executions (conversations)",
    ["status"],  # status: success/error/interrupted
    # Track graph-level execution outcomes
    # Different from agent_node_executions_total (node-level)
)

langgraph_graph_duration_seconds = Histogram(
    "langgraph_graph_duration_seconds",
    "End-to-end graph execution duration (from entry to END)",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0],
    # Optimized for full conversation latency
    # Includes router + planner + agents + response
    # P50: ~2-5s simple queries, P95: ~10-30s complex multi-agent
)

langgraph_graph_errors_total = Counter(
    "langgraph_graph_errors_total",
    "Graph-level errors (unhandled exceptions)",
    ["error_type"],  # GraphRecursionError, GraphInterrupt, StateValidationError, etc.
    # Track framework-level failures
    # Different from agent_node_executions_total{status="error"} (node-level)
)

# ============================================================================
# NODE TRANSITION METRICS
# ============================================================================

langgraph_node_transitions_total = Counter(
    "langgraph_node_transitions_total",
    "Node transitions (edges traversed)",
    ["from_node", "to_node"],
    # Track graph flow: router → planner → task_orchestrator → response
    # Useful for identifying common paths and bottlenecks
    # Cardinality: ~20 node pairs (manageable)
)

langgraph_conditional_edges_total = Counter(
    "langgraph_conditional_edges_total",
    "Conditional edge routing decisions",
    ["edge_name", "decision"],
    # edge_name: route_from_router, route_from_planner, route_from_orchestrator
    # decision: planner/response/task_orchestrator/contacts_agent/emails_agent
    # Track routing logic: high confidence vs fallbacks
)

# ============================================================================
# STATE MANAGEMENT METRICS
# ============================================================================

langgraph_state_updates_total = Counter(
    "langgraph_state_updates_total",
    "State modifications by node",
    ["node_name", "key"],
    # key: messages/routing_history/agent_results/execution_plan
    # Track which nodes modify which state keys
    # Useful for debugging state pollution
)

langgraph_state_size_bytes = Histogram(
    "langgraph_state_size_bytes",
    "State payload size after node execution",
    ["node_name"],
    buckets=[1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000],
    # Track state growth: router adds routing_history, planner adds execution_plan
    # Alert if state >1MB (checkpoint save performance degradation)
)

# ============================================================================
# SUBGRAPH INVOCATION METRICS
# ============================================================================

langgraph_subgraph_invocations_total = Counter(
    "langgraph_subgraph_invocations_total",
    "SubGraph invocations (contacts_agent, emails_agent, etc.)",
    ["agent_name", "status"],  # agent_name: contacts_agent/emails_agent, status: success/error
    # Track specialized agent usage
    # Different from agent_node_executions_total (includes non-subgraph nodes like router)
)

langgraph_subgraph_duration_seconds = Histogram(
    "langgraph_subgraph_duration_seconds",
    "SubGraph execution duration (ReAct loop)",
    ["agent_name"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
    # Optimized for agent ReAct loops
    # contacts_agent: P50 ~3s (search), P95 ~15s (complex filters)
    # emails_agent: P50 ~5s (list), P95 ~20s (details fetching)
)

langgraph_subgraph_tool_calls_total = Counter(
    "langgraph_subgraph_tool_calls_total",
    "Tool calls within subgraphs (ReAct loop iterations)",
    ["agent_name", "tool_name"],
    # agent_name: contacts_agent/emails_agent
    # tool_name: google_contacts_search/google_gmail_list/etc.
    # Track ReAct loop behavior: average iterations before success
)

# ============================================================================
# STREAMING EVENT METRICS (SSE)
# ============================================================================

langgraph_streaming_chunks_total = Counter(
    "langgraph_streaming_chunks_total",
    "SSE streaming chunks emitted to client",
    ["event_type"],
    # event_type: STREAM_START/STREAM_TOKEN/STREAM_COMPLETE/STREAM_ERROR/STREAM_INTERRUPT
    # Track streaming lifecycle
    # Complement sse_streaming_duration_seconds (total duration)
)

langgraph_streaming_events_total = Counter(
    "langgraph_streaming_events_total",
    "LangGraph streaming events (astream_events)",
    ["event_name"],
    # event_name: on_chain_start/on_chain_end/on_llm_start/on_llm_stream/on_llm_end/on_tool_start/on_tool_end
    # Track LangChain event distribution
    # Useful for debugging streaming pipeline
)

# ============================================================================
# GRAPH RECURSION & INTERRUPTS
# ============================================================================

langgraph_graph_recursion_limit_exceeded_total = Counter(
    "langgraph_graph_recursion_limit_exceeded_total",
    "Graph executions that exceeded recursion limit",
    ["max_recursion_limit"],
    # Track infinite loop detection
    # max_recursion_limit: typically 25-50 (configured in service.py)
    # Alert if >0: indicates graph design issue or malicious input
)

langgraph_graph_interrupts_total = Counter(
    "langgraph_graph_interrupts_total",
    "Graph interrupts (HITL approval gates)",
    ["interrupt_type"],
    # interrupt_type: plan_approval/tool_approval
    # Track HITL intervention points
    # Complement hitl_plan_approval_requests_total (HITL-specific metrics)
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def extract_node_name_from_config(config: dict) -> str:
    """
    Extract node_name from LangGraph RunnableConfig.

    Args:
        config: RunnableConfig dict with metadata

    Returns:
        node_name or "unknown"

    Example:
        >>> config = {"configurable": {"node_name": "router"}}
        >>> extract_node_name_from_config(config)
        'router'
    """
    configurable = config.get("configurable", {})
    node_name = configurable.get("node_name", "unknown")
    # Type narrowing: ensure we always return str
    return str(node_name) if node_name != "unknown" else "unknown"


def calculate_state_size(state: dict) -> int:
    """
    Calculate approximate state size in bytes.

    Uses JSON serialization length as proxy for state size.
    Not exact (doesn't include Python object overhead) but consistent for tracking growth.

    Args:
        state: LangGraph MessagesState dict

    Returns:
        Approximate size in bytes

    Example:
        >>> state = {"messages": [HumanMessage(content="test")]}
        >>> size = calculate_state_size(state)
        >>> size > 0
        True
    """
    import json

    try:
        # Convert state to JSON (approximation)
        # MessagesState contains BaseMessage objects which aren't JSON serializable directly
        # We use str() as fallback for non-serializable objects
        json_str = json.dumps(state, default=str)
        return len(json_str.encode("utf-8"))
    except Exception:
        # Fallback: rough estimate based on dict keys
        return sum(len(str(k)) + len(str(v)) for k, v in state.items())
