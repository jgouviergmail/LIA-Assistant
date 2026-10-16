"""A voice per role: chosen when the engine still has it, distinct and contrasted otherwise."""

from __future__ import annotations

from itertools import permutations

import pytest

from src.domains.radio.cast import VOICES_APART, Cast, cast_voices, shared_voice
from src.domains.radio.formats import (
    FORMAT_SPECS,
    SPEAKER_ROLES,
    STAFF_ROLES,
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
    assert {role: cast.voices[role] for role in STAFF_ROLES} == {
        RadioRole.HOST: "aoede",
        RadioRole.ANCHOR: "puck",
        RadioRole.EXPERT: "kore",
        RadioRole.COLUMNIST: "orus",
    }
    assert cast.distinct_voices_of(STAFF_ROLES) == 4


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
    assert cast.distinct_voices_of(STAFF_ROLES) == 2
    chinese = cast_voices(EDGE, {}, language="zh-CN", multilingual=False)
    assert chinese is not None and chinese.distinct_voices_of(STAFF_ROLES) == 1


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
    """ADR-324 decision 39: a commentator the listener left automatic is cast by the station,
    with a voice nobody else speaks with when the engine has enough — never LIA's for a
    view; one the listener chose speaks with that voice (2026-10-16)."""

    def test_they_take_voices_nobody_speaks_with_first(self) -> None:
        cast = cast_voices(MANY, {}, language="fr", multilingual=True)
        assert cast is not None
        mine = {cast.voices[role] for role in STAFF_ROLES}
        theirs = [cast.voices[role] for role in SPEAKER_ROLES]
        assert len(set(theirs)) == 3 and not mine & set(theirs)
        assert cast.voiced_roles(roles_of(RadioFormat.DEBATE)) == roles_of(RadioFormat.DEBATE)
        assert cast.distinct_voices_of(roles_of(RadioFormat.DEBATE)) == 4

    def test_a_listener_s_choice_is_kept_and_no_default_takes_it(self) -> None:
        # Before 2026-10-16 the station cast them all: a debate was heard in voices
        # nobody had chosen.
        chosen = {RadioRole.SPEAKER_A: "aoede", RadioRole.SPEAKER_C: "orus"}
        cast = cast_voices(MANY, chosen, language="fr", multilingual=True)
        assert cast is not None
        assert (cast.voices[RadioRole.SPEAKER_A], cast.voices[RadioRole.SPEAKER_C]) == (
            "aoede",
            "orus",
        )
        others = [voice for role, voice in cast.voices.items() if role not in chosen]
        assert not {"aoede", "orus"} & set(others)
        assert cast.distinct_voices_of(roles_of(RadioFormat.DEBATE)) == 4

    def test_a_voice_chosen_for_a_later_role_is_no_default_for_an_earlier_one(self) -> None:
        # The host is cast first: before, its default could take the anchor's chosen voice.
        cast = cast_voices(MULTI, {RadioRole.ANCHOR: "aoede"}, language="fr", multilingual=True)
        assert cast is not None
        assert cast.voices[RadioRole.ANCHOR] == "aoede"
        assert cast.voices[RadioRole.HOST] != "aoede"

    def test_a_chosen_commentator_with_lia_s_voice_is_still_silenced(self) -> None:
        # A write refuses it (``shared_voice``); a stored one is read forgivingly.
        chosen = {RadioRole.HOST: "puck", RadioRole.SPEAKER_B: "puck"}
        cast = cast_voices(MANY, chosen, language="fr", multilingual=True)
        assert cast is not None
        assert RadioRole.SPEAKER_B not in cast.voiced_roles(roles_of(RadioFormat.DISCUSSION))

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
        older = type(cast)(voices={role: cast.voices[role] for role in STAFF_ROLES})
        assert older.voiced_roles(roles_of(RadioFormat.DISCUSSION)) == ()
        assert older.distinct_voices_of(roles_of(RadioFormat.DEBATE)) == 1


class TestAMultilingualEngine:
    """Every voice speaks every language; one native to it speaks it without an accent."""

    FISH = [
        VoiceOption("e" * 32, "Emma", "female", "en"),
        VoiceOption("n" * 32, "Clone", "male", None),
        VoiceOption("f" * 32, "Emilie", "female", "fr"),
        VoiceOption("j" * 32, "Jun", "male", "ja"),
        VoiceOption("r" * 32, "Remy", "male", "fr"),
    ]

    def test_the_default_cast_speaks_the_listener_s_language(self) -> None:
        cast = cast_voices(self.FISH, {}, language="fr", multilingual=True)
        assert cast is not None
        assert cast.voices[RadioRole.HOST] in {"f" * 32, "r" * 32}


class TestTheVoicesApart:
    """What a write refuses is exactly what the cast would silence — derived, never listed."""

    @pytest.mark.parametrize(("first", "second"), list(permutations(RadioRole, 2)))
    def test_two_roles_may_not_share_a_voice_exactly_when_a_programme_would_silence_one(
        self, first: RadioRole, second: RadioRole
    ) -> None:
        voices = {role: role.value for role in RadioRole}
        voices[second] = voices[first]
        cast = Cast(voices=voices)
        silenced = any(
            set(spec.roles) - set(cast.voiced_roles(spec.roles)) for spec in FORMAT_SPECS.values()
        )
        assert (second in VOICES_APART[first]) is silenced
        assert shared_voice({first: "v", second: "v"}) is silenced

    def test_a_commentator_never_sounds_like_lia_the_moderator_or_another_one(self) -> None:
        assert VOICES_APART[RadioRole.SPEAKER_A] == frozenset(
            {RadioRole.HOST, RadioRole.ANCHOR, RadioRole.SPEAKER_B, RadioRole.SPEAKER_C}
        )
        assert VOICES_APART[RadioRole.HOST] == frozenset(SPEAKER_ROLES)
        assert VOICES_APART[RadioRole.EXPERT] == frozenset()

    def test_the_team_may_share_a_voice_it_is_the_listener_s_choice(self) -> None:
        assert not shared_voice({RadioRole.ANCHOR: "kore", RadioRole.EXPERT: "kore"})
        assert not shared_voice({RadioRole.EXPERT: "kore", RadioRole.SPEAKER_A: "kore"})
        assert not shared_voice({})
