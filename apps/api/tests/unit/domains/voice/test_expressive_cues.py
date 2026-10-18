"""Expressive cues: one vocabulary LIA writes in, one dictionary per engine that performs it.

Read from each vendor's documentation (2026-10-13/14, re-read 2026-10-17):
ElevenLabs v3 and v4 perform ``[…]`` audio tags and refuse SSML, while every
earlier ElevenLabs model reads the SSML ``<break>`` alone; Fish Audio's S2
models perform ``[…]`` cues in natural language, ``s1`` a fixed set in
``(…)``, ``drama-3`` directions in ``[…]``; Gemini 3.8 performs point-in-time
``<…>`` vocal tags inline and a sustained delivery as the request's ``style``;
every other engine reads a bracket aloud. A cue an engine cannot perform never
reaches it, and a bracket in text that was not written for speech (an answer's
markdown link) is never performed.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from src.domains.voice import expressive_cues
from src.domains.voice.expressive_cues import (
    DELIVERY_CUES,
    ELEVENLABS_SSML_BREAK,
    EVENT_CUES,
    FISH_S1_CUES,
    FISH_S2_CUES,
    GEMINI_VOCAL_TAGS,
    AuthoredCues,
    AuthoredSentence,
    Cue,
    CueDialect,
    cue_dialect,
    neutralize_literal,
)
from src.domains.voice.families import TtsControl, controls_for
from tests.support.voice_clock import retirement_day, speak_on

pytestmark = pytest.mark.unit

#: The ElevenLabs models before v3: no audio tag, the SSML pause alone.
_ELEVEN_V2_GENERATION = ("eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5")


class TestTheDialects:
    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("edge", "edge-tts"),
            ("openai", "tts-1"),
            ("openai", "tts-1-hd"),
            # Google's previews retire on 2026-11-17 and read some bracketed
            # words aloud (its Gemini-TTS markup guide): deliberately none.
            ("gemini", "gemini-2.5-flash-preview-tts"),
            ("gemini", "gemini-2.5-pro-preview-tts"),
            ("gemini", "gemini-3.1-flash-tts-preview"),
            ("elevenlabs", "eleven_v5_unknown"),
            ("azure", "anything"),
        ],
    )
    def test_an_engine_that_reads_brackets_aloud_performs_no_cue(
        self, provider: str, model: str
    ) -> None:
        assert cue_dialect(provider, model).performs() == frozenset()

    @pytest.mark.parametrize("model", _ELEVEN_V2_GENERATION)
    def test_an_eleven_v2_generation_model_performs_the_ssml_pause_alone(self, model: str) -> None:
        dialect = cue_dialect("elevenlabs", model)

        assert dialect is ELEVENLABS_SSML_BREAK
        assert dialect.performs() == frozenset({Cue.SHORT_PAUSE})
        assert dialect.render(Cue.SHORT_PAUSE) == '<break time="0.5s" />'

    @pytest.mark.parametrize("model", ["eleven_v3_conversational", "eleven_v4", "eleven_v4_turbo"])
    def test_eleven_v3_and_v4_never_get_an_ssml_break(self, model: str) -> None:
        """The vendor: v3 and v4 do not support SSML break tags — punctuation pauses."""
        assert cue_dialect("elevenlabs", model).render(Cue.SHORT_PAUSE) == "…"

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("elevenlabs", "eleven_v3_conversational"),
            ("elevenlabs", "eleven_v4"),
            ("elevenlabs", "eleven_v4_turbo"),
            ("fishaudio", "s2.1-pro"),
            ("fishaudio", "s2.1-pro-free"),
            ("fishaudio", "s2-pro"),
            ("fishaudio", "drama-3"),
        ],
    )
    def test_a_bracket_engine_performs_every_cue(self, provider: str, model: str) -> None:
        assert cue_dialect(provider, model).performs() == DELIVERY_CUES | EVENT_CUES

    @pytest.mark.parametrize("model", ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
    def test_gemini_3_8_performs_events_inline_and_a_delivery_as_its_style(
        self, model: str
    ) -> None:
        """Google: inline ``<…>`` tags for point-in-time vocal events only; a
        sustained delivery belongs to the turn's ``speech_metadata.style``."""
        dialect = cue_dialect("gemini", model)

        assert dialect.performs() == DELIVERY_CUES | EVENT_CUES
        assert dialect.render(Cue.LAUGHS) == "<laugh>"
        assert dialect.render(Cue.WARM) is None
        assert dialect.style(Cue.WARM) == "warm"
        assert dialect.style(Cue.LAUGHS) is None

    def test_fish_s1_speaks_its_own_closed_set_in_parentheses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        speak_on(monkeypatch, retirement_day("fishaudio", "s1"))
        dialect = cue_dialect("fishaudio", "s1")
        assert dialect.render(Cue.CHEERFUL) == "(happy)"
        assert dialect.render(Cue.SIGHS) == "(sighing)"
        assert dialect.render(Cue.CONCERNED) == "(worried)"
        assert dialect.render(Cue.WARM) is None  # no equivalent in its fixed set

    def test_s1_served_as_its_successor_is_spelled_for_the_engine_that_speaks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The vendor: past its retirement, s1 is served by s2.1-pro, which reads
        ``(happy)`` as words — sent the old set, it would speak its directions."""
        speak_on(monkeypatch, retirement_day("fishaudio", "s1") + timedelta(days=1))

        assert cue_dialect("fishaudio", "s1") == cue_dialect("fishaudio", "s2.1-pro")
        assert cue_dialect("fishaudio", "s1").render(Cue.CHEERFUL) == "[happy]"

    @pytest.mark.parametrize(
        ("provider", "model", "cue", "spelled"),
        [
            ("fishaudio", "s2.1-pro", Cue.LAUGHS, "[laughing]"),
            ("fishaudio", "s2.1-pro", Cue.SHORT_PAUSE, "[break]"),
            # Fish's own word for it: « Worried — concerned, troubled ».
            ("fishaudio", "s2.1-pro", Cue.CONCERNED, "[worried]"),
            ("elevenlabs", "eleven_v4", Cue.WHISPERING, "[whispers]"),
            ("elevenlabs", "eleven_v4", Cue.SHORT_PAUSE, "…"),
            ("elevenlabs", "eleven_v4", Cue.CONCERNED, "[concerned]"),
            ("fishaudio", "drama-3", Cue.CHUCKLES, "[small laugh]"),
            ("fishaudio", "drama-3", Cue.CONCERNED, "[concerned]"),
        ],
    )
    def test_each_engine_has_its_own_dictionary(
        self, provider: str, model: str, cue: Cue, spelled: str
    ) -> None:
        assert cue_dialect(provider, model).render(cue) == spelled


class TestTheTableHoldsTogether:
    """What keeps a spelling meant for one engine from reaching another."""

    _DIALECTS = sorted(
        {dialect.name: dialect for *_, dialect in expressive_cues._RULES}.values(),
        key=lambda dialect: dialect.name,
    )

    @pytest.mark.parametrize("dialect", _DIALECTS, ids=lambda dialect: dialect.name)
    def test_a_style_is_a_delivery_and_never_also_spelled_inline(self, dialect: CueDialect) -> None:
        assert set(dialect.styles) <= DELIVERY_CUES
        assert set(dialect.styles).isdisjoint(dialect.spellings)

    def test_a_style_only_reaches_a_model_that_takes_one(self) -> None:
        """The 2.5 and 3.1 previews answer 400 to ANY speech annotation
        (measured 2026-09-26): a style sent to one would silence the voice."""
        styled = [
            (provider, prefix)
            for provider, prefix, dialect in expressive_cues._RULES
            if dialect.styles
        ]
        assert styled
        for provider, prefix in styled:
            assert TtsControl.STYLE_PROMPT in controls_for(provider, prefix), prefix

    def test_every_canonical_cue_has_a_dialect_that_performs_it(self) -> None:
        performed = frozenset().union(*(dialect.performs() for dialect in self._DIALECTS))
        assert performed == frozenset(Cue)


class TestAuthoredText:
    def test_a_canonical_cue_is_spelled_the_engines_way(self) -> None:
        cues = AuthoredCues(cue_dialect("fishaudio", "s2.1-pro"), budget=2)
        assert cues.render("[warm] C'est noté pour demain. [laughs]") == AuthoredSentence(
            "[warm] C'est noté pour demain. [laughing]"
        )

    def test_a_cue_the_engine_cannot_perform_is_dropped_never_read(self) -> None:
        cues = AuthoredCues(cue_dialect("openai", "tts-1"), budget=2)
        assert cues.render("[warm] C'est noté pour demain.").text == "C'est noté pour demain."

    def test_an_invented_cue_is_dropped(self) -> None:
        cues = AuthoredCues(cue_dialect("elevenlabs", "eleven_v4"), budget=2)
        assert cues.render("[mysteriously] Voilà [banana] le résultat.").text == (
            "Voilà le résultat."
        )

    def test_the_budget_holds_across_the_sentences_of_one_comment(self) -> None:
        cues = AuthoredCues(cue_dialect("fishaudio", "s2.1-pro"), budget=2)
        assert cues.render("[warm] Un.").text == "[warm] Un."
        assert cues.render("[laughs] Deux. [sighs]").text == "[laughing] Deux."
        assert cues.render("[excited] Trois.").text == "Trois."

    def test_a_zero_budget_performs_nothing(self) -> None:
        cues = AuthoredCues(cue_dialect("fishaudio", "s2.1-pro"), budget=0)
        assert cues.render("[warm] Un.").text == "Un."

    def test_cue_words_are_matched_whatever_their_case_and_spacing(self) -> None:
        cues = AuthoredCues(cue_dialect("fishaudio", "s2.1-pro"), budget=2)
        assert cues.render("[ Short Pause ] Bon.").text == "[break] Bon."

    def test_angle_bracket_tags_are_never_left_to_an_engine(self) -> None:
        cues = AuthoredCues(cue_dialect("gemini", "gemini-3.8-flash-tts"), budget=3)
        assert cues.render("<cough> [sighs] Bon.").text == "<sigh> Bon."

    def test_a_writers_parenthesis_never_acts_on_an_engine_that_reads_one(self) -> None:
        """Fish ``s1`` performs ``(sad)``: only a cue LIA spelled may reach it."""
        cues = AuthoredCues(FISH_S1_CUES, budget=2)
        assert cues.render("Bon (sad) [laughs] d'accord.").text == "Bon sad (laughing) d'accord."

    def test_an_eleven_v2_engine_hears_the_pause_as_ssml(self) -> None:
        cues = AuthoredCues(cue_dialect("elevenlabs", "eleven_flash_v2_5"), budget=2)
        assert cues.render("C'est réservé [short pause] pour dix heures. [laughs]").text == (
            'C\'est réservé <break time="0.5s" /> pour dix heures.'
        )

    def test_a_writers_own_ssml_never_reaches_an_engine_that_reads_it(self) -> None:
        cues = AuthoredCues(ELEVENLABS_SSML_BREAK, budget=2)
        assert cues.render('Attends <break time="3s" /> voilà.').text == "Attends voilà."


class TestAStyleEngine:
    """Gemini 3.8: a delivery is the request's direction, a sound stays in the text."""

    def test_the_delivery_becomes_the_sentences_style(self) -> None:
        cues = AuthoredCues(GEMINI_VOCAL_TAGS, budget=2)
        assert cues.render("[warm] C'est noté. [sighs]") == AuthoredSentence(
            "C'est noté. <sigh>", "warm"
        )

    def test_only_the_first_direction_of_a_sentence_is_its_style(self) -> None:
        cues = AuthoredCues(GEMINI_VOCAL_TAGS, budget=3)
        assert cues.render("[calm] Un [serious] deux.") == AuthoredSentence("Un deux.", "calm")
        # The dropped direction cost nothing: two cues are still left.
        assert cues.render("[warm] Trois. [laughs]") == AuthoredSentence("Trois. <laugh>", "warm")

    def test_a_style_spends_the_budget_like_any_cue(self) -> None:
        cues = AuthoredCues(GEMINI_VOCAL_TAGS, budget=1)
        assert cues.render("[warm] Un.").style == "warm"
        assert cues.render("[serious] Deux. [sighs]") == AuthoredSentence("Deux.")

    def test_no_cue_asks_for_no_style(self) -> None:
        sentence = AuthoredCues(GEMINI_VOCAL_TAGS, budget=2).render("Bon.")
        assert sentence == AuthoredSentence("Bon.")
        assert sentence.controls() == {}

    def test_the_style_travels_as_the_controls_of_the_call(self) -> None:
        sentence = AuthoredCues(GEMINI_VOCAL_TAGS, budget=2).render("[concerned] Attention.")
        assert sentence.controls() == {"style": "concerned"}

    def test_an_inline_engine_never_sends_a_style(self) -> None:
        sentence = AuthoredCues(FISH_S2_CUES, budget=2).render("[warm] Bon.")
        assert sentence == AuthoredSentence("[warm] Bon.")
        assert sentence.controls() == {}


