"""A synthesis and what it costs, in one result.

The TTS protocol returns audio bytes and nothing else, which is enough for a
provider that bills per character sent: the caller knows the characters. It is
not enough for a provider that bills the TOKENS it produced (Gemini: audio
output tokens, about 35 per second of speech, measured 2026-09-26): only the
provider's usage report knows them. A client that can report usage implements
:class:`UsageReportingTTSClient`; :func:`synthesize_billed` is the one door a
billing-aware caller goes through, whatever the client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.domains.voice.protocol import TTSClient


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """The audio of one synthesis, and the units it is billed on.

    Attributes:
        audio: The encoded audio.
        characters: Characters sent (always known).
        input_tokens: Text tokens the vendor counted, when it bills tokens.
        output_tokens: Audio tokens the vendor produced, when it bills tokens.
    """

    audio: bytes
    characters: int
    input_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class UsageReportingTTSClient(Protocol):
    """A client whose provider reports the tokens it bills."""

    async def synthesize_with_usage(
        self, text: str, voice_name: str | None = None, **kwargs: object
    ) -> SynthesisResult:
        """Synthesize and return the audio with the vendor's usage."""
        ...


async def synthesize_billed(
    client: TTSClient, text: str, voice_name: str | None = None, **kwargs: object
) -> SynthesisResult:
    """Synthesize through any client and say what the call is billed on.

    Args:
        client: The TTS client.
        text: What to say.
        voice_name: Provider voice id.
        **kwargs: Per-call delivery controls, passed through.

    Returns:
        The audio and its billing units.
    """
    if isinstance(client, UsageReportingTTSClient):
        return await client.synthesize_with_usage(text, voice_name, **kwargs)
    audio = await client.synthesize(text, voice_name, **kwargs)
    return SynthesisResult(audio=audio, characters=len(text))


__all__ = ["SynthesisResult", "UsageReportingTTSClient", "synthesize_billed"]
