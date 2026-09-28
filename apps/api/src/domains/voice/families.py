"""What each speech-synthesis provider offers, declared once (the ADR-305 shape).

A TTS provider differs from the next in three ways that matter to a caller:
how it BILLS (per character sent, per token produced, or not at all), which
delivery CONTROLS it accepts per call (some only on the models measured to take
them — :func:`controls_for`), and whether one voice speaks every
language. Every reader asks this table, never the provider's name: the cost
recorder (a token-billed engine priced per character was under-billed about a
hundred times), the delivery seam (a control a provider cannot express is
dropped and counted, never sent), and the cast editor (a multilingual voice
needs no per-language entry).

A provider absent from the table is NOT SERVED: no client exists for it, and
nothing may pretend otherwise — the silent fallback to another engine that a
Gemini model configured without a client used to get is exactly that pretence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class TtsBilling(StrEnum):
    """How a provider charges a synthesis."""

    #: A local or free engine: nothing is recorded.
    FREE = "free"
    #: Per character sent (the catalogue prices characters as input tokens).
    CHARACTERS = "characters"
    #: Per token: text in, audio out, as the vendor's usage report states them.
    TOKENS = "tokens"


class TtsControl(StrEnum):
    """A delivery control a provider accepts per call."""

    #: Edge SSML prosody: speaking rate, pitch and volume offsets.
    RATE = "rate"
    PITCH = "pitch"
    VOLUME = "volume"
    #: OpenAI's speaking speed multiplier.
    SPEED = "speed"
    #: ElevenLabs' stability / style block.
    VOICE_SETTINGS = "voice_settings"
    #: A natural-language direction of how the line should sound (Gemini).
    STYLE_PROMPT = "style_prompt"


@dataclass(frozen=True, slots=True)
class TtsFamily:
    """What one provider offers.

    Attributes:
        provider: LIA's provider id.
        billing: How a synthesis is charged.
        controls: The per-call delivery controls EVERY model of it accepts.
        multilingual_voices: Whether every voice speaks every language (the
            cast then needs one voice per role, not one per role and language).
        native_format: The container the provider returns (``mp3`` or ``wav``).
        model_controls: Controls only some of its models accept, by model-name
            prefix (a dated release inherits its model's). A control is sent to
            a model that matches and to no other: refused, it fails the WHOLE
            synthesis; withheld, the line only loses its nuance.
    """

    provider: str
    billing: TtsBilling
    controls: frozenset[TtsControl]
    multilingual_voices: bool
    native_format: str
    model_controls: tuple[tuple[str, frozenset[TtsControl]], ...] = ()


TTS_FAMILIES: Final[dict[str, TtsFamily]] = {
    "edge": TtsFamily(
        provider="edge",
        billing=TtsBilling.FREE,
        controls=frozenset({TtsControl.RATE, TtsControl.PITCH, TtsControl.VOLUME}),
        multilingual_voices=False,
        native_format="mp3",
    ),
    "openai": TtsFamily(
        provider="openai",
        billing=TtsBilling.CHARACTERS,
        controls=frozenset({TtsControl.SPEED}),
        multilingual_voices=True,
        native_format="mp3",
    ),
    "elevenlabs": TtsFamily(
        provider="elevenlabs",
        billing=TtsBilling.CHARACTERS,
        controls=frozenset({TtsControl.VOICE_SETTINGS}),
        multilingual_voices=True,
        native_format="mp3",
    ),
    "gemini": TtsFamily(
        provider="gemini",
        billing=TtsBilling.TOKENS,
        controls=frozenset(),
        multilingual_voices=True,
        native_format="wav",
        # Measured 2026-09-26 on the Interactions API, the same line with and
        # without a ``speech_metadata`` style: the 3.8 models take it; the 2.5
        # previews and the 3.1 preview answer 400 to ANY annotation — a radio
        # voiced by one of them aired no line at all.
        model_controls=(
            ("gemini-3.8-flash-tts", frozenset({TtsControl.STYLE_PROMPT})),
            ("gemini-3.8-flash-lite-tts", frozenset({TtsControl.STYLE_PROMPT})),
        ),
    ),
}


def family_of(provider: str) -> TtsFamily | None:
    """The family serving ``provider``, or ``None`` when no client serves it."""
    return TTS_FAMILIES.get(provider)


def controls_for(provider: str, model: str) -> frozenset[TtsControl]:
    """The delivery controls ``model`` of ``provider`` accepts per call.

    Args:
        provider: LIA's provider id.
        model: The model, as the provider names it.

    Returns:
        What every model of the family accepts, plus what the model's declared
        prefix adds; nothing for a provider no client serves.
    """
    family = family_of(provider)
    if family is None:
        return frozenset()
    declared = (controls for prefix, controls in family.model_controls if model.startswith(prefix))
    return family.controls.union(*declared)


__all__ = ["TTS_FAMILIES", "TtsBilling", "TtsControl", "TtsFamily", "controls_for", "family_of"]
