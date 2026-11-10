"""How a voice session's engine expresses itself: words alone, or LIA's cues (ADR-373).

A voice that speaks through a provider's native audio (Gemini Live, GPT-Live)
carries its delivery in the words the mandate asks for: no cue is ever
offered. A voice on an ElevenLabs AGENT speaks through the engine the agent
stores, and that engine may perform audio tags written inside its words: then
LIA offers the cues of its vocabulary, spelled the engine's way, and writes
the same palette on the agent (the vendor's own expression prompt reads it).

Who is offered what is declared here, once: the person hears every cue their
personality may choose; a stranger the phone calls (a restaurant, a garage)
only the cordial ones — no persona cue, nothing familiar (owner, 2026-11-07).
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any, Final, Literal

from src.domains.voice.expressive_cues import (
    DELIVERY_CUES,
    ELEVENLABS_AGENT_TAGS,
    EVENT_CUES,
    NO_CUES,
    PERSONA_CUES,
    Cue,
    CueDialect,
)

#: How a session's voice expresses itself, as the browser is told: in words
#: alone, or with cues written inside its words (which a caption never shows).
VoiceExpression = Literal["prose", "cues"]

#: What a voice speaking to the PERSON is offered: the whole vocabulary — their
#: personality decides which cues it uses.
PERSON_CUES: Final[frozenset[Cue]] = DELIVERY_CUES | PERSONA_CUES | EVENT_CUES
#: What a voice speaking to a STRANGER is offered: cordial delivery and sounds,
#: never a persona cue, nothing over-familiar.
STRANGER_CUES: Final[frozenset[Cue]] = (DELIVERY_CUES | EVENT_CUES) - {
    Cue.EXCITED,
    Cue.WHISPERING,
    Cue.LAUGHS,
}
#: The TTS families that perform audio tags while their expressive mode is on
#: (vendor: « automatically disabled for non-v3 models »; v4 Turbo turns it on).
_TAG_ENGINES: Final[tuple[str, ...]] = ("eleven_v3", "eleven_v4")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def agent_dialect(agent: Mapping[str, Any]) -> CueDialect:
    """The dialect an ElevenLabs agent's speaking engine performs, from its stored config.

    A realtime model (``conversation_config.realtime_model``) speaks with
    audio tags: the vendor manages its speech model and expressive mode, and
    applied the suggested tags on the owner's agent (measured 2026-11-07).
    Otherwise the TTS model decides: a v3 or v4 model performs tags unless the
    person switched its expressive mode off. Anything else — or a
    configuration LIA cannot read — is words alone: a cue LIA cannot prove
    the engine performs is never offered.

    Args:
        agent: The agent as ``GET /v1/convai/agents/{id}`` serves it.

    Returns:
        :data:`ELEVENLABS_AGENT_TAGS` or :data:`NO_CUES`.
    """
    config = _mapping(agent.get("conversation_config"))
    realtime = config.get("realtime_model")
    if isinstance(realtime, str) and realtime:
        return ELEVENLABS_AGENT_TAGS
    tts = _mapping(config.get("tts"))
    model = tts.get("model_id")
    if tts.get("expressive_mode") is False or not isinstance(model, str):
        return NO_CUES
    return ELEVENLABS_AGENT_TAGS if model.startswith(_TAG_ENGINES) else NO_CUES


def _stored_palette(agent: Mapping[str, Any]) -> list[dict[str, str]]:
    """The agent's suggested tags as ``{tag, description}`` pairs; [] when unreadable."""
    tts = _mapping(_mapping(agent.get("conversation_config")).get("tts"))
    stored = tts.get("suggested_audio_tags")
    if not isinstance(stored, list):
        return []
    return [
        {"tag": str(entry.get("tag")), "description": str(entry.get("description"))}
        for entry in stored
        if isinstance(entry, Mapping)
    ]


def palette_block(agent: Mapping[str, Any], tags: list[dict[str, str]]) -> dict[str, Any] | None:
    """The agent's ``tts`` block carrying ``tags``, sent back WHOLE; None when it holds them.

    The ONE comparison of what an agent holds with the palette LIA writes —
    by the live session's sync and by the phone's dial alike.

    Every other stored setting travels as stored: the vendor replaced the
    omitted booleans of a PATCHed block on the overrides (measured
    2026-09-16) and its merge of the ``tts`` block was never measured, so a
    partial block could reset the person's voice, engine or expressive
    switch. Read and returned whole, only the palette LIA owns changes,
    whatever the merge.

    Args:
        agent: The agent as ``GET /v1/convai/agents/{id}`` serves it.
        tags: The palette LIA writes (:func:`cue_prompt.palette`).

    Returns:
        The ``conversation_config.tts`` block to PATCH, or None.
    """
    if _stored_palette(agent) == tags:
        return None
    stored = _mapping(_mapping(agent.get("conversation_config")).get("tts"))
    return {**copy.deepcopy(dict(stored)), "suggested_audio_tags": tags}


def invented_cues(tags: Iterable[str], dialect: CueDialect) -> int:
    """How many ``tags`` a voice wrote outside the palette the person is offered.

    Case and blanks aside, as the vendor reads a tag. What it measures is whether
    the model keeps to LIA's palette; every tag is removed from what the chat
    shows either way.
    """
    offered = {
        _words(spelled[1:-1]) for cue, spelled in dialect.tags().items() if cue in PERSON_CUES
    }
    return sum(1 for tag in tags if _words(tag) not in offered)


def _words(tag: str) -> str:
    return " ".join(tag.casefold().split())


def expression_of(dialect: CueDialect) -> VoiceExpression:
    """``cues`` when the engine performs a tag a voice may write itself, else ``prose``."""
    return "cues" if dialect.tags() else "prose"


__all__ = [
    "PERSON_CUES",
    "STRANGER_CUES",
    "VoiceExpression",
    "agent_dialect",
    "expression_of",
    "invented_cues",
    "palette_block",
]
