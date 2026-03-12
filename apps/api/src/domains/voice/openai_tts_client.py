"""
OpenAI TTS Client.

Provides TTS synthesis using OpenAI's text-to-speech API.
Implements the TTSClient protocol for multi-provider support.

Uses generic TTS configuration keys:
- VOICE_TTS_MODEL: tts-1 or tts-1-hd
- VOICE_TTS_SPEED: 0.25 to 4.0
- VOICE_TTS_RESPONSE_FORMAT: mp3, opus, etc.
- VOICE_TTS_VOICE_MALE / VOICE_TTS_VOICE_FEMALE: voice selection by gender

Documentation: https://platform.openai.com/docs/guides/text-to-speech
Voices: alloy, echo, fable, onyx, nova, shimmer

Created: 2026-01-15
Updated: 2026-01-15 - Use generic TTS config keys
"""

import base64
import time
from typing import Literal

import structlog
from openai import AsyncOpenAI

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.observability.metrics_voice import (
    voice_tts_errors_total,
    voice_tts_latency_seconds,
    voice_tts_requests_total,
)

logger = structlog.get_logger(__name__)

# Type aliases for OpenAI TTS
OpenAITTSModel = Literal["tts-1", "tts-1-hd"]
OpenAITTSVoice = Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
OpenAITTSFormat = Literal["mp3", "opus", "aac", "flac", "wav", "pcm"]


