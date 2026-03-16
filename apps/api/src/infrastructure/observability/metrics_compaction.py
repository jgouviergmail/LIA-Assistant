"""
Prometheus metrics for context compaction observability.

Tracks compaction executions, skips, token savings, duration, and cost.

Phase: F4 — Intelligent Context Compaction
Created: 2026-03-16
"""

from prometheus_client import Counter, Histogram

# ============================================================================
# COMPACTION EXECUTION METRICS
# ============================================================================

compaction_executions_total = Counter(
    "compaction_executions_total",
    "Total compaction executions by strategy",
    ["strategy"],  # strategy: single_chunk / multi_chunk / descriptive_fallback
)

compaction_skipped_total = Counter(
    "compaction_skipped_total",
    "Total compaction skips by reason",
    ["reason"],  # reason: below_threshold / too_few_messages / disabled /
    #   hitl_pending_draft / hitl_pending_disambiguation / hitl_pending_queue
)

compaction_tokens_saved = Histogram(
    "compaction_tokens_saved",
    "Tokens saved per compaction execution",
    buckets=[1000, 5000, 10000, 20000, 50000, 100000, 200000],
)

compaction_duration_seconds = Histogram(
    "compaction_duration_seconds",
    "Duration of compaction LLM calls",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
)

compaction_cost_tokens_total = Counter(
    "compaction_cost_tokens_total",
    "Total tokens consumed by compaction LLM calls (prompt + completion)",
    ["token_type"],  # token_type: prompt / completion
)

compaction_errors_total = Counter(
    "compaction_errors_total",
    "Total compaction errors by type",
    ["error_type"],  # error_type: llm_failure / timeout / unexpected
)
