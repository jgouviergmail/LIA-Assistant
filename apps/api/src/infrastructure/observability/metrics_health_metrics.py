"""Prometheus metrics for the Health Metrics domain.

Covers the ingestion endpoint (outcome + latency), per-field validation
rejections, token lifecycle, and deletion operations.

All label cardinalities are bounded on purpose:
- ``status``: accepted | partial
- ``field``: heart_rate | steps
- ``reason``: out_of_range | invalid_type | missing
- ``scope``: all | field
- ``source`` is NOT a label to keep cardinality low — use DB queries if you
  need per-client breakdowns.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# =============================================================================
# Ingestion
# =============================================================================

health_metrics_ingested_total = Counter(
    "health_metrics_ingested_total",
    "Total successful health-metric ingestions, labeled by outcome.",
    ["status"],
    # status: accepted | partial
)

health_metrics_ingest_duration_seconds = Histogram(
    "health_metrics_ingest_duration_seconds",
    "Ingestion endpoint latency (seconds).",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

health_metrics_validation_rejected_total = Counter(
    "health_metrics_validation_rejected_total",
    "Per-field validation rejections that nullified an individual metric.",
    ["field", "reason"],
)

health_metrics_rate_limit_hits_total = Counter(
    "health_metrics_rate_limit_hits_total",
    "Ingestion requests rejected because the per-token rate limit was hit.",
)

health_metrics_auth_failures_total = Counter(
    "health_metrics_auth_failures_total",
    "Ingestion requests rejected for missing/invalid/revoked tokens.",
    ["reason"],
    # reason: missing_or_malformed_header | unknown_or_revoked
)

# =============================================================================
# Tokens
# =============================================================================

health_metrics_tokens_generated_total = Counter(
    "health_metrics_tokens_generated_total",
    "Ingestion tokens issued via the Settings UI.",
)

health_metrics_tokens_revoked_total = Counter(
    "health_metrics_tokens_revoked_total",
    "Ingestion tokens revoked via the Settings UI.",
)
# Active token count is derivable in PromQL as
#   (sum(health_metrics_tokens_generated_total)
#    - sum(health_metrics_tokens_revoked_total))
# so no dedicated Gauge is exposed — keeping cardinality and scheduler
# responsibilities out of the domain.

# =============================================================================
# Deletion
# =============================================================================

health_metrics_deleted_total = Counter(
    "health_metrics_deleted_total",
    "User-initiated deletions, labeled by scope.",
    ["scope"],
    # scope: all | field
)
