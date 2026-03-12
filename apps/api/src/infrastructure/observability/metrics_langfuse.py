"""
Prometheus metrics for Langfuse advanced LLM observability - Phase 3.1.

Implements comprehensive Langfuse-specific metrics for Dashboard 14:
- Prompt versioning tracking (Phase 3.1.2)
- Evaluation scores distribution (Phase 3.1.3)
- A/B testing variant performance (Phase 3.1.4)
- Hierarchical trace depth (Phase 3.1.5.1)
- Tool call success/failure (Phase 3.1.5.2)
- Multi-agent handoff flow (Phase 3.1.5.3)

These metrics enable:
1. Prompt performance optimization (latency, success rate by version)
2. LLM output quality tracking (relevance, hallucination, correctness scores)
3. Data-driven A/B test decisions (variant comparison)
4. Conversation flow debugging (trace depth, agent transitions)
5. Tool integration reliability monitoring
6. Multi-agent orchestration optimization

Architecture:
- Prometheus Counter/Histogram/Gauge metrics
- Low cardinality labels (no session_id, conversation_id as labels)
- Integration with existing callback infrastructure
- Grafana Dashboard 14 visualization

Phase: 3.1.6.3 - Metrics Instrumentation
Created: 2025-11-23
"""

from prometheus_client import Counter, Histogram

# ============================================================================
# PHASE 3.1.2 - PROMPT VERSIONING METRICS
# ============================================================================

langfuse_prompt_version_usage = Counter(
    "langfuse_prompt_version_usage",
    "Prompt version usage from prompt_loader",
    ["prompt_id", "version"],
    # Track which prompt versions are actively used
    # Integration: src/domains/agents/prompts/prompt_loader.py::load_prompt()
    # Example labels:
    #   prompt_id: router_system_prompt, planner_system_prompt, response_system_prompt
    #   version: v1, v2, v3
    # Cardinality: ~15 prompts × 3 versions = 45 series (manageable)
)

# ============================================================================
# PHASE 3.1.3 - EVALUATION SCORES METRICS
# ============================================================================

langfuse_evaluation_score = Histogram(
    "langfuse_evaluation_score",
    "LLM output evaluation scores (relevance, hallucination, correctness)",
    ["metric_name"],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    # Track evaluation score distribution (0.0-1.0 range)
    # Integration: src/domains/agents/evaluation/pipeline.py::evaluate()
    # Dashboard: Panel 7 (Evaluation Scores Trends), Panel 8 (Score Distribution Heatmap)
    # Example labels:
    #   metric_name: relevance, hallucination, correctness, coherence, factuality
    # Cardinality: ~5 metric types = 5 series
    # Histogram generates 3 metrics:
    #   - langfuse_evaluation_score_bucket{metric_name, le}
    #   - langfuse_evaluation_score_sum{metric_name}
    #   - langfuse_evaluation_score_count{metric_name}
)

# ============================================================================
# PHASE 3.1.4 - A/B TESTING METRICS
# ============================================================================

langfuse_ab_test_variant = Counter(
    "langfuse_ab_test_variant",
    "A/B test variant assignments",
    ["experiment", "variant"],
    # Track variant distribution and assignment rate
    # Integration: src/domains/agents/ab_testing/variant_manager.py::assign_variant()
    # Dashboard: Panel 9 (Variant Distribution), Panel 10 (Variant Performance), Panel 11 (Variant Trends)
    # Example labels:
    #   experiment: prompt_optimization_001, model_comparison_gpt4_vs_claude
    #   variant: control, variant_a, variant_b
    # Cardinality: ~5 active experiments × 2-3 variants = 15 series
)

# ============================================================================
# PHASE 3.1.5.1 - SUBGRAPH TRACING METRICS
# ============================================================================

langfuse_trace_depth = Histogram(
    "langfuse_trace_depth",
    "Hierarchical trace depth distribution",
    ["depth_level"],
    buckets=[0, 1, 2, 3, 4, 5],
    # Track nesting levels: 0=root, 1=subgraph, 2+=nested
    # Integration: src/infrastructure/llm/instrumentation.py::create_instrumented_config()
    # Dashboard: Panel 12 (Trace Depth Distribution)
    # Example labels:
    #   depth_level: 0 (root graph), 1 (contacts_agent subgraph), 2 (nested subgraph)
    # Cardinality: ~6 depth levels = 6 series
    # Useful for detecting:
    #   - Infinite recursion (depth > 5)
    #   - Overly complex orchestration (high average depth)
)

langfuse_subgraph_invocations = Counter(
    "langfuse_subgraph_invocations",
    "Subgraph invocation rate by agent name",
    ["subgraph_name", "status"],
    # Track which agents are invoked and their success rate
    # Integration: src/infrastructure/llm/instrumentation.py::create_instrumented_config()
    # Dashboard: Panel 13 (Subgraph Invocation Rate)
    # Example labels:
    #   subgraph_name: contacts_agent, emails_agent, calendar_agent
    #   status: success, error
    # Cardinality: ~5 agents × 2 statuses = 10 series
    # Note: Complements langgraph_subgraph_invocations_total (framework-level)
    # This is Langfuse-specific with hierarchical trace linking
)

