"""
TTS Client Protocol.

Defines the interface that all TTS providers must implement.
Follows the same pattern as LLM providers for consistency.

Created: 2026-01-15
"""

from collections.abc import Sequence
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


@dataclass(frozen=True, slots=True)
class DialogueTurn:
    """One speaker's turn in a dialogue voiced in one request (ADR-345).

    Attributes:
        voice: The provider voice id that speaks it.
        words: What is said — the vendor's timing is read against these words.
        cue: A direction opening the turn, already spelled for the engine; it
            is performed, never timed.
    """

    voice: str
    words: str
    cue: str = ""


@dataclass(frozen=True, slots=True)
class DialogueAudio:
    """A dialogue's audio, what the vendor billed, and where each turn starts.

    Attributes:
        audio: Every turn, in order, in the client's container.
        sent_text: The text the request carried — markers, cues and words: the
            vendor bills it whole.
        turn_starts_s: When each turn's first word starts, in seconds; ``None``
            when the vendor's timing could not place every turn.
    """

    audio: bytes
    sent_text: str
    turn_starts_s: tuple[float, ...] | None


@runtime_checkable
class DialogueTTSClient(TTSClient, Protocol):
    """A client that voices several speakers in one request, and times each turn."""

    async def synthesize_dialogue(
        self, turns: Sequence[DialogueTurn], **kwargs: object
    ) -> DialogueAudio:
        """Voice ``turns`` in one request.

        Args:
            turns: The turns, in order (at least one).
            **kwargs: The per-call delivery controls shared by every turn.

        Returns:
            The audio and each turn's start.
        """
        ...
