"""One delivery shape, rendered for each engine — and what cannot be rendered is said."""

from __future__ import annotations

import pytest

from src.core.prompt_store import read_prompt_file
from src.domains.radio.delivery import (
    DELIVERY_LINES,
    RenderedDelivery,
    StylePhrases,
    delivery_kwargs,
    load_style_phrases,
)
from src.domains.radio.formats import RadioRole
from src.domains.radio.script import Energy, Pace, RadioDelivery, Tone

pytestmark = pytest.mark.unit

PHRASES = StylePhrases(
    roles={RadioRole.HOST: "the station host", RadioRole.ANCHOR: "a news anchor"},
    qualities={
        "energy.lively": "energetic",
        "energy.calm": "calm",
        "pace.brisk": "brisk",
        "pace.slow": "unhurried",
        "tone.warm": "warm",
        "tone.serious": "serious",
    },
    template="Speak as {role}: {qualities}.",
    template_plain="Speak as {role}.",
)
#: A model of each family that takes every control its family declares.
MODELS = {
    "gemini": "gemini-3.8-flash-tts",
    "edge": "edge-tts",
    "openai": "tts-1",
    "elevenlabs": "eleven_v3_conversational",
}
NEUTRAL = RadioDelivery()
LIVELY = RadioDelivery(energy=Energy.LIVELY, pace=Pace.BRISK, tone=Tone.WARM)


def render(
    provider: str, delivery: RadioDelivery = LIVELY, role: RadioRole = RadioRole.ANCHOR
) -> RenderedDelivery:
    model = MODELS.get(provider, "unknown")
    return delivery_kwargs(provider, role, delivery, model=model, phrases=PHRASES)


def test_gemini_is_directed_in_words_and_renders_everything() -> None:
    out = render("gemini")
    assert out.kwargs == {"style": "Speak as a news anchor: energetic, brisk, warm."}
    assert out.unrendered == ()


def test_a_gemini_model_that_takes_no_direction_is_sent_none_and_says_so() -> None:
    """Measured 2026-09-26: the 2.5 and 3.1 previews answer 400 to ANY speech
    annotation, so a direction sent to one of them silenced every line."""
    out = delivery_kwargs(
        "gemini",
        RadioRole.ANCHOR,
        LIVELY,
        model="gemini-2.5-flash-preview-tts",
        phrases=PHRASES,
    )
    assert out.kwargs == {}
    assert out.unrendered == ("energy", "pace", "tone")


def test_a_neutral_delivery_leaves_no_dangling_separator() -> None:
    assert render("gemini", NEUTRAL).kwargs == {"style": "Speak as a news anchor."}


def test_a_lines_file_without_a_role_is_refused() -> None:
    with pytest.raises(ValueError, match="role.expert"):
        load_style_phrases(
            "\n".join(
                (
                    "template|As {role}, {qualities}.",
                    "template.plain|As {role}.",
                    "role.host|h",
                    "role.anchor|a",
                    "role.columnist|c",
                )
            )
        )


def test_an_unknown_role_is_spoken_as_the_host() -> None:
    out = render("gemini", role=RadioRole.EXPERT)
    assert out.kwargs["style"].startswith("Speak as the station host")


def test_edge_renders_pace_and_energy_but_not_tone() -> None:
    out = render("edge")
    assert out.kwargs == {"rate": "+10%", "pitch": "+3Hz", "volume": "+5%"}
    assert out.unrendered == ("tone",)


def test_openai_renders_pace_alone() -> None:
    out = render("openai")
    assert out.kwargs == {"speed": 1.1}
    assert out.unrendered == ("energy", "tone")


def test_elevenlabs_bends_the_admin_settings_without_touching_them() -> None:
    base = {"stability": 0.5, "style": 0.1, "similarity_boost": 0.75}
    out = delivery_kwargs(
        "elevenlabs",
        RadioRole.ANCHOR,
        LIVELY,
        model=MODELS["elevenlabs"],
        phrases=PHRASES,
        base_voice_settings=base,
    )
    settings = out.kwargs["voice_settings"]
    assert settings["similarity_boost"] == 0.75
    assert settings["stability"] == pytest.approx(0.35)
    assert settings["style"] == pytest.approx(0.4)
    assert base == {"stability": 0.5, "style": 0.1, "similarity_boost": 0.75}
    assert out.unrendered == ("pace",)


def test_elevenlabs_dials_stay_inside_their_bounds() -> None:
    base = {"stability": 0.05, "style": 0.95}
    out = delivery_kwargs(
        "elevenlabs",
        RadioRole.ANCHOR,
        RadioDelivery(energy=Energy.LIVELY, tone=Tone.UPBEAT),
        model=MODELS["elevenlabs"],
        phrases=PHRASES,
        base_voice_settings=base,
    )
    assert out.kwargs["voice_settings"]["stability"] == 0.0
    assert out.kwargs["voice_settings"]["style"] == 1.0


def test_a_neutral_delivery_asks_nothing_and_reports_nothing() -> None:
    for provider in ("gemini", "edge", "openai", "elevenlabs"):
        assert render(provider, NEUTRAL).unrendered == ()
    assert render("edge", NEUTRAL).kwargs == {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"}


def test_an_unknown_engine_renders_nothing_and_reports_everything() -> None:
    out = render("azure")
    assert out.kwargs == {}
    assert out.unrendered == ("energy", "pace", "tone")


def test_a_delivery_word_off_the_vocabulary_is_the_default_never_a_lost_script() -> None:
    # Measured 2026-09-26: a whole script was refused for ``delivery.energy`` alone.
    repaired = RadioDelivery.model_validate({"energy": "high", "pace": ["fast"], "tone": "warm"})
    assert (repaired.energy, repaired.pace, repaired.tone) == (
        Energy.NEUTRAL,
        Pace.NORMAL,
        Tone.WARM,
    )


def test_the_versioned_phrases_direct_every_role_and_every_marked_delivery() -> None:
    """The file the engine is directed from names every role, and every energy,
    pace and tone a script may mark — the neutral ones are the absence of a mark."""
    phrases = load_style_phrases(read_prompt_file(DELIVERY_LINES))
    assert set(phrases.roles) == set(RadioRole)
    marked = {
        *(f"energy.{value.value}" for value in Energy if value is not Energy.NEUTRAL),
        *(f"pace.{value.value}" for value in Pace if value is not Pace.NORMAL),
        *(f"tone.{value.value}" for value in Tone if value is not Tone.NEUTRAL),
    }
    assert marked <= set(phrases.qualities), sorted(marked - set(phrases.qualities))
