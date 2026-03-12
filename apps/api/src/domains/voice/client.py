"""
Edge TTS Client.

Provides TTS synthesis using Microsoft Edge neural voices (free).
Uses the edge-tts library for streaming audio synthesis.
Implements the TTSClient protocol for multi-provider support.

Documentation: https://github.com/rany2/edge-tts
Voices: Run `edge-tts --list-voices` to see all available voices.

Recommended French voices (Multilingual = highest quality):
- fr-FR-RemyMultilingualNeural (male)
- fr-FR-VivienneMultilingualNeural (female)

Updated: 2026-01-15 - Implements TTSClient protocol for multi-provider support
"""

import base64
import io
import time

import edge_tts
import structlog

from src.infrastructure.observability.metrics_voice import (
    voice_tts_errors_total,
    voice_tts_latency_seconds,
    voice_tts_requests_total,
)

logger = structlog.get_logger(__name__)


class EdgeTTSClient:
    """
    Edge TTS Client using Microsoft neural voices.

    Free, high-quality text-to-speech using the same voices as Microsoft Edge.
    No API key required - uses public Microsoft Edge TTS endpoints.
    Implements the TTSClient protocol.

    Example:
        client = EdgeTTSClient()
        audio_bytes = await client.synthesize(
            text="Bonjour, comment puis-je vous aider?",
            voice_name="fr-FR-RemyMultilingualNeural",
        )
    """

    def __init__(
        self,
        rate: str | None = None,
        pitch: str | None = None,
        volume: str | None = None,
    ) -> None:
        """
        Initialize Edge TTS client.

        All parameters should be provided by the factory (get_tts_client)
        which reads from the appropriate Standard mode settings.

        Args:
            rate: Speaking rate adjustment (e.g., "+10%", "-5%", "+0%"). Defaults to "+0%".
            pitch: Voice pitch adjustment (e.g., "+5Hz", "-10Hz", "+0Hz"). Defaults to "+0Hz".
            volume: Volume adjustment (e.g., "+10%", "-5%", "+0%"). Defaults to "+0%".
        """
        self.rate = rate or "+0%"
        self.pitch = pitch or "+0Hz"
        self.volume = volume or "+0%"

    @property
    def provider_name(self) -> str:
        """Get the provider name for logging and metrics."""
        return "edge"

    @property
    def audio_format(self) -> str:
        """Get the audio format produced by this provider."""
        return "mp3"

    async def synthesize(
        self,
        text: str,
        voice_name: str | None = None,
        rate: str | None = None,
        pitch: str | None = None,
        volume: str | None = None,
        **kwargs: object,
    ) -> bytes:
        """
        Synthesize text to audio using Edge TTS.

        Args:
            text: Text to synthesize.
            voice_name: Edge TTS voice name (e.g., "fr-FR-RemyMultilingualNeural").
            rate: Speaking rate adjustment (overrides instance default).
            pitch: Voice pitch adjustment (overrides instance default).
            volume: Volume adjustment (overrides instance default).
            **kwargs: Additional arguments (ignored for compatibility).

        Returns:
            Raw audio bytes (MP3 format).

        Raises:
            Exception: If synthesis fails.
        """
        # kwargs is ignored for Edge TTS but accepted for protocol compatibility
        _ = kwargs
        # Voice name is required - should be provided by service
        if not voice_name:
            raise ValueError("voice_name is required for Edge TTS")
        rate = rate or self.rate
        pitch = pitch or self.pitch
        volume = volume or self.volume

        logger.debug(
            "edge_tts_request",
            text_length=len(text),
            voice_name=voice_name,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )

        # Track request timing
        request_start_time = time.time()

        try:
            # Create Edge TTS communicator
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_name,
                rate=rate,
                pitch=pitch,
                volume=volume,
            )

            # Collect audio data from stream
            audio_buffer = io.BytesIO()

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])

            audio_bytes = audio_buffer.getvalue()

            if not audio_bytes:
                voice_tts_errors_total.labels(
                    error_type="empty_response", voice_name=voice_name
                ).inc()
                raise ValueError("No audio content from Edge TTS")

            # Track successful request metrics
            request_duration = time.time() - request_start_time
            voice_tts_latency_seconds.labels(voice_name=voice_name).observe(request_duration)
            voice_tts_requests_total.labels(status="success", voice_name=voice_name).inc()

            logger.debug(
                "edge_tts_success",
                text_length=len(text),
                audio_bytes=len(audio_bytes),
                voice_name=voice_name,
                latency_ms=int(request_duration * 1000),
            )

            return audio_bytes

        except Exception as e:
            # Track error metrics
            request_duration = time.time() - request_start_time
            voice_tts_latency_seconds.labels(voice_name=voice_name).observe(request_duration)
            voice_tts_requests_total.labels(status="error", voice_name=voice_name).inc()

            # Categorize error type
            error_type = "network_error" if "connect" in str(e).lower() else "synthesis_error"
            voice_tts_errors_total.labels(error_type=error_type, voice_name=voice_name).inc()

            logger.error(
                "edge_tts_error",
                error=str(e),
                error_type=type(e).__name__,
                text_length=len(text),
                voice_name=voice_name,
            )
            raise

    async def synthesize_base64(
        self,
        text: str,
        voice_name: str | None = None,
        rate: str | None = None,
        pitch: str | None = None,
        volume: str | None = None,
        **kwargs: object,
    ) -> str:
        """
        Synthesize text to base64-encoded audio.

        Convenience method that returns base64 string directly.

        Args:
            text: Text to synthesize.
            voice_name: Edge TTS voice name.
            rate: Speaking rate adjustment.
            pitch: Voice pitch adjustment.
            volume: Volume adjustment.
            **kwargs: Additional arguments (ignored for compatibility).

        Returns:
            Base64-encoded audio string (MP3 format).
        """
        audio_bytes = await self.synthesize(
            text=text,
            voice_name=voice_name,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        return base64.b64encode(audio_bytes).decode("utf-8")

    async def close(self) -> None:
        """Close resources (no-op for Edge TTS, kept for API compatibility)."""
        pass

    @staticmethod
    async def list_voices(language: str | None = None) -> list[dict]:
        """
        List available Edge TTS voices.

        Args:
            language: Optional language filter (e.g., "fr", "en").

        Returns:
            List of voice dictionaries with name, language, and gender.
        """
        voices = await edge_tts.list_voices()

        if language:
            # Filter by language code prefix
            voices = [v for v in voices if v.get("Locale", "").startswith(language)]

        return [
            {
                "name": v.get("ShortName"),
                "locale": v.get("Locale"),
                "gender": v.get("Gender"),
                "friendly_name": v.get("FriendlyName"),
            }
            for v in voices
        ]