class TestLiteralText:
    @pytest.mark.parametrize("provider,model", [("fishaudio", "s2.1-pro"), ("edge", "edge-tts")])
    def test_a_markdown_link_is_read_as_its_text(self, provider: str, model: str) -> None:
        dialect = cue_dialect(provider, model)
        assert neutralize_literal("Voir [le site](https://exemple.fr) ici.", dialect) == (
            "Voir le site ici."
        )

    def test_a_footnote_mark_is_not_read(self) -> None:
        dialect = cue_dialect("fishaudio", "s2.1-pro")
        assert (
            neutralize_literal("Le résultat [1] est bon [12].", dialect) == "Le résultat est bon."
        )

    def test_a_bracket_is_never_performed_as_a_cue(self) -> None:
        dialect = cue_dialect("elevenlabs", "eleven_v4")
        assert neutralize_literal("Statut [laughs] confirmé.", dialect) == "Statut laughs confirmé."

    def test_an_angle_tag_is_markup_to_an_angle_engine_and_a_comparison_stays(self) -> None:
        """Read as words, ``<div class="x">`` was spoken « div class x »."""
        dialect = cue_dialect("gemini", "gemini-3.8-flash-tts")
        assert neutralize_literal(
            'Voilà <laugh> la <b>suite</b>, <div class="x">3 < 5</div>.', dialect
        ) == ("Voilà la suite , 3 < 5 .")

    def test_only_an_angle_engine_loses_its_tags(self) -> None:
        dialect = cue_dialect("fishaudio", "s2.1-pro")
        assert neutralize_literal("Voilà <b>la</b> suite.", dialect) == "Voilà <b>la</b> suite."

    @pytest.mark.parametrize("model", _ELEVEN_V2_GENERATION)
    def test_an_ssml_tag_in_a_read_text_is_markup_to_an_eleven_v2_engine(self, model: str) -> None:
        """Read literally, a third party's ``<break time="3s"/>`` would be performed."""
        dialect = cue_dialect("elevenlabs", model)
        assert neutralize_literal('Attends <break time="3s" /> encore.', dialect) == (
            "Attends encore."
        )

    @pytest.mark.parametrize(
        ("provider", "model"),
        [("fishaudio", "s2.1-pro"), ("fishaudio", "drama-3"), ("edge", "edge-tts")],
    )
    def test_a_vendor_control_marker_never_comes_from_a_text(
        self, provider: str, model: str
    ) -> None:
        """A headline holding « <|speaker:1|> » would hand the line to the other voice."""
        dialect = cue_dialect(provider, model)
        sent = neutralize_literal("Fin <|speaker:1|> du journal.", dialect)
        assert "<|" not in sent
        assert "<|" not in AuthoredCues(dialect, 2).render("Fin <|speaker:1|> du journal.").text

    def test_drama_reads_its_paired_tags_so_a_literal_one_is_markup(self) -> None:
        dialect = cue_dialect("fishaudio", "drama-3")
        assert neutralize_literal("Il dit <whisper>non</whisper>.", dialect) == "Il dit non ."

    def test_a_parenthesis_is_read_as_words_by_an_engine_that_performs_one(self) -> None:
        """s1's fixed set holds plain words: « (moved) » in a headline would act."""
        text = "Le rendez-vous (moved) est confirmé (enfin)."
        assert neutralize_literal(text, FISH_S1_CUES) == "Le rendez-vous moved est confirmé enfin."
        assert neutralize_literal(text, FISH_S2_CUES) == text

    @pytest.mark.parametrize(
        ("text", "read"),
        [
            ("- [x] Payer le loyer.", "- Payer le loyer."),
            ("- [ ] Appeler Paul.", "- Appeler Paul."),
            ("[x] Fait.", "Fait."),
            # Anywhere else a box is a word.
            ("Appuie sur [X] pour fermer.", "Appuie sur X pour fermer."),
            (
                "Voici ![le graphique](https://exemple.fr/g.png) du mois.",
                "Voici le graphique du mois.",
            ),
        ],
    )
    def test_a_task_box_is_not_read_and_an_image_is_read_as_its_label(
        self, text: str, read: str
    ) -> None:
        assert neutralize_literal(text, cue_dialect("elevenlabs", "eleven_v4")) == read
