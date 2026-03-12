"""
Prometheus metrics for multi-channel messaging (Telegram, etc.).

Implements RED metrics (Rate, Errors, Duration) for:
- Inbound message processing
- Outbound message delivery
- OTP generation and verification
- HITL decisions via channels
- Voice transcription
- Channel binding state

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# INBOUND MESSAGES
# ============================================================================

channel_messages_received_total = Counter(
    "channel_messages_received_total",
    "Total inbound messages received via channels",
    ["channel_type", "message_type"],
)

channel_message_processing_duration_seconds = Histogram(
    "channel_message_processing_duration_seconds",
    "Duration of inbound message processing (binding lookup to response sent)",
    ["channel_type"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0, 60.0],
)

channel_messages_rejected_total = Counter(
    "channel_messages_rejected_total",
    "Total inbound messages rejected (rate limited, locked, unbound)",
    ["channel_type", "reason"],
)

# ============================================================================
# OUTBOUND MESSAGES
# ============================================================================

channel_messages_sent_total = Counter(
    "channel_messages_sent_total",
    "Total outbound messages sent via channels",
    ["channel_type", "message_type"],
)

channel_send_errors_total = Counter(
    "channel_send_errors_total",
    "Total outbound message send errors",
    ["channel_type", "error_type"],
)

# ============================================================================
# BINDINGS
# ============================================================================

channel_active_bindings = Gauge(
    "channel_active_bindings",
    "Number of active channel bindings",
    ["channel_type"],
)

# ============================================================================
# OTP
# ============================================================================

channel_otp_generated_total = Counter(
    "channel_otp_generated_total",
    "Total OTP codes generated",
    ["channel_type"],
)

channel_otp_verified_total = Counter(
    "channel_otp_verified_total",
    "Total OTP verification attempts",
    ["channel_type", "status"],
)

# ============================================================================
# HITL VIA CHANNELS
# ============================================================================

channel_hitl_decisions_total = Counter(
    "channel_hitl_decisions_total",
    "Total HITL decisions made via channels",
    ["channel_type", "decision"],
)

# ============================================================================
# VOICE TRANSCRIPTION
# ============================================================================

channel_voice_transcriptions_total = Counter(
    "channel_voice_transcriptions_total",
    "Total voice transcription attempts via channels",
    ["channel_type", "status"],
)

channel_voice_duration_seconds = Histogram(
    "channel_voice_duration_seconds",
    "Duration of received voice messages",
    ["channel_type"],
    buckets=[1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0],
)

# ============================================================================
# NOTIFICATIONS VIA CHANNELS
# ============================================================================

channel_notifications_sent_total = Counter(
    "channel_notifications_sent_total",
    "Total proactive notifications sent via channels",
    ["channel_type", "task_type"],
)

channel_notification_errors_total = Counter(
    "channel_notification_errors_total",
    "Total proactive notification send errors",
    ["channel_type", "error_type"],
)
