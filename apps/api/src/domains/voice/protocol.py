"""
TTS Client Protocol.

Defines the interface that all TTS providers must implement.
Follows the same pattern as LLM providers for consistency.

Created: 2026-01-15
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSClient(Protocol):
    """
    Protocol for TTS (Text-to-Speech) clients.

    All TTS providers must implement this interface to be compatible
    with the VoiceCommentService.

    Implementations:
    - EdgeTTSClient: Microsoft Edge TTS (free, neural voices)
    - OpenAITTSClient: OpenAI TTS API (paid, high quality)
    """

    async def synthesize(
        self,
        text: str,
        voice_name: str | None = None,
        **kwargs: object,
    ) -> bytes:
        """
        Synthesize text to audio bytes.

        Args:
            text: Text to synthesize.
            voice_name: Voice identifier (provider-specific).
            **kwargs: Provider-specific parameters.

        Returns:
            Raw audio bytes (format depends on provider config).

        Raises:
            Exception: If synthesis fails.
        """
        ...

    async def synthesize_base64(
        self,
        text: str,
        voice_name: str | None = None,
        **kwargs: object,
    ) -> str:
        """
        Synthesize text to base64-encoded audio.

        Convenience method for streaming to frontend.

        Args:
            text: Text to synthesize.
            voice_name: Voice identifier (provider-specific).
            **kwargs: Provider-specific parameters.

        Returns:
            Base64-encoded audio string.
        """
        ...

    async def close(self) -> None:
        """
        Close and cleanup resources.

        Should be called when the client is no longer needed.
        """
        ...

    @property
    def provider_name(self) -> str:
        """
        Get the provider name for logging and metrics.

        Returns:
            Provider identifier (e.g., "edge", "openai").
        """
        ...

    @property
    def audio_format(self) -> str:
        """
        Get the audio format produced by this provider.

        Returns:
            MIME type suffix (e.g., "mp3", "opus").
        """
        ...
