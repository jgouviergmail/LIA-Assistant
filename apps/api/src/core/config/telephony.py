"""Telephony (agentic outbound calls) settings.

Deployment-wide knobs only. Per-user ElevenLabs credentials (API key, webhook
secret) and identifiers (agent_id, phone_number_id) live in the
``ELEVENLABS_TELEPHONY`` connector, encrypted — never here.

See docs/superpowers/specs/2026-07-07-telephony-agentic-calls-design.md (v5).
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    TELEPHONY_CALL_RETENTION_DAYS_DEFAULT,
    TELEPHONY_MAX_CALL_DURATION_SECONDS_DEFAULT,
    TELEPHONY_PREFETCH_WINDOW_DAYS_DEFAULT,
    TELEPHONY_RATE_LIMIT_PER_HOUR_DEFAULT,
    TELEPHONY_RINGING_TIMEOUT_SECONDS_DEFAULT,
    TELEPHONY_STALE_CALL_TIMEOUT_MINUTES_DEFAULT,
    TELEPHONY_STALE_REAPER_INTERVAL_MINUTES_DEFAULT,
    TELEPHONY_WEBHOOK_TOLERANCE_SECONDS_DEFAULT,
)


class TelephonySettings(BaseSettings):
    """Telephony feature settings (composed into the main ``Settings`` class)."""

    telephony_enabled: bool = Field(
        default=False,
        description="Master switch for the agentic telephony feature.",
    )
    telephony_ringing_timeout_seconds: int = Field(
        default=TELEPHONY_RINGING_TIMEOUT_SECONDS_DEFAULT,
        ge=5,
        le=120,
        description="Ringing timeout passed to ElevenLabs telephony_call_config.",
    )
    telephony_prefetch_window_days: int = Field(
        default=TELEPHONY_PREFETCH_WINDOW_DAYS_DEFAULT,
        ge=1,
        le=60,
        description="Margin (days) around the objective window for availability pre-fetch.",
    )
    telephony_max_call_duration_seconds: int = Field(
        default=TELEPHONY_MAX_CALL_DURATION_SECONDS_DEFAULT,
        ge=30,
        le=3600,
        description="Hard cap on call duration (used when provisioning the agent).",
    )
    telephony_call_retention_days: int = Field(
        default=TELEPHONY_CALL_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Retention TTL (days) for PhoneCall.summary/structured_data (D-8).",
    )
    telephony_stale_call_timeout_minutes: int = Field(
        default=TELEPHONY_STALE_CALL_TIMEOUT_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description="A dialing/in_progress call with no webhook after this is marked failed.",
    )
    telephony_rate_limit_per_hour: int = Field(
        default=TELEPHONY_RATE_LIMIT_PER_HOUR_DEFAULT,
        ge=1,
        le=1000,
        description="Per-user place_phone_call rate limit (calls/hour).",
    )
    telephony_webhook_tolerance_seconds: int = Field(
        default=TELEPHONY_WEBHOOK_TOLERANCE_SECONDS_DEFAULT,
        ge=30,
        le=86400,
        description="Post-call webhook HMAC replay window (reject older timestamps).",
    )
    telephony_stale_reaper_interval_minutes: int = Field(
        default=TELEPHONY_STALE_REAPER_INTERVAL_MINUTES_DEFAULT,
        ge=1,
        le=60,
        description="Interval (minutes) for the stale-call reaper sweep.",
    )
