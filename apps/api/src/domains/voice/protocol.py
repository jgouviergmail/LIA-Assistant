"""
TTS Client Protocol.

Defines the interface that all TTS providers must implement.
Follows the same pattern as LLM providers for consistency.

Created: 2026-01-15
"""

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class RawAudioSpec:
    """The mono samples of a headerless TTS response.

    PCM is signed 16-bit little-endian; u-law has one byte per sample. A
    consumer needs the client's rate to put either in a readable container.
    """

    sample_rate: int
    encoding: Literal["pcm_s16le", "ulaw"] = "pcm_s16le"


@runtime_checkable
class RawAudioTTSClient(Protocol):
    """Optional metadata supplied by a client which can return raw samples."""

    @property
    def raw_audio_spec(self) -> RawAudioSpec | None:
        """Describe the configured raw response; None for an encoded container."""
        ...


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
