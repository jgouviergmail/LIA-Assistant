"""One delivery shape, rendered for each engine — and what cannot be rendered is said."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core.prompt_store import read_prompt_file
from src.domains.radio import delivery as delivery_module
from src.domains.radio.delivery import (
    DELIVERY_LINES,
    REACTION_CUES,
    RenderedDelivery,
    StylePhrases,
    assert_reaction_cues_complete,
    delivery_kwargs,
    load_style_phrases,
    performed_reactions,
)
from src.domains.radio.formats import RadioRole
from src.domains.radio.script import Energy, Pace, RadioDelivery, Reaction, Tone
from src.domains.voice.expressive_cues import EVENT_CUES, Cue, cue_dialect
from src.domains.voice.families import TtsControl
from tests.support.voice_clock import retirement_day, speak_on

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


class TestOpeningCue:
    """An engine that performs cues in the text is handed one opening the line (ADR-345)."""

    def test_a_cue_engine_hears_the_tone_and_still_reports_what_it_could_not_express(
        self,
    ) -> None:
        out = delivery_kwargs(
            "fishaudio", RadioRole.ANCHOR, LIVELY, model="s2.1-pro", phrases=PHRASES
        )

        assert out.cue == "[warm]"
        assert out.kwargs == {"speed": 1.1}
        # One cue opens a line: the tone took it, the energy is still unexpressed.
        assert out.unrendered == ("energy",)

    def test_a_fixed_set_without_the_tone_falls_back_to_the_energy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speak_on(monkeypatch, retirement_day("fishaudio", "s1"))

        out = delivery_kwargs("fishaudio", RadioRole.ANCHOR, LIVELY, model="s1", phrases=PHRASES)

        assert out.cue == "(excited)"
        assert out.unrendered == ("tone",)

    def test_a_cue_engine_with_settings_gets_both(self) -> None:
        out = delivery_kwargs(
            "elevenlabs", RadioRole.ANCHOR, LIVELY, model="eleven_v4", phrases=PHRASES
        )

        assert out.cue == "[warm]"
        assert "voice_settings" in out.kwargs

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("edge", "edge-tts"),
            ("openai", "tts-1"),
            # Gemini performs sounds only; its delivery is the style direction.
            ("gemini", "gemini-3.8-flash-tts"),
            ("elevenlabs", "eleven_multilingual_v2"),
        ],
    )
    def test_an_engine_without_delivery_cues_never_gets_one(
        self, provider: str, model: str
    ) -> None:
        out = delivery_kwargs(provider, RadioRole.ANCHOR, LIVELY, model=model, phrases=PHRASES)

        assert out.cue == ""

    def test_a_neutral_delivery_opens_with_nothing(self) -> None:
        out = delivery_kwargs(
            "fishaudio", RadioRole.ANCHOR, NEUTRAL, model="s2.1-pro", phrases=PHRASES
        )

        assert (out.cue, out.unrendered) == ("", ())


class TestConcernedTone:
    """A concerned line is played as concern, the engine's own word for it (ADR-345)."""

    @pytest.mark.parametrize(
        ("provider", "model", "cue"),
        [
            ("fishaudio", "s2.1-pro", "[worried]"),
            ("elevenlabs", "eleven_v4", "[concerned]"),
            ("fishaudio", "drama-3", "[concerned]"),
        ],
    )
    def test_a_concerned_tone_opens_with_concern(self, provider: str, model: str, cue: str) -> None:
        delivery = RadioDelivery(tone=Tone.CONCERNED)

        out = delivery_kwargs(provider, RadioRole.ANCHOR, delivery, model=model, phrases=PHRASES)

        assert out.cue == cue
        assert "tone" not in out.unrendered


