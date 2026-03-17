"""
Prometheus metrics for sub-agent observability.

Tracks sub-agent executions, duration, tokens, errors, and guard-rail triggers.

Phase: F6 — Persistent Specialized Sub-Agents
Created: 2026-03-16
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# EXECUTION METRICS
# ============================================================================

subagent_spawned_total = Counter(
    "subagent_spawned_total",
    "Total sub-agent executions by agent name and mode",
    ["agent_name", "mode"],  # mode: sync / background
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
)

# ============================================================================
# ERROR & GUARD-RAIL METRICS
# ============================================================================

subagent_errors_total = Counter(
    "subagent_errors_total",
    "Total sub-agent execution errors by type",
    ["agent_name", "error_type"],  # error_type: timeout / token_budget / failure / cancelled
)

subagent_token_budget_exceeded_total = Counter(
    "subagent_token_budget_exceeded_total",
    "Total sub-agent executions stopped by token budget guard",
    ["agent_name"],
)

subagent_killed_total = Counter(
    "subagent_killed_total",
    "Total sub-agent executions killed by reason",
    ["agent_name", "reason"],  # reason: timeout / token_budget / manual / consecutive_failures
)

subagent_daily_tokens_consumed = Gauge(
    "subagent_daily_tokens_consumed",
    "Daily token consumption for sub-agent executions per user",
    ["user_id"],
)
