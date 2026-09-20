"""Live mode configuration (ADR-299).

Deployment-wide knobs only. The person's provider key, model, voice and
thinking level live in the ``gemini_live`` connector (encrypted / metadata);
their conversation preferences live in ``users.live_preferences``.

Created: 2026-09-18
Reference: docs/technical/LIVE_MODE.md
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    GEMINI_TTS_SAMPLE_MODEL_DEFAULT,
    LIVE_CONNECT_WINDOW_SECONDS_DEFAULT,
    LIVE_CONTEXT_TARGET_TOKENS_DEFAULT,
    LIVE_CONTEXT_TRIGGER_TOKENS_DEFAULT,
    LIVE_DELEGATION_RESULT_MAX_TOKENS_DEFAULT,
    LIVE_DELEGATION_TIMEOUT_SECONDS_DEFAULT,
    LIVE_DIRECT_TOOL_CALLS_MAX_DEFAULT,
    LIVE_EXTENSION_MINUTES_DEFAULT,
    LIVE_EXTENSION_PROMPT_SECONDS_DEFAULT,
    LIVE_HIDDEN_GRACE_SECONDS_DEFAULT,
    LIVE_IDLE_TIMEOUT_SECONDS_DEFAULT,
    LIVE_IDLE_TIMEOUT_SECONDS_MAX,
    LIVE_IDLE_TIMEOUT_SECONDS_MIN,
    LIVE_MAX_CONCURRENT_SESSIONS_DEFAULT,
    LIVE_MINT_RATE_LIMIT_MAX_CALLS_DEFAULT,
    LIVE_MINT_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    LIVE_PROBE_TIMEOUT_SECONDS_DEFAULT,
    LIVE_SESSION_MAX_MINUTES_DEFAULT,
    LIVE_SESSION_MAX_MINUTES_MAX,
    LIVE_SESSION_MAX_MINUTES_MIN,
    VOICE_DELEGATION_LEASE_WAIT_SECONDS_DEFAULT,
    VOICE_DELEGATION_RUN_TIMEOUT_SECONDS_DEFAULT,
)


class LiveSettings(BaseSettings):
    """Settings for the duplex voice mode on the person's provider key."""

    live_enabled: bool = Field(
        default=False,
        description=(
            "Deployment ceiling for the live mode (PlatformCapability.LIVE): the /live "
            "routes, the chat button and the settings section."
        ),
    )
    live_session_max_minutes: int = Field(
        default=LIVE_SESSION_MAX_MINUTES_DEFAULT,
        ge=LIVE_SESSION_MAX_MINUTES_MIN,
        le=LIVE_SESSION_MAX_MINUTES_MAX,
        description=(
            "Default longest session before the person is asked to extend it (also the "
            "credential's expiry) for a model whose connector stores none; each model "
            "of a connector keeps its own, 0 meaning unlimited."
        ),
    )
    live_extension_minutes: int = Field(
        default=LIVE_EXTENSION_MINUTES_DEFAULT,
        ge=1,
        le=120,
        description="Minutes one explicit extension adds to the cap (unlimited, each explicit).",
    )
    live_direct_tool_calls_max: int = Field(
        default=LIVE_DIRECT_TOOL_CALLS_MAX_DEFAULT,
        ge=1,
        le=1000,
        description=(
            "Lookups a DIRECT live session may run before the voice is told the budget is "
            "spent (ADR-300 wave 4) — a model in a loop must not spend for ever."
        ),
    )
    live_extension_prompt_seconds: int = Field(
        default=LIVE_EXTENSION_PROMPT_SECONDS_DEFAULT,
        ge=10,
        le=600,
        description="Seconds before the cap at which the extension dialog is shown.",
    )
    live_connect_window_seconds: int = Field(
        default=LIVE_CONNECT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=600,
        description="How long a minted credential may wait before its connection opens.",
    )
    live_idle_timeout_seconds: int = Field(
        default=LIVE_IDLE_TIMEOUT_SECONDS_DEFAULT,
        ge=LIVE_IDLE_TIMEOUT_SECONDS_MIN,
        le=LIVE_IDLE_TIMEOUT_SECONDS_MAX,
        description=(
            "Default silence after which the client ends the session (nobody speaks, LIA "
            "neither, no delegation in flight, no provider processing) for a model whose "
            "connector stores none; each model keeps its own, 0 meaning never."
        ),
    )
    live_hidden_grace_seconds: int = Field(
        default=LIVE_HIDDEN_GRACE_SECONDS_DEFAULT,
        ge=0,
        le=600,
        description="Tab hidden longer than this ends the session (iOS suspends audio).",
    )
    live_max_concurrent_sessions: int = Field(
        default=LIVE_MAX_CONCURRENT_SESSIONS_DEFAULT,
        ge=1,
        le=1000,
        description="Sessions open at once on this instance (bounds the delegated-turn load).",
    )
    live_mint_rate_limit_max_calls: int = Field(
        default=LIVE_MINT_RATE_LIMIT_MAX_CALLS_DEFAULT,
        ge=1,
        le=100,
        description="Credential mints per account per window (a reconnection mints one too).",
    )
    live_mint_rate_limit_window_seconds: int = Field(
        default=LIVE_MINT_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=3600,
        description="The mint rate-limit window.",
    )
    live_delegation_timeout_seconds: int = Field(
        default=LIVE_DELEGATION_TIMEOUT_SECONDS_DEFAULT,
        ge=10,
        le=600,
        description=(
            "After this, the voice is told LIA is still working and the answer will "
            "appear in the chat; the detached run continues (ADR-117)."
        ),
    )
    live_delegation_result_max_tokens: int = Field(
        default=LIVE_DELEGATION_RESULT_MAX_TOKENS_DEFAULT,
        ge=50,
        le=8000,
        description=(
            "Budget of the flattened answer handed back to the voice (the chat keeps it whole)."
        ),
    )
    voice_delegation_run_timeout_seconds: int = Field(
        default=VOICE_DELEGATION_RUN_TIMEOUT_SECONDS_DEFAULT,
        ge=30,
        le=900,
        description=(
            "Hard bound of a turn delegated through the server-side bridge (the phone's "
            "Live mode, ADR-301); the voice's own wait is the vendor's, shorter."
        ),
    )
    voice_delegation_lease_wait_seconds: int = Field(
        default=VOICE_DELEGATION_LEASE_WAIT_SECONDS_DEFAULT,
        ge=1,
        le=60,
        description=(
            "How long a delegated request waits for the conversation's lease before the "
            "voice is told LIA is busy with the person's own chat turn."
        ),
    )
    live_context_trigger_tokens: int = Field(
        default=LIVE_CONTEXT_TRIGGER_TOKENS_DEFAULT,
        ge=1000,
        le=120_000,
        description="Context window compression trigger sent in the session setup.",
    )
    live_context_target_tokens: int = Field(
        default=LIVE_CONTEXT_TARGET_TOKENS_DEFAULT,
        ge=500,
        le=60_000,
        description="Sliding window target sent in the session setup.",
    )
    live_probe_timeout_seconds: int = Field(
        default=LIVE_PROBE_TIMEOUT_SECONDS_DEFAULT,
        ge=3,
        le=60,
        description=(
            "Bound of a provider call that opens a session on the person's key: the "
            "activation probe, a voice sample's start, an SDP offer exchange."
        ),
    )
    live_voice_sample_model: str = Field(
        default=GEMINI_TTS_SAMPLE_MODEL_DEFAULT,
        min_length=1,
        description=(
            "The Gemini TTS model a voice sample is synthesised with, on the person's own key "
            "(never counted); the voices are the live models' own."
        ),
    )

    @model_validator(mode="after")
    def _extension_prompt_inside_the_cap(self) -> LiveSettings:
        """Refuse a prompt at or beyond the cap: the question would come after the end."""
        if self.live_extension_prompt_seconds >= self.live_session_max_minutes * 60:
            raise ValueError(
                "LIVE_EXTENSION_PROMPT_SECONDS must be below LIVE_SESSION_MAX_MINUTES * 60"
            )
        return self
