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
    # strategy: single_chunk / multi_chunk / single_chunk_with_merge /
    # truncation / noop. `descriptive_fallback` was removed in v2 in favour
    # of an explicit `truncation` strategy with a user-visible notice.
    ["strategy"],
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

# ============================================================================
# COMPACTION V2 HARDENING METRICS (2026-05)
# ============================================================================

# Chunk-level timeouts (per LLM ainvoke call). Different from `errors_total`
# (broad error counter) — this one focuses on the asyncio.wait_for trigger.
compaction_chunk_timeouts_total = Counter(
    "compaction_chunk_timeouts_total",
    "Compaction chunk LLM calls that hit the per-chunk asyncio.wait_for timeout",
)

# Global timeouts: the whole compact() budget was exceeded → truncation fallback.
compaction_global_timeouts_total = Counter(
    "compaction_global_timeouts_total",
    "Compaction runs that exceeded the global budget and fell back to truncation",
)

# End-to-end duration with buckets adapted to the new global budget (120s default).
# Replaces the old `compaction_duration_seconds` histogram for v2-aware dashboards;
# the legacy metric is kept for backward compatibility with existing alerts.
compaction_total_duration_seconds = Histogram(
    "compaction_total_duration_seconds",
    "End-to-end compact() duration in seconds (v2)",
    buckets=[1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 180],
)

# Writer-unavailability counter — fires when `langgraph.config.get_stream_writer`
# is missing (LangGraph downgrade) or raises (graph executed without
# `stream_mode=["custom"]`). Both branches degrade silently to a no-op writer,
# so this counter is the only production-visible signal that the compaction
# SSE start/done events are being dropped.
compaction_writer_unavailable_total = Counter(
    "compaction_writer_unavailable_total",
    "Compaction node fallbacks to a no-op stream writer (start/done events dropped)",
    ["reason"],  # reason: get_stream_writer_import_failed / get_stream_writer_raised
)
