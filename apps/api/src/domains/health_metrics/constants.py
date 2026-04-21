"""Constants local to the Health Metrics domain.

Centralizes string-valued domain constants (log event names, deletion scope
literals, Prometheus labels) to avoid magic strings inside the service and
router layers.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
Revised: 2026-04-21 — polymorphic samples + batch upsert events.
"""

from __future__ import annotations

# =============================================================================
# Structured log event names (structlog event= field)
# =============================================================================

LOG_EVENT_SAMPLES_INGESTED: str = "health_samples_ingested"
LOG_EVENT_SAMPLE_REJECTED: str = "health_sample_rejected"
LOG_EVENT_BATCH_DUPLICATES_COLLAPSED: str = "health_batch_duplicates_collapsed"
LOG_EVENT_SAMPLES_DELETED: str = "health_samples_deleted"
LOG_EVENT_TOKEN_GENERATED: str = "health_metric_token_generated"
LOG_EVENT_TOKEN_REVOKED: str = "health_metric_token_revoked"
LOG_EVENT_TOKEN_REJECTED: str = "health_metric_token_rejected"
LOG_EVENT_RATE_LIMIT_HIT: str = "health_metric_rate_limit_hit"
LOG_EVENT_PARSER_ERROR: str = "health_metric_parser_error"

# =============================================================================
# Validation rejection reasons (used in logs + Prometheus labels — low cardinality)
# =============================================================================

REJECTION_REASON_OUT_OF_RANGE: str = "out_of_range"
REJECTION_REASON_MALFORMED: str = "malformed"
REJECTION_REASON_MISSING_FIELD: str = "missing_field"
REJECTION_REASON_INVALID_DATE: str = "invalid_date"

# =============================================================================
# Deletion scopes
# =============================================================================

DELETION_SCOPE_ALL: str = "all"
DELETION_SCOPE_KIND: str = "kind"

# =============================================================================
# Upsert operation labels (Prometheus)
# =============================================================================

UPSERT_OPERATION_INSERT: str = "insert"
UPSERT_OPERATION_UPDATE: str = "update"
