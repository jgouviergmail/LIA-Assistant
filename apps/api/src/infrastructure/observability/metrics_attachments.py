"""
Prometheus metrics for the attachments domain.

Follows RED methodology (Rate, Errors, Duration) pattern
from metrics_voice.py.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# Upload Metrics
# ============================================================================

attachments_uploaded_total = Counter(
    "attachments_uploaded_total",
    "Total file attachments uploaded",
    ["content_type", "status"],  # content_type: image|document, status: success|error
)

attachments_upload_size_bytes = Histogram(
    "attachments_upload_size_bytes",
    "Size of uploaded attachments in bytes",
    ["content_type"],
    buckets=[1024, 10240, 102400, 524288, 1048576, 5242880, 10485760, 20971520],
)

attachments_upload_duration_seconds = Histogram(
    "attachments_upload_duration_seconds",
    "Attachment upload processing duration (validation + save + extraction)",
    ["content_type"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# ============================================================================
# Vision LLM Metrics
# ============================================================================

vision_llm_requests_total = Counter(
    "vision_llm_requests_total",
    "Total vision LLM requests triggered by attachments",
    ["model"],
)

vision_llm_duration_seconds = Histogram(
    "vision_llm_duration_seconds",
    "Vision LLM call duration",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0],
)

# ============================================================================
# Cleanup Metrics
# ============================================================================

attachments_cleanup_deleted_total = Counter(
    "attachments_cleanup_deleted_total",
    "Total attachments deleted by cleanup job",
    ["reason"],  # reason: expired|conversation_reset
)

attachments_active_count = Gauge(
    "attachments_active_count",
    "Current number of active (non-expired) attachments",
)