# ============================================================================
# PHASE 3.1.5.2 - TOOL CALL TRACING METRICS
# ============================================================================

langfuse_tool_calls = Counter(
    "langfuse_tool_calls",
    "Tool call executions by tool name and success status",
    ["tool_name", "success"],
    # Track tool usage and reliability
    # Integration: src/infrastructure/llm/tool_tracing.py::trace_tool_call()
    # Dashboard: Panel 14 (Tool Call Success Rate), Panel 15 (Tool Calls by Tool Name)
    # Example labels:
    #   tool_name: search_contacts, create_contact, send_email, search_emails, create_event
    #   success: true, false
    # Cardinality: ~10 tools × 2 statuses = 20 series
    # Success Rate Calculation (Panel 14):
    #   sum(langfuse_tool_calls{success="true"}) / sum(langfuse_tool_calls) * 100
)

# ============================================================================
# PHASE 3.1.5.3 - MULTI-AGENT HANDOFF METRICS
# ============================================================================

langfuse_agent_handoffs = Counter(
    "langfuse_agent_handoffs",
    "Agent handoff transitions (source → target)",
    ["source_agent", "target_agent"],
    # Track conversation flow between agents
    # Integration: src/infrastructure/llm/agent_handoff_tracing.py::trace_agent_handoff()
    # Dashboard: Panel 16 (Agent Handoff Flow - Table), Panel 18 (Conversation Flow Complexity)
    # Example labels:
    #   source_agent: router, planner, orchestrator, contacts_agent, emails_agent (or None for root)
    #   target_agent: router, planner, contacts_agent, emails_agent, response
    # Cardinality: ~7 agents × 7 agents = 49 series (but sparse matrix, ~15 actual transitions)
    # Use cases:
    #   - Visualize conversation flow patterns
    #   - Identify common routing paths
    #   - Detect unexpected transitions (debugging)
)

langfuse_handoff_duration_seconds = Histogram(
    "langfuse_handoff_duration_seconds",
    "Agent handoff duration (transition latency)",
    ["source_agent", "target_agent"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    # Track handoff performance by agent pair
    # Integration: src/infrastructure/llm/agent_handoff_tracing.py::trace_agent_handoff()
    # Dashboard: Panel 17 (Handoff Duration Heatmap)
    # Example labels: Same as langfuse_agent_handoffs
    # Cardinality: ~15 active transition pairs = 15 series
    # Optimization targets:
    #   - Fast handoffs: <1s (green)
    #   - Acceptable: 1-5s (yellow)
    #   - Slow handoffs: >5s (red) - investigate context transfer overhead
)

# ============================================================================
# METRICS SUMMARY
# ============================================================================

# Total Metrics: 7
# - 5 Counters: prompt_version_usage, ab_test_variant, subgraph_invocations, tool_calls, agent_handoffs
# - 2 Histograms: evaluation_score, trace_depth, handoff_duration_seconds
#
# Total Time Series (approx):
# - prompt_version_usage: 30
# - evaluation_score: 5 × 3 (histogram) = 15
# - ab_test_variant: 15
# - trace_depth: 6 × 3 (histogram) = 18
# - subgraph_invocations: 10
# - tool_calls: 20
# - agent_handoffs: 15
# - handoff_duration_seconds: 15 × 3 (histogram) = 45
# Total: ~173 time series (acceptable for Prometheus)
#
# Grafana Dashboard 14 Coverage:
# - 24 panels total
# - 10 panels use existing metrics (llm_calls_total, llm_cost_total, etc.)
# - 14 panels use new metrics from this module
#
# Integration Points (implemented):
# 1. src/infrastructure/llm/tool_tracing.py - langfuse_tool_calls.labels(...).inc()
# 2. src/infrastructure/llm/agent_handoff_tracing.py - langfuse_agent_handoffs/handoff_duration_seconds
#
# Future integration points (not yet implemented):
# - langfuse_prompt_version_usage: prompt version tracking
# - langfuse_evaluation_score: LLM output evaluation
# - langfuse_ab_test_variant: A/B testing variants
#
# Best Practices 2025:
# ✅ Low cardinality labels (no session_id, conversation_id, user_id as labels)
# ✅ Semantic buckets (aligned with SLO targets)
# ✅ Clear metric naming (langfuse_ prefix for namespace)
# ✅ Comprehensive documentation (integration points, dashboard panels, use cases)
# ✅ Histogram for distributions (scores, depth, durations)
# ✅ Counter for rates (usage, assignments, calls, handoffs)
