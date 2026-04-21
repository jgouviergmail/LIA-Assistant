"""Prometheus metrics for the Health Metrics domain.

Covers the batch ingestion pipeline (outcome + latency), per-sample
validation rejections, token lifecycle, and deletion operations. All label
cardinalities are bounded on purpose:

- ``kind``: heart_rate | steps
- ``operation``: insert | update (for upsert result breakdown)
- ``field``: heart_rate | steps (per-sample validation target)
- ``reason``: out_of_range | malformed | missing_field | invalid_date
- ``scope``: all | kind
- ``status``: accepted | partial (legacy ingest result — still emitted as
  an aggregated counter derived from inserted + updated vs rejected)

``source`` is NOT a label to keep cardinality low — use DB queries if you
need per-client breakdowns.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — replaced ``ingested_total`` with
``health_samples_upserted_total{kind, operation}``.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# =============================================================================
# Batch ingestion
# =============================================================================

health_samples_upserted_total = Counter(
    "health_samples_upserted_total",
    "Per-sample upsert outcomes, labeled by kind (heart_rate|steps) and "
    "operation (insert|update). Insert = new row, update = idempotent "
    "re-ingestion of an existing (user_id, kind, date_start, date_end) tuple.",
    ["kind", "operation"],
)

health_samples_batch_duplicates_total = Counter(
    "health_samples_batch_duplicates_total",
    "Intra-batch duplicate samples collapsed before UPSERT (two samples "
    "in the same request carrying the same (date_start, date_end) tuple). "
    "Common when iOS emits overlapping Apple Watch + iPhone measurements. "
    "Collapsed with last-wins semantics; reported as updates in the response.",
    ["kind"],
)

health_metrics_ingest_duration_seconds = Histogram(
    "health_metrics_ingest_duration_seconds",
    "Batch ingestion endpoint latency (seconds).",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

health_metrics_validation_rejected_total = Counter(
    "health_metrics_validation_rejected_total",
    "Per-sample validation rejections.",
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
# so no dedicated Gauge is exposed.

# =============================================================================
# Deletion
# =============================================================================

health_metrics_deleted_total = Counter(
    "health_metrics_deleted_total",
    "User-initiated deletions, labeled by scope (all | kind).",
    ["scope"],
)
