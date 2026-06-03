"""
Prometheus metrics for sub-agent observability.

Tracks sub-agent ReAct executions, duration, tokens and errors. Emitted by the
generic ``ReactSubAgentRunner`` (the single sub-agent execution path per
ADR-083), labelled by ``agent_name`` (the runner's ``llm_type``).

The token-budget / kill / per-user daily-token guard-rail metrics from the
original F6 design were removed in 2026-05: ADR-083 Phase 2 deleted the bespoke
``SubAgentExecutor`` pipeline, so those mechanisms (and therefore those metrics)
no longer exist.

Phase: F6 / ADR-083 — Sub-Agent Delegation as Parameterized ReAct Loop
Created: 2026-03-16
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# EXECUTION METRICS
# ============================================================================

subagent_spawned_total = Counter(
    "subagent_spawned_total",
    "Total sub-agent executions by agent name and mode",
    ["agent_name", "mode"],  # mode: sync (the runner always awaits the loop)
)

subagent_duration_seconds = Histogram(
    "subagent_duration_seconds",
    "Duration of sub-agent execution in seconds",
    ["agent_name"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
)

subagent_tokens_in_total = Counter(
    "subagent_tokens_in_total",
    "Total prompt tokens consumed by sub-agent executions",
    ["agent_name"],
)

subagent_tokens_out_total = Counter(
    "subagent_tokens_out_total",
    "Total completion tokens consumed by sub-agent executions",
    ["agent_name"],
)

subagent_active_count = Gauge(
    "subagent_active_count",
    "Number of sub-agents currently executing",
    multiprocess_mode="livesum",
)

# ============================================================================
# ERROR METRICS
# ============================================================================

subagent_errors_total = Counter(
    "subagent_errors_total",
    "Total sub-agent execution errors by type",
    # error_type: the raised exception class name (e.g. TimeoutError, ValueError).
    ["agent_name", "error_type"],
)
