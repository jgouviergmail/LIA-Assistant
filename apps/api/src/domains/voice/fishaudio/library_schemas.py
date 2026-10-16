"""The voice library's wire shapes (ADR-345): what the page sends, and what it is told.

Every bound the API enforces is published here (ADR-184): the page offers
exactly what the routes accept.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.core.constants import (
    FISHAUDIO_DESIGN_CANDIDATES_MAX,
    FISHAUDIO_DESIGN_INSTRUCTION_MAX_CHARS,
    FISHAUDIO_DESIGN_PREVIEW_MAX_CHARS,
    FISHAUDIO_VOICE_TITLE_MAX_CHARS,
)

#: The languages a design or a transcript may be asked in: the interface's six.
LibraryLanguage = Literal["en", "fr", "de", "es", "it", "zh"]


def _words(value: str) -> str:
    """``value`` with its blanks collapsed — nothing left is no value at all."""
    words = " ".join(value.split())
    if not words:
        raise ValueError("must hold at least one non-blank character")
    return words


class LibraryVoicePayload(BaseModel):
    """One voice the account owns."""

    voice_id: str = Field(description="The vendor's model id.")
    title: str = Field(description="Its name.")
    state: str = Field(description="created, training, trained or failed (the vendor's).")
    languages: list[str] = Field(description="The languages the vendor detected.")
    created_at: str | None = Field(description="When it was created (ISO 8601), when known.")
    used_by_slots: list[str] = Field(
        description="The TTS slots speaking with it — a voice in use cannot be deleted."
    )


class VoiceLibraryBounds(BaseModel):
    """What the routes accept, published so the page offers nothing else."""

    samples_max: int = Field(description="Recordings per clone.")
    sample_max_bytes: int = Field(description="Size of one recording.")
    total_max_bytes: int = Field(description="Size of a clone's recordings together.")
    sample_extensions: list[str] = Field(description="The containers a recording may use.")
    title_max_chars: int = Field(description="Length of a voice's name.")
    instruction_max_chars: int = Field(description="Length of a design's description.")
    preview_max_chars: int = Field(description="Length of a design's preview text.")
    candidates_max: int = Field(description="Candidates one design may ask for.")
    prefill_max_seconds: int = Field(description="Longest recording the local transcript hears.")


class VoiceLibraryResponse(BaseModel):
    """The library and what the instance lets an administrator do with it."""

    configured: bool = Field(description="Whether the instance holds a Fish Audio key.")
    creation_enabled: bool = Field(description="Whether voices may be cloned or designed.")
    prefill_available: bool = Field(
        description="Whether the local engine can offer a recording's transcript."
    )
    design_cost_usd: float = Field(description="What one design costs the instance.")
    candidate_ttl_seconds: int = Field(description="How long designed voices wait to be saved.")
    voices: list[LibraryVoicePayload] = Field(description="The account's own voices.")
    bounds: VoiceLibraryBounds = Field(description="What the routes accept.")


class VoiceTitleRequest(BaseModel):
    """A voice's name."""

    title: str = Field(max_length=FISHAUDIO_VOICE_TITLE_MAX_CHARS, description="Its name.")

    @field_validator("title")
    @classmethod
    def _titled(cls, value: str) -> str:
        return _words(value)


class DesignRequest(BaseModel):
    """A voice to design from a description."""

    instruction: str = Field(
        max_length=FISHAUDIO_DESIGN_INSTRUCTION_MAX_CHARS,
        description="What the voice sounds like: age, tone, accent, pace, context.",
    )
    preview_text: str | None = Field(
        default=None,
        max_length=FISHAUDIO_DESIGN_PREVIEW_MAX_CHARS,
        description="What each candidate reads, to compare them on one line.",
    )
    language: LibraryLanguage | None = Field(
        default=None, description="The language the candidates speak, when it matters."
    )
    count: int = Field(
        default=2, ge=1, le=FISHAUDIO_DESIGN_CANDIDATES_MAX, description="How many candidates."
    )

    @field_validator("instruction")
    @classmethod
    def _described(cls, value: str) -> str:
        return _words(value)

    @field_validator("preview_text")
    @classmethod
    def _preview(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None


class DesignCandidatePayload(BaseModel):
    """One designed voice, to listen to before saving it."""

    candidate_id: str = Field(description="What a save names.")
    duration_ms: int = Field(description="How long its preview lasts.")
    text: str | None = Field(description="What its preview says, when known.")
    language: str | None = Field(description="Its preview's language, when known.")
    audio_base64: str = Field(description="Its preview, a base64 WAV file.")


class DesignResponse(BaseModel):
    """What a design answered, and what it cost the instance."""

    candidates: list[DesignCandidatePayload] = Field(description="In the vendor's order.")
    cost_usd: float = Field(description="What the request cost the instance.")
    expires_in_seconds: int = Field(description="How long the candidates wait to be saved.")


class PinVoiceRequest(BaseModel):
    """A public voice to pin, under the administrator's attestation."""

    attested: bool = Field(
        default=False,
        description=(
            "The administrator attests holding the right to use the voice (a licence, or "
            "its owner's consent); without it, nothing is pinned."
        ),
    )


class PinnedVoicesResponse(BaseModel):
    """The public voices the instance pinned, for every voice slot."""

    voice_ids: list[str] = Field(description="The pinned voice ids, in the order they were pinned.")
    max_pins: int = Field(description="How many voices may be pinned.")


class SampleTranscriptResponse(BaseModel):
    """What a recording says, as the local engine heard it."""

    text: str = Field(description="The words, to check before cloning.")


__all__ = [
    "DesignCandidatePayload",
    "DesignRequest",
    "DesignResponse",
    "LibraryLanguage",
    "LibraryVoicePayload",
    "PinVoiceRequest",
    "PinnedVoicesResponse",
    "SampleTranscriptResponse",
    "VoiceLibraryBounds",
    "VoiceLibraryResponse",
    "VoiceTitleRequest",
]
