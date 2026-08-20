"""
Voice configuration module (Text-to-Speech and Speech-to-Text).

Contains settings for:
- Voice comment LLM (model, temperature, max tokens, provider, reasoning_effort)
- STT configuration (Sherpa-onnx: offline, multi-language, free)
- WebSocket STT settings (ticket auth, rate limiting, timeouts)
- ElevenLabs Scribe remote STT (paid, audio-billed)

The TTS provider/model/voice selection moved to ``llm_config_overrides``
(LLM type ``voice_tts``) in v1.20.x — see ADR-081. Voice tuning (rate,
pitch, volume, speed, voice_settings, …) is now stored as JSONB on the
override row's ``provider_config`` field, not in env vars.

Phase: Voice Feature Implementation
Created: 2025-12-24
Updated: 2025-12-29 - Migrated from Google Cloud TTS to Edge TTS
Updated: 2026-01-15 - Aligned LLM config with standard pattern (provider_config, reasoning_effort)
Updated: 2026-01-15 - Added multi-provider TTS support with generic config keys
Updated: 2026-01-16 - Refactored to Standard/HD mode architecture (admin-controlled)
Updated: 2026-02-01 - Added STT configuration (Sherpa-onnx Whisper Small INT8)
Updated: 2026-05-07 - TTS provider config relocated to llm_config_overrides (ADR-081)
"""

from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    VOICE_CHAT_MODE_MAX_SENTENCES_DEFAULT,
    VOICE_CONTEXT_MAX_CHARS_DEFAULT,
    VOICE_LLM_FREQUENCY_PENALTY_DEFAULT,
    VOICE_LLM_MAX_TOKENS_DEFAULT,
    VOICE_LLM_MODEL_DEFAULT,
    VOICE_LLM_PRESENCE_PENALTY_DEFAULT,
    VOICE_LLM_PROVIDER_CONFIG_DEFAULT,
    VOICE_LLM_TEMPERATURE_DEFAULT,
    VOICE_LLM_TOP_P_DEFAULT,
    VOICE_MAX_SENTENCES_DEFAULT,
    VOICE_PARALLEL_TIMEOUT_SECONDS_DEFAULT,
    VOICE_SENTENCE_DELIMITERS_DEFAULT,
    VOICE_STT_LANGUAGE_DEFAULT,
    VOICE_STT_MAX_DURATION_SECONDS_DEFAULT,
    VOICE_STT_MODEL_PATH_DEFAULT,
    VOICE_STT_NUM_THREADS_DEFAULT,
    VOICE_STT_TASK_DEFAULT,
    VOICE_WS_IDLE_TIMEOUT_SECONDS_DEFAULT,
    VOICE_WS_RATE_LIMIT_MAX_CALLS_DEFAULT,
    VOICE_WS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    VOICE_WS_TICKET_TTL_SECONDS_DEFAULT,
)


