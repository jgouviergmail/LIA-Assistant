"""Constants local to the Health Metrics domain.

Centralizes string-valued domain constants (log event names, deletion scope
literals, Prometheus labels) to avoid magic strings inside the service and
router layers.

Phase: evolution — Health Metrics (iPhone Shortcuts integration)
Created: 2026-04-20
"""

from __future__ import annotations

# =============================================================================
# Structured log event names (structlog event= field)
# =============================================================================

LOG_EVENT_METRIC_INGESTED: str = "health_metric_ingested"
LOG_EVENT_METRIC_REJECTED: str = "health_metric_rejected"
LOG_EVENT_METRIC_FIELD_INVALID: str = "health_metric_field_invalid"
LOG_EVENT_METRIC_DELETED: str = "health_metric_deleted"
LOG_EVENT_TOKEN_GENERATED: str = "health_metric_token_generated"
LOG_EVENT_TOKEN_REVOKED: str = "health_metric_token_revoked"
LOG_EVENT_TOKEN_REJECTED: str = "health_metric_token_rejected"
LOG_EVENT_RATE_LIMIT_HIT: str = "health_metric_rate_limit_hit"

# =============================================================================
# Validation rejection reasons (used in logs + Prometheus labels — low cardinality)
# =============================================================================

REJECTION_REASON_OUT_OF_RANGE: str = "out_of_range"
REJECTION_REASON_INVALID_TYPE: str = "invalid_type"
REJECTION_REASON_MISSING: str = "missing"

# =============================================================================
# Deletion scopes
# =============================================================================

DELETION_SCOPE_ALL: str = "all"
DELETION_SCOPE_FIELD: str = "field"

# =============================================================================
# Ingest response status values
# =============================================================================

INGEST_STATUS_ACCEPTED: str = "accepted"
INGEST_STATUS_PARTIAL: str = "partial"  # Accepted but some fields nullified
