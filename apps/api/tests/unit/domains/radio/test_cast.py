"""A voice per role: chosen when the engine still has it, distinct and contrasted otherwise."""

from __future__ import annotations

import pytest

from src.domains.radio.cast import cast_voices
from src.domains.radio.formats import (
    CONFIGURABLE_ROLES,
    FORMAT_SPECS,
    SPEAKER_ROLES,
    RadioFormat,
    RadioRole,
)
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit

MULTI = [
    VoiceOption("aoede", "Aoede", "female"),
    VoiceOption("kore", "Kore", "female"),
    VoiceOption("puck", "Puck", "male"),
    VoiceOption("orus", "Orus", "male"),
]
EDGE = [
    VoiceOption("en-US-Ava", "Ava", "female", "en"),
    VoiceOption("fr-FR-Denise", "Denise", "female", "fr"),
    VoiceOption("fr-FR-Henri", "Henri", "male", "fr"),
    VoiceOption("zh-CN-Xiaoxiao", "Xiaoxiao", "female", "zh"),
]


def test_every_role_gets_its_own_voice_alternating_genders() -> None:
    cast = cast_voices(MULTI, {}, language="fr", multilingual=True)
    assert cast is not None
    assert {role: cast.voices[role] for role in CONFIGURABLE_ROLES} == {
        RadioRole.HOST: "aoede",
        RadioRole.ANCHOR: "puck",
        RadioRole.EXPERT: "kore",
        RadioRole.COLUMNIST: "orus",
    }
    assert cast.distinct_voices_of(CONFIGURABLE_ROLES) == 4


def test_a_choice_the_engine_still_has_is_kept() -> None:
    cast = cast_voices(MULTI, {RadioRole.HOST: "orus"}, language="fr", multilingual=True)
    assert cast is not None
    assert cast.voices[RadioRole.HOST] == "orus"
    assert cast.voices[RadioRole.ANCHOR] == "aoede"  # contrasts with the chosen host


def test_a_choice_from_a_previous_engine_falls_back_to_a_default() -> None:
    cast = cast_voices(MULTI, {RadioRole.HOST: "alloy"}, language="fr", multilingual=True)
    assert cast is not None and cast.voices[RadioRole.HOST] == "aoede"


def test_one_voice_per_language_engine_casts_in_the_listeners_language() -> None:
    cast = cast_voices(EDGE, {}, language="fr", multilingual=False)
    assert cast is not None
    assert set(cast.voices.values()) == {"fr-FR-Denise", "fr-FR-Henri"}
    assert cast.distinct_voices_of(CONFIGURABLE_ROLES) == 2
    chinese = cast_voices(EDGE, {}, language="zh-CN", multilingual=False)
    assert chinese is not None and chinese.distinct_voices_of(CONFIGURABLE_ROLES) == 1


def test_a_language_without_voices_still_gets_a_programme() -> None:
    cast = cast_voices(EDGE, {}, language="it", multilingual=False)
    assert cast is not None and cast.voices[RadioRole.HOST] == "en-US-Ava"


def test_the_same_voice_twice_is_the_persons_choice_and_counted_once() -> None:
    chosen = {RadioRole.ANCHOR: "kore", RadioRole.EXPERT: "kore"}
    cast = cast_voices(MULTI, chosen, language="en", multilingual=True)
    assert cast is not None
    assert cast.voices[RadioRole.ANCHOR] == cast.voices[RadioRole.EXPERT] == "kore"


def test_an_empty_catalogue_casts_nobody() -> None:
    assert cast_voices([], {}, language="en", multilingual=True) is None


MANY = [
    *MULTI,
    VoiceOption("charon", "Charon", "male"),
    VoiceOption("leda", "Leda", "female"),
    VoiceOption("fenrir", "Fenrir", "male"),
]


def roles_of(fmt: RadioFormat) -> tuple[RadioRole, ...]:
    return FORMAT_SPECS[fmt].roles


class TestTheCommentators:
    """ADR-324 decision 39: the station casts its commentators itself, with voices nobody
    else speaks with when the engine has enough — never LIA's voice for a view."""

    def test_they_take_voices_nobody_speaks_with_first(self) -> None:
        cast = cast_voices(MANY, {}, language="fr", multilingual=True)
        assert cast is not None
        mine = {cast.voices[role] for role in CONFIGURABLE_ROLES}
        theirs = [cast.voices[role] for role in SPEAKER_ROLES]
        assert len(set(theirs)) == 3 and not mine & set(theirs)
        assert cast.voiced_roles(roles_of(RadioFormat.DEBATE)) == roles_of(RadioFormat.DEBATE)
        assert cast.distinct_voices_of(roles_of(RadioFormat.DEBATE)) == 4

    def test_a_listener_never_chooses_one(self) -> None:
        chosen = {RadioRole.SPEAKER_A: "aoede"}
        cast = cast_voices(MANY, chosen, language="fr", multilingual=True)
        assert cast is not None and cast.voices[RadioRole.SPEAKER_A] != "aoede"

    def test_with_few_voices_they_borrow_the_expert_s_and_the_editorialist_s(self) -> None:
        cast = cast_voices(MULTI, {}, language="fr", multilingual=True)
        assert cast is not None
        assert {cast.voices[RadioRole.SPEAKER_A], cast.voices[RadioRole.SPEAKER_B]} == {
            cast.voices[RadioRole.EXPERT],
            cast.voices[RadioRole.COLUMNIST],
        }
        # The third one borrows the moderator's voice rather than LIA's, which never
        # speaks a view: silent in a debate, where the moderator speaks, heard in a
        # discussion, where nobody else has that voice.
        assert cast.voices[RadioRole.SPEAKER_C] == cast.voices[RadioRole.ANCHOR]
        debate = cast.voiced_roles(roles_of(RadioFormat.DEBATE))
        assert debate == (RadioRole.ANCHOR, RadioRole.SPEAKER_A, RadioRole.SPEAKER_B)
        assert cast.distinct_voices_of(roles_of(RadioFormat.DEBATE)) == 3
        assert cast.voiced_roles(roles_of(RadioFormat.DISCUSSION)) == SPEAKER_ROLES
        assert cast.distinct_voices_of(roles_of(RadioFormat.DISCUSSION)) == 3

    def test_one_speaking_with_lia_s_voice_is_left_out(self) -> None:
        cast = cast_voices(EDGE, {}, language="fr", multilingual=False)
        assert cast is not None
        assert cast.distinct_voices_of(roles_of(RadioFormat.DEBATE)) == 1
        assert cast.distinct_voices_of(roles_of(RadioFormat.DISCUSSION)) == 1

    def test_a_dialogue_of_the_listener_s_roles_keeps_its_voices(self) -> None:
        chosen = {RadioRole.ANCHOR: "kore", RadioRole.EXPERT: "kore"}
        cast = cast_voices(MULTI, chosen, language="en", multilingual=True)
        assert cast is not None
        assert cast.voiced_roles(roles_of(RadioFormat.ANALYSIS)) == roles_of(RadioFormat.ANALYSIS)
        assert cast.distinct_voices_of(roles_of(RadioFormat.ANALYSIS)) == 1

    def test_a_cast_stored_before_the_commentators_voices_none(self) -> None:
        cast = cast_voices(MULTI, {}, language="fr", multilingual=True)
        assert cast is not None
        older = type(cast)(voices={role: cast.voices[role] for role in CONFIGURABLE_ROLES})
        assert older.voiced_roles(roles_of(RadioFormat.DISCUSSION)) == ()
        assert older.distinct_voices_of(roles_of(RadioFormat.DEBATE)) == 1
