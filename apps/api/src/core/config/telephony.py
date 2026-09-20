"""Telephony (agentic outbound calls) settings.

Deployment-wide knobs only. Per-user ElevenLabs credentials (API key, webhook
secret) and identifiers (agent_id, phone_number_id) live in the
``ELEVENLABS_TELEPHONY`` connector, encrypted — never here.

What the vendor agent SOUNDS like is not here either (owner decision,
2026-09-16): its model and reasoning effort, its language, its voice, its
audio format and its duration cap are administered on the ElevenLabs portal,
for the agent, and changed there without restarting the application. LIA
passes only what is its own — prompts, greeting, tools, context, data
contract (``telephony/client.py``).

See docs/superpowers/specs/2026-07-07-telephony-agentic-calls-design.md (v5).
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    TELEPHONY_CALL_RETENTION_DAYS_DEFAULT,
    TELEPHONY_DEFAULT_COUNTRY_CODE_DEFAULT,
    TELEPHONY_DELEGATION_TIMEOUT_SECONDS_DEFAULT,
    TELEPHONY_LIVE_TOOL_MAX_CALLS_PER_CALL_DEFAULT,
    TELEPHONY_LIVE_TOOL_RESULT_MAX_TOKENS_DEFAULT,
    TELEPHONY_LIVE_TOOL_TIMEOUT_SECONDS_DEFAULT,
    TELEPHONY_NOTIFICATION_GRACE_SECONDS_DEFAULT,
    TELEPHONY_NOTIFICATION_MAX_ATTEMPTS_DEFAULT,
    TELEPHONY_NOTIFICATION_REAPER_INTERVAL_MINUTES_DEFAULT,
    TELEPHONY_PREFETCH_WINDOW_DAYS_DEFAULT,
    TELEPHONY_PROBE_NOT_FOUND_GRACE_SECONDS_DEFAULT,
    TELEPHONY_RATE_LIMIT_PER_HOUR_DEFAULT,
    TELEPHONY_RELAY_BUSY_DELAY_SECONDS_DEFAULT,
    TELEPHONY_RELAY_BUSY_RETRIES_DEFAULT,
    TELEPHONY_RELAY_MAX_AGE_MINUTES_DEFAULT,
    TELEPHONY_RELAY_TIMEOUT_SECONDS_DEFAULT,
    TELEPHONY_RELAY_TRANSCRIPT_MAX_TOKENS_DEFAULT,
    TELEPHONY_RETURN_GRACE_SECONDS_DEFAULT,
    TELEPHONY_RETURN_MAX_AGE_MINUTES_DEFAULT,
    TELEPHONY_RETURN_MAX_ATTEMPTS_DEFAULT,
    TELEPHONY_RETURN_REAPER_INTERVAL_MINUTES_DEFAULT,
    TELEPHONY_RETURN_RETRY_DELAY_SECONDS_DEFAULT,
    TELEPHONY_RINGING_TIMEOUT_SECONDS_DEFAULT,
    TELEPHONY_SELF_CONTEXT_MAX_TOKENS_DEFAULT,
    TELEPHONY_STALE_CALL_TIMEOUT_MINUTES_DEFAULT,
    TELEPHONY_STALE_REAPER_INTERVAL_MINUTES_DEFAULT,
    TELEPHONY_VERIFICATION_CODE_LENGTH_DEFAULT,
    TELEPHONY_VERIFICATION_CODE_TTL_SECONDS_DEFAULT,
    TELEPHONY_VERIFICATION_MAX_ATTEMPTS_DEFAULT,
    TELEPHONY_WEBHOOK_TOLERANCE_SECONDS_DEFAULT,
)


class TelephonySettings(BaseSettings):
    """Telephony feature settings (composed into the main ``Settings`` class)."""

    telephony_enabled: bool = Field(
        default=False,
        description="Master switch for the agentic telephony feature.",
    )
    telephony_default_country_code: str = Field(
        default=TELEPHONY_DEFAULT_COUNTRY_CODE_DEFAULT,
        pattern=r"^$|^\+\d{1,3}$",
        description=(
            "Country calling code (e.g. '+33') applied to national numbers with a "
            "single leading 0 so dialing uses E.164. Empty = numbers passed as-is."
        ),
    )
    telephony_probe_not_found_grace_seconds: int = Field(
        default=TELEPHONY_PROBE_NOT_FOUND_GRACE_SECONDS_DEFAULT,
        ge=10,
        le=600,
        description=(
            "Age a call row must reach before a 404 conversation-status probe "
            "closes it as gone (guards against closing a freshly dialed call "
            "whose conversation is not yet readable vendor-side)."
        ),
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
        description=(
            "Per-user cap on paid calls (calls/hour): place_phone_call, call_me and "
            "the number-verification calls alike — one line, one bill."
        ),
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
    telephony_return_max_attempts: int = Field(
        default=TELEPHONY_RETURN_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=10,
        description="Bounded retries of the idempotent post-call return delivery (T1).",
    )
    telephony_return_retry_delay_seconds: int = Field(
        default=TELEPHONY_RETURN_RETRY_DELAY_SECONDS_DEFAULT,
        ge=0,
        le=120,
        description="Delay (seconds) between post-call return delivery retries.",
    )
    telephony_notification_grace_seconds: int = Field(
        default=TELEPHONY_NOTIFICATION_GRACE_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Grace (seconds) before the notification reaper re-dispatches a "
        "PENDING return — keeps it from racing the live in-process dispatch (T1).",
    )
    telephony_notification_reaper_interval_minutes: int = Field(
        default=TELEPHONY_NOTIFICATION_REAPER_INTERVAL_MINUTES_DEFAULT,
        ge=1,
        le=60,
        description="Interval (minutes) for the return-notification recovery reaper (T1).",
    )
    telephony_notification_max_attempts: int = Field(
        default=TELEPHONY_NOTIFICATION_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=20,
        description="Bounded re-dispatch attempts before a PENDING return is marked FAILED (T1).",
    )
    telephony_return_grace_seconds: int = Field(
        default=TELEPHONY_RETURN_GRACE_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Grace (seconds) before the return reaper re-runs a RECEIVED inbox "
        "synthesis — keeps it from racing the live fire-and-forget synthesis (T1-A).",
    )
    telephony_return_max_age_minutes: int = Field(
        default=TELEPHONY_RETURN_MAX_AGE_MINUTES_DEFAULT,
        ge=5,
        le=1440,
        description="A RECEIVED inbox row still unsynthesized after this is retired to "
        "FAILED and its encrypted transcript purged (T1-A give-up + D-8).",
    )
    telephony_return_reaper_interval_minutes: int = Field(
        default=TELEPHONY_RETURN_REAPER_INTERVAL_MINUTES_DEFAULT,
        ge=1,
        le=60,
        description="Interval (minutes) for the pre-synthesis return recovery reaper (T1-A).",
    )
    # --- Owner and verification mandates (phone-as-a-channel, lot 2) ---------
    telephony_verification_code_length: int = Field(
        default=TELEPHONY_VERIFICATION_CODE_LENGTH_DEFAULT,
        ge=4,
        le=8,
        description="Digits in the code the verification call reads aloud.",
    )
    telephony_verification_code_ttl_seconds: int = Field(
        default=TELEPHONY_VERIFICATION_CODE_TTL_SECONDS_DEFAULT,
        ge=60,
        le=3600,
        description="How long a spoken verification code stays valid.",
    )
    telephony_verification_max_attempts: int = Field(
        default=TELEPHONY_VERIFICATION_MAX_ATTEMPTS_DEFAULT,
        ge=1,
        le=20,
        description="Wrong codes tolerated before the pending verification is void.",
    )
    telephony_self_context_max_tokens: int = Field(
        default=TELEPHONY_SELF_CONTEXT_MAX_TOKENS_DEFAULT,
        ge=200,
        le=20000,
        description=(
            "Token budget of the context block an owner call carries (memories, agenda, "
            "reminders, open loops, recent exchanges) — spent in that order, cuts stated."
        ),
    )
    telephony_relay_transcript_max_tokens: int = Field(
        default=TELEPHONY_RELAY_TRANSCRIPT_MAX_TOKENS_DEFAULT,
        ge=500,
        le=60000,
        description=(
            "Token budget of the transcript the relay synthesis reads after an owner "
            "call; the cut is stated to the model."
        ),
    )
    telephony_relay_timeout_seconds: int = Field(
        default=TELEPHONY_RELAY_TIMEOUT_SECONDS_DEFAULT,
        ge=30,
        le=900,
        description="Hard bound of one attempt of the relayed turn after an owner call.",
    )
    telephony_relay_busy_retries: int = Field(
        default=TELEPHONY_RELAY_BUSY_RETRIES_DEFAULT,
        ge=1,
        le=20,
        description="How many times a busy conversation is retried before the relay falls back.",
    )
    telephony_relay_busy_delay_seconds: int = Field(
        default=TELEPHONY_RELAY_BUSY_DELAY_SECONDS_DEFAULT,
        ge=0,
        le=300,
        description="Pause between two attempts to take the conversation's lock for a relay.",
    )
    telephony_relay_max_age_minutes: int = Field(
        default=TELEPHONY_RELAY_MAX_AGE_MINUTES_DEFAULT,
        ge=2,
        le=240,
        description=(
            "A RELAYING outbox row older than this (a crash mid-relay) is handed to the "
            "notification reaper as PENDING."
        ),
    )
    # --- Live read-only tools on an owner call (lot 7, flagged) --------------
    telephony_live_tools_enabled: bool = Field(
        default=False,
        description=(
            "Let the owner call look things up live (calendar, tasks, open loops) "
            "through webhook tools the vendor calls back on this API; read-only, "
            "bound to an active owner call, off by default."
        ),
    )
    telephony_callback_base_url: str | None = Field(
        default=None,
        description=(
            "Public base URL the vendor calls this API back on for live tools and the "
            "Live mode's delegation (ADR-301); None = API_URL. A private host means "
            "the phone's Live mode is unavailable and every owner call runs direct."
        ),
    )
    telephony_live_tool_timeout_seconds: int = Field(
        default=TELEPHONY_LIVE_TOOL_TIMEOUT_SECONDS_DEFAULT,
        ge=5,
        le=60,
        description=(
            "Vendor-side timeout of a live tool call; the lookup itself is bounded "
            "a few seconds under it so the agent hears a refusal, not a timeout."
        ),
    )
    telephony_delegation_timeout_seconds: int = Field(
        default=TELEPHONY_DELEGATION_TIMEOUT_SECONDS_DEFAULT,
        ge=20,
        le=290,
        description=(
            "Vendor-side timeout of the Live mode's asynchronous delegation call-back "
            "(ADR-301); the bridge answers a few seconds under it so the voice hears "
            "« still working », never a vendor error."
        ),
    )
    telephony_live_tool_result_max_tokens: int = Field(
        default=TELEPHONY_LIVE_TOOL_RESULT_MAX_TOKENS_DEFAULT,
        ge=100,
        le=4000,
        description="Token budget of a live tool result handed to the voice agent.",
    )
    telephony_live_tool_max_calls_per_call: int = Field(
        default=TELEPHONY_LIVE_TOOL_MAX_CALLS_PER_CALL_DEFAULT,
        ge=1,
        le=200,
        description="How many live lookups one owner call may make.",
    )
