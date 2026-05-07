"""Protocol for Speech-To-Text services (local Sherpa or remote ElevenLabs).

The voice WebSocket handler always buffers audio as raw PCM Int16 little-endian
mono at 16 kHz (the format the frontend AudioWorklet emits). Both backends
expose a single async method that accepts that buffer and returns the
transcription plus the authoritative audio duration.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class STTResult(BaseModel):
    """Outcome of a single transcription request."""

    text: str = Field(..., description="Transcribed text (may be empty if no speech)")
    audio_duration_seconds: float = Field(
        ...,
        ge=0.0,
        description="Authoritative audio duration in seconds.",
    )
    language_code: str | None = Field(
        default=None,
        description="ISO-639-1 language code returned/inferred by the provider, if any.",
    )


@runtime_checkable
class SttServiceProtocol(Protocol):
    """Common interface for any STT backend used by the voice WebSocket."""

    async def transcribe_pcm_int16_async(
        self,
        pcm_int16_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> STTResult:
        """Transcribe a raw PCM Int16 LE mono buffer.

        Args:
            pcm_int16_bytes: Raw audio samples as 16-bit signed little-endian
                bytes. Length must be even (2 bytes per sample).
            sample_rate: Sample rate in Hz. Frontend always streams at 16 kHz.
            language: Optional ISO-639-1 hint. ``None`` or empty string means
                "auto-detect".

        Returns:
            STTResult with the transcription, audio duration in seconds, and
            (when available) the resolved language code.

        Raises:
            STTProviderError: when a remote provider fails. Local backends
                may raise their own ``STTError`` family for parity with the
                pre-existing API.
        """
        ...