class TestReactions:
    """A vocal reaction the writer asked for opens its line, in the engine's own words."""

    def test_a_reaction_follows_the_delivery_cue(self) -> None:
        delivery = RadioDelivery(tone=Tone.WARM, reaction=Reaction.CHUCKLES)

        out = delivery_kwargs(
            "fishaudio", RadioRole.SPEAKER_A, delivery, model="s2.1-pro", phrases=PHRASES
        )

        assert out.cue == "[warm] [chuckling]"
        assert out.unrendered == ()

    def test_a_reaction_alone_opens_the_line(self) -> None:
        delivery = RadioDelivery(reaction=Reaction.SIGHS)

        out = delivery_kwargs(
            "elevenlabs", RadioRole.SPEAKER_B, delivery, model="eleven_v4", phrases=PHRASES
        )

        assert out.cue == "[sighs]"

    def test_gemini_hears_the_reaction_inline_beside_its_direction(self) -> None:
        delivery = RadioDelivery(tone=Tone.WARM, reaction=Reaction.LAUGHS)

        out = delivery_kwargs(
            "gemini",
            RadioRole.SPEAKER_A,
            delivery,
            model="gemini-3.8-flash-tts",
            phrases=PHRASES,
        )

        assert out.cue == "<laugh>"
        assert "style" in out.kwargs
        assert out.unrendered == ()

    @pytest.mark.parametrize(
        ("provider", "model"),
        [("edge", "edge-tts"), ("openai", "tts-1"), ("elevenlabs", "eleven_multilingual_v2")],
    )
    def test_an_engine_without_sounds_reports_the_reaction(self, provider: str, model: str) -> None:
        delivery = RadioDelivery(reaction=Reaction.CHUCKLES)

        out = delivery_kwargs(provider, RadioRole.SPEAKER_A, delivery, model=model, phrases=PHRASES)

        assert out.cue == ""
        assert out.unrendered == ("reaction",)

    def test_no_reaction_asks_nothing(self) -> None:
        out = delivery_kwargs(
            "fishaudio", RadioRole.SPEAKER_A, NEUTRAL, model="s2.1-pro", phrases=PHRASES
        )

        assert (out.cue, out.unrendered) == ("", ())

    @pytest.mark.parametrize(
        ("provider", "model", "performed"),
        [
            ("fishaudio", "s2.1-pro", (Reaction.LAUGHS, Reaction.CHUCKLES, Reaction.SIGHS)),
            ("elevenlabs", "eleven_v4", (Reaction.LAUGHS, Reaction.CHUCKLES, Reaction.SIGHS)),
            (
                "gemini",
                "gemini-3.8-flash-tts",
                (Reaction.LAUGHS, Reaction.CHUCKLES, Reaction.SIGHS),
            ),
            ("elevenlabs", "eleven_flash_v2_5", ()),
            ("gemini", "gemini-3.1-flash-tts-preview", ()),
            ("edge", "edge-tts", ()),
        ],
    )
    def test_the_reactions_an_engine_performs(
        self, provider: str, model: str, performed: tuple[Reaction, ...]
    ) -> None:
        assert performed_reactions(cue_dialect(provider, model)) == performed

    def test_every_reaction_but_none_is_a_sound_of_the_cue_vocabulary(self) -> None:
        assert {reaction for reaction in Reaction if reaction is not Reaction.NONE} == set(
            REACTION_CUES
        )
        assert set(REACTION_CUES.values()) <= EVENT_CUES

    def test_a_reaction_word_off_the_vocabulary_is_none_never_a_lost_script(self) -> None:
        repaired = RadioDelivery.model_validate({"reaction": "applause"})
        assert repaired.reaction is Reaction.NONE


def test_a_style_direction_never_claims_the_reaction_it_does_not_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The direction words energy, pace and tone; a reaction is a sound — an engine
    directed in words that performs no cue reports the reaction unrendered."""
    monkeypatch.setattr(
        delivery_module,
        "controls_for",
        lambda provider, model: frozenset({TtsControl.STYLE_PROMPT}),
    )
    delivery = RadioDelivery(tone=Tone.WARM, reaction=Reaction.LAUGHS)

    out = delivery_kwargs(
        "worded-engine", RadioRole.SPEAKER_A, delivery, model="any", phrases=PHRASES
    )

    assert "style" in out.kwargs
    assert out.cue == ""
    assert out.unrendered == ("reaction",)


class TestReactionCuesCompleteness:
    """ADR-085: ``REACTION_CUES`` is read with ``.get``, so a new reaction without a
    cue would be offered to no writer and voiced by no engine, in silence — the
    module refuses to import instead, as the radio's other registries do."""

    def test_the_shipped_table_is_complete(self) -> None:
        assert_reaction_cues_complete()

    def test_a_reaction_without_a_cue_refuses_the_boot(self) -> None:
        table = dict(REACTION_CUES)
        del table[Reaction.CHUCKLES]
        with pytest.raises(RuntimeError, match=r"without a cue=\['chuckles'\]"):
            assert_reaction_cues_complete(table)

    def test_none_is_no_reaction_to_voice(self) -> None:
        table = {**REACTION_CUES, Reaction.NONE: Cue.SIGHS}
        with pytest.raises(RuntimeError, match=r"no reaction to voice=\['none'\]"):
            assert_reaction_cues_complete(table)

    def test_a_reaction_voiced_by_a_delivery_cue_refuses_the_boot(self) -> None:
        table = {**REACTION_CUES, Reaction.SIGHS: Cue.WARM}
        with pytest.raises(RuntimeError, match=r"no sound=\['warm'\]"):
            assert_reaction_cues_complete(table)

    def test_the_import_carries_the_check(self) -> None:
        """Called at module level, like every radio registry check: the boot runs it."""
        source = Path(delivery_module.__file__).read_text(encoding="utf-8")
        calls = [
            node.value.func.id
            for node in ast.parse(source).body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ]
        assert "assert_reaction_cues_complete" in calls