class VoiceSettings(BaseSettings):
    """Voice (TTS / STT) settings.

    TTS provider/model/voice selection lives on
    ``llm_config_overrides.voice_tts`` — the runtime factory in
    ``src/domains/voice/factory.py`` reads it via
    ``LLMConfigOverrideCache``. This module only carries the voice-comment
    LLM, the local Sherpa STT pipeline, the WebSocket transport defaults,
    and the ElevenLabs Scribe transport defaults.
    """

    voice_psyche_prosody_enabled: bool = Field(
        default=True,
        description=(
            "Bend the ElevenLabs voice_settings by the live PAD mood "
            "(ADR-237). Other providers ignore the block gracefully. "
            "Off = the admin-configured settings are used verbatim."
        ),
    )

    # ========================================================================
    # Voice Comment LLM Configuration
    # ========================================================================
    # Follows standard LLM configuration pattern (see llm.py for reference)
    # All parameters configurable via VOICE_LLM_* environment variables
    # ========================================================================

    voice_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini", "qwen"
    ] = Field(
        default="openai",
        description="LLM provider for voice comment generation",
    )

    voice_llm_provider_config: str = Field(
        default=VOICE_LLM_PROVIDER_CONFIG_DEFAULT,
        description="Advanced provider-specific config for voice LLM (JSON string)",
    )

    voice_llm_model: str = Field(
        default=VOICE_LLM_MODEL_DEFAULT,
        description="LLM model for voice comment generation (fast, cheap model recommended)",
    )

    voice_llm_temperature: float = Field(
        default=VOICE_LLM_TEMPERATURE_DEFAULT,
        ge=0.0,
        le=2.0,
        description="LLM temperature for voice comments (0.7 = creative but controlled)",
    )

    voice_llm_top_p: float = Field(
        default=VOICE_LLM_TOP_P_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling for voice LLM (1.0 = disabled)",
    )

    voice_llm_frequency_penalty: float = Field(
        default=VOICE_LLM_FREQUENCY_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for voice LLM (reduce repetition)",
    )

    voice_llm_presence_penalty: float = Field(
        default=VOICE_LLM_PRESENCE_PENALTY_DEFAULT,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for voice LLM (encourage diversity)",
    )

    voice_llm_max_tokens: int = Field(
        default=VOICE_LLM_MAX_TOKENS_DEFAULT,
        gt=0,
        le=2000,
        description="Max tokens for voice comment (500 ~ 6 sentences)",
    )

    voice_llm_reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = Field(
        default=None,
        description=(
            "Reasoning effort for voice LLM (OpenAI o-series/GPT-5 only). "
            "Controls reasoning depth: minimal=sub-second, low=1-3s, medium=5-15s, high=30+s. "
            "Recommended: 'low' or None for voice comments (fast creative generation)."
        ),
    )

    # ========================================================================
    # VALIDATOR - Empty String to None Conversion
    # ========================================================================

    @field_validator("voice_llm_reasoning_effort", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: Any) -> Any:
        """
        Convert empty strings to None for reasoning_effort field.

        Environment variables with empty values (VAR=) are read as "" (empty string).
        Since reasoning_effort accepts Literal[...] | None, we convert "" to None.

        Args:
            v: Raw value from environment or settings

        Returns:
            None if empty string, otherwise original value
        """
        if v == "" or v is None:
            return None
        return v

    # ========================================================================
    # Voice Comment Behavior
    # ========================================================================
    voice_max_sentences: int = Field(
        default=VOICE_MAX_SENTENCES_DEFAULT,
        ge=1,
        le=10,
        description="Maximum number of sentences in voice comment",
    )

    voice_sentence_delimiters: str = Field(
        default=VOICE_SENTENCE_DELIMITERS_DEFAULT,
        description="Characters that mark end of sentence for TTS chunking",
    )

    # ========================================================================
    # Voice Context Configuration
    # ========================================================================
    voice_context_max_chars: int = Field(
        default=VOICE_CONTEXT_MAX_CHARS_DEFAULT,
        gt=0,
        le=10000,
        description="Maximum characters for voice context (truncation limit for fallback)",
    )

    voice_parallel_timeout_seconds: float = Field(
        default=VOICE_PARALLEL_TIMEOUT_SECONDS_DEFAULT,
        gt=0.0,
        le=60.0,
        description="Timeout for parallel voice generation task (seconds). "
        "Voice LLM (~2s) + 3 TTS sentences (~4s) = ~6s minimum. "
        "Set to 15s to account for network variability.",
    )

    # ========================================================================
    # Chat Mode Direct TTS (Skip Voice LLM)
    # ========================================================================
    # NOTE: Chat mode direct TTS is always enabled (skip voice LLM for chat responses)
    # This provides faster and more natural conversational responses.

    voice_chat_mode_max_sentences: int = Field(
        default=VOICE_CHAT_MODE_MAX_SENTENCES_DEFAULT,
        ge=1,
        le=50,
        description=(
            "Maximum number of sentences synthesised by the chat-mode TTS "
            "stream (response read aloud, no voice-comment LLM). Hard cap to "
            "prevent very long replies producing minutes of audio. "
            "Recommended values: 3 (default, conversational style), 10 "
            "(longer educational answers), 50 (functional ceiling — 'read "
            "everything' mode for content-rich replies)."
        ),
    )

    # ========================================================================
    # STT (Speech-to-Text) Configuration - Sherpa-onnx Whisper
    # ========================================================================
    # Offline, multi-language STT using Whisper Small INT8 model.
    # 100% free, no API costs. Supports: 99+ languages (FR/EN/DE/ES/IT/ZH/...).
    # Model: csukuangfj/sherpa-onnx-whisper-small (~375 MB INT8)
    # Reference: domains/voice/stt/, plan zippy-drifting-valley.md
    # ========================================================================

    voice_tts_enabled: bool = Field(
        default=True,
        description=(
            "Deployment ceiling for Text-to-Speech. The provider/model picker "
            "lives on llm_config_overrides (voice_tts, ADR-081); this flag "
            "decides whether the capability is offered at all, so an operator "
            "can switch spoken answers off without touching the LLM config."
        ),
    )

    voice_stt_enabled: bool = Field(
        default=True,
        description="Enable Speech-to-Text via WebSocket /ws/audio. "
        "Requires Sherpa-onnx Whisper model to be installed.",
    )

    voice_stt_model_path: str = Field(
        default=VOICE_STT_MODEL_PATH_DEFAULT,
        description=(
            "Path to Sherpa-onnx Whisper model directory. "
            "Must contain: encoder.onnx, decoder.onnx, tokens.txt. "
            "Download: scripts/download-whisper-model.sh"
        ),
    )

    voice_stt_num_threads: int = Field(
        default=VOICE_STT_NUM_THREADS_DEFAULT,
        ge=1,
        le=16,
        description="CPU threads for STT transcription. "
        "Recommended: 2 for Raspberry Pi, 4 for desktop.",
    )

    voice_stt_language: str = Field(
        default=VOICE_STT_LANGUAGE_DEFAULT,
        description=(
            "Language hint for Whisper transcription (ISO 639-1 code). "
            "Empty = auto-detect. Examples: 'fr', 'en', 'de', 'es', 'it', 'zh'."
        ),
    )

    voice_stt_task: str = Field(
        default=VOICE_STT_TASK_DEFAULT,
        description=("Whisper task: 'transcribe' (same language) or 'translate' (to English)."),
    )

    voice_stt_max_duration_seconds: int = Field(
        default=VOICE_STT_MAX_DURATION_SECONDS_DEFAULT,
        ge=5,
        le=300,
        description="Maximum audio duration per transcription request (seconds). "
        "Longer audio is rejected to prevent memory exhaustion.",
    )

    # ========================================================================
    # WebSocket STT Configuration
    # ========================================================================

    voice_ws_ticket_ttl_seconds: int = Field(
        default=VOICE_WS_TICKET_TTL_SECONDS_DEFAULT,
        ge=10,
        le=300,
        description="WebSocket auth ticket TTL (seconds). Tickets are single-use. "
        "Short TTL (60s) minimizes replay attack window.",
    )

    voice_ws_rate_limit_max_calls: int = Field(
        default=VOICE_WS_RATE_LIMIT_MAX_CALLS_DEFAULT,
        ge=1,
        le=100,
        description="Max WebSocket connections per user per minute. "
        "Prevents abuse of transcription resources.",
    )

    voice_ws_rate_limit_window_seconds: int = Field(
        default=VOICE_WS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Rate limit window for WebSocket connections (seconds).",
    )

    voice_ws_idle_timeout_seconds: int = Field(
        default=VOICE_WS_IDLE_TIMEOUT_SECONDS_DEFAULT,
        ge=30,
        le=600,
        description="Close WebSocket after N seconds of inactivity. "
        "Prevents resource leaks from abandoned connections.",
    )

    # ========================================================================
    # ElevenLabs Scribe STT (Remote — paid, audio-billed)
    # ========================================================================
    # Active when the user opts into ``voice_stt_mode='remote'``. The API key
    # itself is stored encrypted in ``provider_api_keys`` and the active model
    # plus per-row ``base_url`` (regional residency override) and
    # ``timeout_seconds`` live in ``llm_config_overrides.voice_transcription``.
    # These two settings cover only the global remote-STT kill switch and the
    # cost-spike duration cap, both enforced at the WebSocket entry point.

    elevenlabs_stt_enabled: bool = Field(
        default=True,
        description="Allow ElevenLabs Scribe as a remote STT provider. "
        "Disable to force every user back to the local Sherpa pipeline.",
    )

    elevenlabs_stt_max_audio_duration_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Hard cap on a single STT call duration (seconds). "
        "Defends against accidental cost spikes; ElevenLabs accepts much "
        "longer files but a 5-minute conversational clip is plenty.",
    )
