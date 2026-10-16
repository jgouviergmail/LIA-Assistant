"""What each speech-synthesis provider offers, declared once (the ADR-305 shape).

A TTS provider differs from the next in three ways that matter to a caller:
how it BILLS (per character sent, per UTF-8 byte sent, per token produced, or
not at all — :func:`billed_text_units`), which delivery CONTROLS it accepts per
call (some only on the models measured to take them — :func:`controls_for`),
and whether one voice speaks every language. Every reader asks this table,
never the provider's name: the cost recorder (a token-billed engine priced per
character was under-billed about a hundred times, a byte-billed one priced per
character under-bills a Chinese line three times), the delivery seam (a control
a provider cannot express is dropped and counted, never sent), and the cast
editor (a multilingual voice needs no per-language entry).

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
    #: Per UTF-8 byte sent (the catalogue prices bytes as input tokens): a
    #: character outside ASCII costs two to four units, not one.
    UTF8_BYTES = "utf8_bytes"
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
        dialogue_models: The models, by name prefix, that voice several
            speakers in ONE request and say where each turn starts (ADR-345).
    """

    provider: str
    billing: TtsBilling
    controls: frozenset[TtsControl]
    multilingual_voices: bool
    native_format: str
    model_controls: tuple[tuple[str, frozenset[TtsControl]], ...] = ()
    dialogue_models: tuple[str, ...] = ()


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
    # Measured 2026-10-13 on s2.1-pro-free (ADR-345): billed per million UTF-8
    # bytes of text, a speaking rate in [0.5, 2.0] on every model, and any voice
    # speaks every language (the vendor detects the language from the text).
    # The S2 models and drama-3 voice a dialogue in one request, timed word by
    # word (measured on s2.1-pro-free, documented for drama-3); s1 does not.
    "fishaudio": TtsFamily(
        provider="fishaudio",
        billing=TtsBilling.UTF8_BYTES,
        controls=frozenset({TtsControl.SPEED}),
        multilingual_voices=True,
        native_format="mp3",
        dialogue_models=("s2", "drama-3"),
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


def voices_dialogue(provider: str, model: str) -> bool:
    """Whether ``model`` of ``provider`` voices several speakers in one timed request."""
    family = family_of(provider)
    return family is not None and model.startswith(family.dialogue_models)


def billed_text_units(provider: str, text: str) -> int | None:
    """The units a synthesis of ``text`` is billed on, counted from the text.

    Args:
        provider: LIA's provider id — of the client that SPOKE, never of the
            configured engine it may have stood in for.
        text: What was sent.

    Returns:
        ``0`` for a free engine; the UTF-8 byte count for a byte-billed one;
        ``None`` for a token-billed one, whose units only its own usage report
        states; the character count otherwise — an engine no family declares
        is priced like the most common case rather than as free, because an
        invisible cost is the wrong way to be wrong.
    """
    family = family_of(provider)
    billing = family.billing if family is not None else TtsBilling.CHARACTERS
    if billing is TtsBilling.FREE:
        return 0
    if billing is TtsBilling.TOKENS:
        return None
    if billing is TtsBilling.UTF8_BYTES:
        return len(text.encode("utf-8"))
    return len(text)


__all__ = [
    "TTS_FAMILIES",
    "TtsBilling",
    "TtsControl",
    "TtsFamily",
    "billed_text_units",
    "controls_for",
    "family_of",
    "voices_dialogue",
]
