"""The one seam from a line's delivery to a voice engine's per-call controls.

The writer asks for a delivery in ONE provider-independent shape
(:class:`~src.domains.radio.script.RadioDelivery`: energy, pace, tone) and the
role that speaks. Each engine expresses a different subset: Edge takes SSML
prosody offsets, OpenAI a speed, ElevenLabs a stability/style block, Gemini a
natural-language direction — on the models measured to take one. :func:`delivery_kwargs`
renders what the family declares the engine's MODEL accepts
(:func:`src.domains.voice.families.controls_for`) and REPORTS what it could not
render, so the pipeline counts it rather than pretending — the
``kwargs_for`` shape of ADR-245 applied to speech.

It never raises: an unknown provider renders nothing and reports everything.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from src.core.prompt_store import parse_prompt_sections
from src.domains.radio.formats import RadioRole
from src.domains.radio.script import Energy, Pace, RadioDelivery, Tone
from src.domains.voice.families import TtsControl, controls_for

#: The versioned lines file an engine directed in words is read from.
DELIVERY_LINES: Final[str] = "radio_delivery_lines"

# Edge SSML offsets — modest on purpose: a newsreader sped up by a third sounds
# like a fault, not like energy.
_EDGE_RATE: Final[dict[Pace, str]] = {Pace.SLOW: "-8%", Pace.NORMAL: "+0%", Pace.BRISK: "+10%"}
_EDGE_PITCH: Final[dict[Energy, str]] = {
    Energy.CALM: "-2Hz",
    Energy.NEUTRAL: "+0Hz",
    Energy.LIVELY: "+3Hz",
}
_EDGE_VOLUME: Final[dict[Energy, str]] = {
    Energy.CALM: "-5%",
    Energy.NEUTRAL: "+0%",
    Energy.LIVELY: "+5%",
}

#: OpenAI's speed multiplier (the API accepts 0.25 to 4.0).
_OPENAI_SPEED: Final[dict[Pace, float]] = {Pace.SLOW: 0.92, Pace.NORMAL: 1.0, Pace.BRISK: 1.1}

# ElevenLabs: expressiveness rises as stability falls and style rises, inside
# [0, 1]; the tone nudges the same two dials. Applied ON TOP of the admin's
# configured settings, which stay the base (the ADR-237 prosody doctrine).
_ELEVEN_ENERGY: Final[dict[Energy, tuple[float, float]]] = {
    Energy.CALM: (0.15, -0.10),
    Energy.NEUTRAL: (0.0, 0.0),
    Energy.LIVELY: (-0.15, 0.20),
}
_ELEVEN_TONE: Final[dict[Tone, tuple[float, float]]] = {
    Tone.NEUTRAL: (0.0, 0.0),
    Tone.WARM: (0.0, 0.10),
    Tone.SERIOUS: (0.10, -0.05),
    Tone.UPBEAT: (-0.05, 0.15),
    Tone.CONCERNED: (0.05, 0.05),
}
_ELEVEN_DEFAULT_STABILITY: Final[float] = 0.5
_ELEVEN_DEFAULT_STYLE: Final[float] = 0.0


@dataclass(frozen=True, slots=True)
class StylePhrases:
    """The words a natural-language engine is directed with (a prompt file's rows).

    Attributes:
        roles: One phrase per role (« a clear, credible news anchor »).
        qualities: One word per non-neutral energy, pace and tone value.
        template: The sentence, with ``{role}`` and ``{qualities}``.
        template_plain: The sentence when nothing but the role is asked, with
            ``{role}`` alone — a template with an empty ``{qualities}`` leaves
            a dangling separator in the direction.
    """

    roles: Mapping[RadioRole, str]
    qualities: Mapping[str, str]
    template: str
    template_plain: str


@dataclass(frozen=True, slots=True)
class RenderedDelivery:
    """What an engine receives, and which requested dimensions it could not express."""

    kwargs: dict[str, Any]
    unrendered: tuple[str, ...]


def _requested(delivery: RadioDelivery) -> tuple[str, ...]:
    """The dimensions of ``delivery`` that ask for something (non-neutral)."""
    asked = []
    if delivery.energy is not Energy.NEUTRAL:
        asked.append("energy")
    if delivery.pace is not Pace.NORMAL:
        asked.append("pace")
    if delivery.tone is not Tone.NEUTRAL:
        asked.append("tone")
    return tuple(asked)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _eleven_settings(delivery: RadioDelivery, base: Mapping[str, Any] | None) -> dict[str, Any]:
    settings = dict(base or {})
    stability = float(settings.get("stability", _ELEVEN_DEFAULT_STABILITY))
    style = float(settings.get("style", _ELEVEN_DEFAULT_STYLE))
    for d_stability, d_style in (_ELEVEN_ENERGY[delivery.energy], _ELEVEN_TONE[delivery.tone]):
        stability += d_stability
        style += d_style
    return {**settings, "stability": _clamp01(stability), "style": _clamp01(style)}


def _style_prompt(role: RadioRole, delivery: RadioDelivery, phrases: StylePhrases) -> str:
    qualities = [
        phrases.qualities[key]
        for key in (
            f"energy.{delivery.energy.value}",
            f"pace.{delivery.pace.value}",
            f"tone.{delivery.tone.value}",
        )
        if key in phrases.qualities
    ]
    spoken_as = phrases.roles.get(role, phrases.roles[RadioRole.HOST])
    if not qualities:
        return phrases.template_plain.format(role=spoken_as).strip()
    return phrases.template.format(role=spoken_as, qualities=", ".join(qualities)).strip()


def load_style_phrases(text: str) -> StylePhrases:
    """The direction phrases from the ``radio_delivery_lines`` prompt file.

    Args:
        text: The file's content (``key|text`` rows).

    Returns:
        The phrases.

    Raises:
        ValueError: When a role or a template is missing — an engine directed
            with half a vocabulary would read some lines with no direction.
    """
    rows = dict(parse_prompt_sections(text, 2))
    missing = [
        key
        for key in ("template", "template.plain", *(f"role.{r.value}" for r in RadioRole))
        if not rows.get(key)
    ]
    if missing:
        raise ValueError(f"{DELIVERY_LINES} lacks {missing}")
    return StylePhrases(
        roles={role: rows[f"role.{role.value}"] for role in RadioRole},
        qualities={
            key: value
            for key, value in rows.items()
            if key.split(".", 1)[0] in ("energy", "pace", "tone")
        },
        template=rows["template"],
        template_plain=rows["template.plain"],
    )


def delivery_kwargs(
    provider: str,
    role: RadioRole,
    delivery: RadioDelivery,
    *,
    model: str,
    phrases: StylePhrases,
    base_voice_settings: Mapping[str, Any] | None = None,
) -> RenderedDelivery:
    """Render a line's delivery for one engine.

    Args:
        provider: The TTS provider id.
        role: Who speaks the line (a natural-language engine is told).
        delivery: What the writer asked for.
        model: The engine's model — some controls are only accepted by some
            models of a provider (:func:`controls_for`).
        phrases: The direction phrases (from the radio delivery prompt file).
        base_voice_settings: The admin's ElevenLabs settings, the base the
            delivery bends (never replaced, never mutated).

    Returns:
        The per-call kwargs, and the requested dimensions the engine cannot express.
    """
    asked = _requested(delivery)
    controls = controls_for(provider, model)
    kwargs: dict[str, Any] = {}
    rendered: set[str] = set()
    if TtsControl.STYLE_PROMPT in controls:
        kwargs["style"] = _style_prompt(role, delivery, phrases)
        rendered.update(asked)
    if TtsControl.RATE in controls:
        kwargs["rate"] = _EDGE_RATE[delivery.pace]
        rendered.add("pace")
    if TtsControl.PITCH in controls and TtsControl.VOLUME in controls:
        kwargs["pitch"] = _EDGE_PITCH[delivery.energy]
        kwargs["volume"] = _EDGE_VOLUME[delivery.energy]
        rendered.add("energy")
    if TtsControl.SPEED in controls:
        kwargs["speed"] = _OPENAI_SPEED[delivery.pace]
        rendered.add("pace")
    if TtsControl.VOICE_SETTINGS in controls:
        kwargs["voice_settings"] = _eleven_settings(delivery, base_voice_settings)
        rendered.update({"energy", "tone"})
    return RenderedDelivery(
        kwargs=kwargs, unrendered=tuple(dim for dim in asked if dim not in rendered)
    )


__all__ = [
    "DELIVERY_LINES",
    "RenderedDelivery",
    "StylePhrases",
    "delivery_kwargs",
    "load_style_phrases",
]