class OpenAITTSClient:
    """
    OpenAI TTS Client using OpenAI's audio.speech API.

    High-quality text-to-speech with natural sounding voices.
    Requires OPENAI_API_KEY environment variable.
    Implements the TTSClient protocol.

    Example:
        client = OpenAITTSClient()
        audio_bytes = await client.synthesize(
            text="Hello, how can I help you today?",
            voice_name="nova",
        )

    Pricing (as of 2025):
        - tts-1: $15.00 / 1M characters
        - tts-1-hd: $30.00 / 1M characters
    """

    def __init__(
        self,
        model: str | None = None,
        speed: float | None = None,
        response_format: OpenAITTSFormat | None = None,
    ) -> None:
        """
        Initialize OpenAI TTS client.

        All parameters should be provided by the factory (get_tts_client)
        which reads from the appropriate HD mode settings.

        Args:
            model: TTS model (tts-1 or tts-1-hd). Defaults to "tts-1".
            speed: Speaking speed (0.25 to 4.0). Defaults to 1.0.
            response_format: Audio format (mp3, opus, etc.). Defaults to "mp3".
        """
        self.model: str = model or "tts-1"
        self.speed = speed if speed is not None else 1.0
        self.response_format: OpenAITTSFormat = response_format or "mp3"

        # Initialize async OpenAI client
        self._client = AsyncOpenAI(api_key=LLMConfigOverrideCache.get_api_key("openai") or "")

    @property
    def provider_name(self) -> str:
        """Get the provider name for logging and metrics."""
        return "openai"

    @property
    def audio_format(self) -> str:
        """Get the audio format produced by this provider."""
        return self.response_format

    async def synthesize(
        self,
        text: str,
        voice_name: str | None = None,
        model: str | None = None,
        speed: float | None = None,
        response_format: OpenAITTSFormat | None = None,
        **kwargs: object,
    ) -> bytes:
        """
        Synthesize text to audio using OpenAI TTS API.

        Args:
            text: Text to synthesize.
            voice_name: OpenAI voice name (alloy, echo, fable, onyx, nova, shimmer).
                       Required - should come from voice_tts_voice_male/female.
            model: TTS model (overrides instance default).
            speed: Speaking speed (overrides instance default).
            response_format: Audio format (overrides instance default).
            **kwargs: Additional arguments (ignored for compatibility).

        Returns:
            Raw audio bytes in the configured format.

        Raises:
            ValueError: If voice_name is not provided.
            Exception: If synthesis fails.
        """
        # Voice is required - should be provided by service based on gender
        if not voice_name:
            raise ValueError("voice_name is required for OpenAI TTS")

        voice: str = voice_name
        model = model or self.model
        speed = speed if speed is not None else self.speed
        response_format = response_format or self.response_format

        logger.debug(
            "openai_tts_request",
            text_length=len(text),
            voice=voice,
            model=model,
            speed=speed,
            response_format=response_format,
        )

        # Track request timing
        request_start_time = time.time()

        try:
            # Call OpenAI TTS API
            response = await self._client.audio.speech.create(
                model=model,
                voice=voice,
                input=text,
                speed=speed,
                response_format=response_format,
            )

            # Get audio bytes from response
            audio_bytes = response.content

            if not audio_bytes:
                voice_tts_errors_total.labels(error_type="empty_response", voice_name=voice).inc()
                raise ValueError("No audio content from OpenAI TTS")

            # Track successful request metrics
            request_duration = time.time() - request_start_time
            voice_tts_latency_seconds.labels(voice_name=voice).observe(request_duration)
            voice_tts_requests_total.labels(status="success", voice_name=voice).inc()

            logger.debug(
                "openai_tts_success",
                text_length=len(text),
                audio_bytes=len(audio_bytes),
                voice=voice,
                model=model,
                latency_ms=int(request_duration * 1000),
            )

            return audio_bytes

        except Exception as e:
            # Track error metrics
            request_duration = time.time() - request_start_time
            voice_tts_latency_seconds.labels(voice_name=voice).observe(request_duration)
            voice_tts_requests_total.labels(status="error", voice_name=voice).inc()

            # Categorize error type
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str:
                error_type = "rate_limit"
            elif "auth" in error_str or "key" in error_str:
                error_type = "auth_error"
            elif "connect" in error_str or "timeout" in error_str:
                error_type = "network_error"
            else:
                error_type = "synthesis_error"

            voice_tts_errors_total.labels(error_type=error_type, voice_name=voice).inc()

            logger.error(
                "openai_tts_error",
                error=str(e),
                error_type=type(e).__name__,
                text_length=len(text),
                voice=voice,
                model=model,
            )
            raise

    async def synthesize_base64(
        self,
        text: str,
        voice_name: str | None = None,
        model: str | None = None,
        speed: float | None = None,
        response_format: OpenAITTSFormat | None = None,
        **kwargs: object,
    ) -> str:
        """
        Synthesize text to base64-encoded audio.

        Convenience method that returns base64 string directly.

        Args:
            text: Text to synthesize.
            voice_name: OpenAI voice name (required).
            model: TTS model (overrides instance default).
            speed: Speaking speed (overrides instance default).
            response_format: Audio format (overrides instance default).
            **kwargs: Additional arguments (ignored for compatibility).

        Returns:
            Base64-encoded audio string.
        """
        audio_bytes = await self.synthesize(
            text=text,
            voice_name=voice_name,
            model=model,
            speed=speed,
            response_format=response_format,
        )
        return base64.b64encode(audio_bytes).decode("utf-8")

    async def close(self) -> None:
        """Close resources (cleanup for OpenAI client)."""
        # AsyncOpenAI client handles cleanup internally
        await self._client.close()

    @staticmethod
    def list_voices() -> list[dict]:
        """
        List available OpenAI TTS voices.

        Returns:
            List of voice dictionaries with name and description.
        """
        return [
            {
                "name": "alloy",
                "description": "Neutral, balanced voice",
                "gender": "neutral",
            },
            {
                "name": "echo",
                "description": "Male voice, warm and natural",
                "gender": "male",
            },
            {
                "name": "fable",
                "description": "British accent, storytelling style",
                "gender": "neutral",
            },
            {
                "name": "onyx",
                "description": "Deep male voice, authoritative",
                "gender": "male",
            },
            {
                "name": "nova",
                "description": "Warm female voice, friendly",
                "gender": "female",
            },
            {
                "name": "shimmer",
                "description": "Soft female voice, gentle",
                "gender": "female",
            },
        ]
