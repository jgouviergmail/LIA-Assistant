"""
Voice configuration module (Text-to-Speech and Speech-to-Text).

Contains settings for:
- TTS Mode selection (Standard/HD) - Admin-controlled global setting
- TTS Standard mode parameters (Edge TTS: free, high quality)
- TTS HD mode parameters (OpenAI/Gemini: paid, premium quality)
- Voice comment LLM (model, temperature, max tokens, provider, reasoning_effort)
- STT configuration (Sherpa-onnx: offline, multi-language, free)
- WebSocket STT settings (ticket auth, rate limiting, timeouts)

Phase: Voice Feature Implementation
Created: 2025-12-24
Updated: 2025-12-29 - Migrated from Google Cloud TTS to Edge TTS
Updated: 2026-01-15 - Aligned LLM config with standard pattern (provider_config, reasoning_effort)
Updated: 2026-01-15 - Added multi-provider TTS support with generic config keys
Updated: 2026-01-16 - Refactored to Standard/HD mode architecture (admin-controlled)
Updated: 2026-02-01 - Added STT configuration (Sherpa-onnx Whisper Small INT8)
"""

from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Type alias for voice quality mode
VoiceTTSMode = Literal["standard", "hd"]


class VoiceSettings(BaseSettings):
    """Voice (TTS) settings for generating audio comments."""

    # ========================================================================
    # TTS Mode Selection (Admin-controlled)
    # ========================================================================
    # The active mode is stored in the database (SystemSettings table) and
    # controlled by administrators. This env var sets the default mode when
    # no database setting exists yet.
    #
    # - standard: Free, high quality (Edge TTS)
    # - hd: Premium quality, paid (OpenAI/Gemini TTS)
    # ========================================================================

    voice_tts_default_mode: VoiceTTSMode = Field(
        default="standard",
        description=(
            "Default TTS mode when no admin setting exists. "
            "standard = Edge TTS (free), hd = OpenAI/Gemini TTS (paid)"
        ),
    )

    # ========================================================================
    # STANDARD MODE Configuration (Edge TTS - Free)
    # ========================================================================
    # Microsoft Edge neural voices - free, high quality
    # Voices: fr-FR-RemyMultilingualNeural, en-US-AriaNeural, etc.
    # ========================================================================

    voice_tts_standard_provider: Literal["edge"] = Field(
        default="edge",
        description="TTS provider for Standard mode (edge = Microsoft Edge TTS)",
    )

    voice_tts_standard_voice_male: str = Field(
        default="fr-FR-RemyMultilingualNeural",
        description=(
            "Standard mode male voice. "
            "Edge voices: fr-FR-RemyMultilingualNeural, en-US-GuyNeural, etc."
        ),
    )

    voice_tts_standard_voice_female: str = Field(
        default="fr-FR-VivienneMultilingualNeural",
        description=(
            "Standard mode female voice. "
            "Edge voices: fr-FR-VivienneMultilingualNeural, en-US-AriaNeural, etc."
        ),
    )

    voice_tts_standard_rate: str = Field(
        default="+10%",
        description=(
            "Standard mode (Edge TTS) speaking rate adjustment. "
            "Examples: '+10%' (faster), '-5%' (slower), '+0%' (normal)"
        ),
    )

    voice_tts_standard_pitch: str = Field(
        default="+0Hz",
        description=(
            "Standard mode (Edge TTS) voice pitch adjustment. "
            "Examples: '+5Hz' (higher), '-10Hz' (lower), '+0Hz' (normal)"
        ),
    )

    voice_tts_standard_volume: str = Field(
        default="+0%",
        description=(
            "Standard mode (Edge TTS) volume adjustment. "
            "Examples: '+10%' (louder), '-5%' (quieter), '+0%' (normal)"
        ),
    )

    # ========================================================================
    # HD MODE Configuration (OpenAI/Gemini TTS - Paid)
    # ========================================================================
    # Premium TTS providers - paid, highest quality
    # OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
    # Gemini voices: Kore, Puck, Charon, etc.
    # ========================================================================

    voice_tts_hd_provider: Literal["openai", "gemini"] = Field(
        default="openai",
        description=(
            "TTS provider for HD mode. " "openai = OpenAI TTS API, gemini = Google Gemini TTS"
        ),
    )

    voice_tts_hd_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for HD TTS (JSON string)",
    )

    voice_tts_hd_voice_male: str = Field(
        default="onyx",
        description=(
            "HD mode male voice. "
            "OpenAI: onyx (deep), echo (warm). "
            "Gemini: Charon (informative), Puck (upbeat)"
        ),
    )

    voice_tts_hd_voice_female: str = Field(
        default="nova",
        description=(
            "HD mode female voice. "
            "OpenAI: nova (warm), shimmer (soft), alloy (neutral). "
            "Gemini: Kore (firm), Aoede (warm)"
        ),
    )

    voice_tts_hd_model: str = Field(
        default="tts-1",
        description=(
            "HD mode TTS model. "
            "OpenAI: tts-1 (faster/cheaper), tts-1-hd (higher quality). "
            "Gemini: gemini-2.5-flash-tts, gemini-2.5-pro-tts"
        ),
    )

    voice_tts_hd_speed: float = Field(
        default=1.0,
        ge=0.25,
        le=4.0,
        description="HD mode speaking speed (0.25 to 4.0). 1.0 = normal speed.",
    )

    voice_tts_hd_response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = Field(
        default="mp3",
        description=(
            "HD mode audio output format. "
            "mp3 = best compatibility, opus = smaller size, wav = uncompressed"
        ),
    )

    # ========================================================================
    # Voice Comment LLM Configuration
    # ========================================================================
    # Follows standard LLM configuration pattern (see llm.py for reference)
    # All parameters configurable via VOICE_LLM_* environment variables
    # ========================================================================

    voice_llm_provider: Literal[
        "openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini"
    ] = Field(
        default="openai",
        description="LLM provider for voice comment generation",
    )

    voice_llm_provider_config: str = Field(
        default="{}",
        description="Advanced provider-specific config for voice LLM (JSON string)",
    )

    voice_llm_model: str = Field(
        default="gpt-4.1-nano",
        description="LLM model for voice comment generation (fast, cheap model recommended)",
    )

    voice_llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="LLM temperature for voice comments (0.7 = creative but controlled)",
    )

    voice_llm_top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling for voice LLM (1.0 = disabled)",
    )

    voice_llm_frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Frequency penalty for voice LLM (reduce repetition)",
    )

    voice_llm_presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Presence penalty for voice LLM (encourage diversity)",
    )

    voice_llm_max_tokens: int = Field(
        default=500,
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
        default=6,
        ge=1,
        le=10,
        description="Maximum number of sentences in voice comment",
    )

    voice_sentence_delimiters: str = Field(
        default=".!?",
        description="Characters that mark end of sentence for TTS chunking",
    )

    # ========================================================================
    # Voice Context Configuration
    # ========================================================================
    voice_context_max_chars: int = Field(
        default=2000,
        gt=0,
        le=10000,
        description="Maximum characters for voice context (truncation limit for fallback)",
    )

    voice_parallel_timeout_seconds: float = Field(
        default=15.0,
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
        default=3,
        ge=1,
        le=6,
        description="Max sentences to TTS in chat mode direct TTS. "
        "Chat responses don't need full commentary.",
    )

    # ========================================================================
    # STT (Speech-to-Text) Configuration - Sherpa-onnx Whisper
    # ========================================================================
    # Offline, multi-language STT using Whisper Small INT8 model.
    # 100% free, no API costs. Supports: 99+ languages (FR/EN/DE/ES/IT/ZH/...).
    # Model: csukuangfj/sherpa-onnx-whisper-small (~375 MB INT8)
    # Reference: domains/voice/stt/, plan zippy-drifting-valley.md
    # ========================================================================

    voice_stt_enabled: bool = Field(
        default=True,
        description="Enable Speech-to-Text via WebSocket /ws/audio. "
        "Requires Sherpa-onnx Whisper model to be installed.",
    )

    voice_stt_model_path: str = Field(
        default="/models/whisper-small",
        description=(
            "Path to Sherpa-onnx Whisper model directory. "
            "Must contain: encoder.onnx, decoder.onnx, tokens.txt. "
            "Download: scripts/download-whisper-model.sh"
        ),
    )

    voice_stt_num_threads: int = Field(
        default=4,
        ge=1,
        le=16,
        description="CPU threads for STT transcription. "
        "Recommended: 2 for Raspberry Pi, 4 for desktop.",
    )

    voice_stt_language: str = Field(
        default="",
        description=(
            "Language hint for Whisper transcription (ISO 639-1 code). "
            "Empty = auto-detect. Examples: 'fr', 'en', 'de', 'es', 'it', 'zh'."
        ),
    )

    voice_stt_task: str = Field(
        default="transcribe",
        description=("Whisper task: 'transcribe' (same language) or 'translate' (to English)."),
    )

    voice_stt_max_duration_seconds: int = Field(
        default=60,
        ge=5,
        le=300,
        description="Maximum audio duration per transcription request (seconds). "
        "Longer audio is rejected to prevent memory exhaustion.",
    )

    # ========================================================================
    # WebSocket STT Configuration
    # ========================================================================

    voice_ws_ticket_ttl_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="WebSocket auth ticket TTL (seconds). Tickets are single-use. "
        "Short TTL (60s) minimizes replay attack window.",
    )

    voice_ws_rate_limit_max_calls: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Max WebSocket connections per user per minute. "
        "Prevents abuse of transcription resources.",
    )

    voice_ws_rate_limit_window_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Rate limit window for WebSocket connections (seconds).",
    )

    voice_ws_idle_timeout_seconds: int = Field(
        default=120,
        ge=30,
        le=600,
        description="Close WebSocket after N seconds of inactivity. "
        "Prevents resource leaks from abandoned connections.",
    )
