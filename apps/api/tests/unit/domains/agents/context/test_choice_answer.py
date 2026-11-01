"""Which listed option an answer to « which one? » designates — read without a model (ADR-367).

The person was shown the items a description fits and asked which one. A
click carries its own index; a typed or spoken answer is read here: a number
or an ordinal of the person's language, a word that tells one option apart,
a refusal, « none of them ». Anything else is UNCLEAR — asked again, never
guessed.
"""

from __future__ import annotations

import pytest

from src.core.i18n_hitl import DISAMBIGUATION_ANSWER_WORDS
from src.domains.agents.context.choice_answer import (
    CHOICE_CANCEL,
    CHOICE_NONE,
    CHOICE_SELECT,
    CHOICE_UNCLEAR,
    FIELD_SELECTED_INDEX,
    ChoiceAnswer,
    read_choice_answer,
)

pytestmark = pytest.mark.unit

MAILS = (
    "Marc Dubois <marc@example.com> · Photos du week-end · mardi 15 septembre 2026 à 17:24",
    "Marc Dubois <marc@example.com> · Facture du garage · lundi 14 septembre 2026 à 09:12",
    "Marc Dubois <marc@example.com> · Dîner samedi · dimanche 13 septembre 2026 à 08:30",
)


def _read(answer: str, language: str = "fr", labels: tuple[str, ...] = MAILS) -> ChoiceAnswer:
    return read_choice_answer(answer, labels, language)


class TestAnOptionNamedByItsPosition:
    @pytest.mark.parametrize(
        ("answer", "language", "index"),
        [
            ("2", "fr", 2),
            ("le 2", "fr", 2),
            ("numéro 3", "fr", 3),
            ("le deuxième", "fr", 2),
            ("la première", "fr", 1),
            ("le dernier", "fr", 3),
            ("deux", "fr", 2),
            ("the second one", "en", 2),
            ("number 1", "en", 1),
            ("the last one", "en", 3),
            ("three", "en", 3),
            ("el segundo", "es", 2),
            ("el último", "es", 3),
            ("der zweite", "de", 2),
            ("die letzte", "de", 3),
            ("Nummer 2", "de", 2),
            ("il secondo", "it", 2),
            ("quello", "it", None),
            ("第二个", "zh-CN", 2),
            ("第3个", "zh-CN", 3),
            ("最后一个", "zh-CN", 3),
            ("2.", "de", 2),
            ("2ème", "fr", 2),
            ("1st", "en", 1),
        ],
    )
    def test_a_position_of_the_persons_language(
        self, answer: str, language: str, index: int | None
    ) -> None:
        read = _read(answer, language)
        if index is None:
            assert read.action == CHOICE_UNCLEAR
        else:
            assert (read.action, read.index) == (CHOICE_SELECT, index)

    def test_a_position_outside_the_options_is_not_a_choice(self) -> None:
        assert _read("5").action == CHOICE_UNCLEAR
        assert _read("0").action == CHOICE_UNCLEAR

    def test_two_positions_are_not_one_choice(self) -> None:
        assert _read("le 1 ou le 2").action == CHOICE_UNCLEAR

    def test_naming_an_option_that_does_not_exist_is_not_a_choice(self) -> None:
        assert _read("2 ou 5").action == CHOICE_UNCLEAR

    def test_another_languages_number_word_is_not_read(self) -> None:
        # « due » is two in Italian and a date in English.
        assert _read("the one due", "en").action == CHOICE_UNCLEAR
        assert _read("due", "it").index == 2

    def test_one_is_not_a_number_word(self) -> None:
        # « the garage one » names the garage, not option one.
        read = _read("the garage one", "en")
        assert (read.action, read.index) == (CHOICE_SELECT, 2)


class TestAnOptionNamedByWhatItIs:
    def test_a_word_only_one_option_carries(self) -> None:
        read = _read("celui de la facture")
        assert (read.action, read.index) == (CHOICE_SELECT, 2)

    def test_a_date_on_the_option_tells_it_apart(self) -> None:
        assert _read("celui de dimanche").index == 3
        assert _read("celui du 15 septembre").index == 1

    def test_a_word_every_option_carries_tells_nothing_apart(self) -> None:
        assert _read("celui de Marc").action == CHOICE_UNCLEAR

    def test_a_position_and_a_description_that_agree(self) -> None:
        read = _read("le deuxième, celui de la facture")
        assert (read.action, read.index) == (CHOICE_SELECT, 2)

    def test_a_position_and_a_description_that_disagree_are_asked_again(self) -> None:
        assert _read("le premier, celui de la facture").action == CHOICE_UNCLEAR

    def test_a_kind_word_no_option_carries_is_ignored(self) -> None:
        read = _read("le deuxième mail")
        assert (read.action, read.index) == (CHOICE_SELECT, 2)

    def test_words_carried_by_no_option_are_unclear(self) -> None:
        assert _read("celui de Paul").action == CHOICE_UNCLEAR


ZH_MAILS = (
    "Marc <marc@example.com> · 周末照片 · 2026年9月15日 星期二",
    "Marc <marc@example.com> · 修车发票 · 2026年9月14日 星期一",
    "Marc <marc@example.com> · 周六晚餐 · 2026年9月13日 星期日",
)


class TestAChineseAnswerNamedByWhatItIs:
    """Chinese writes no spaces: « 关于发票的那个 » is one run, read for what it shares."""

    @pytest.mark.parametrize(
        ("answer", "index"),
        [
            ("关于发票的那个", 2),
            ("照片那封", 1),
            ("晚餐的", 3),
            ("星期一那个", 2),
            ("就是修车发票", 2),
        ],
    )
    def test_the_words_one_option_carries(self, answer: str, index: int) -> None:
        read = _read(answer, "zh-CN", ZH_MAILS)
        assert (read.action, read.index) == (CHOICE_SELECT, index)

    @pytest.mark.parametrize("answer", ["Marc的那个", "那封邮件", "星期的"])
    def test_words_every_option_or_none_carries_are_unclear(self, answer: str) -> None:
        assert _read(answer, "zh-CN", ZH_MAILS).action == CHOICE_UNCLEAR

    def test_a_position_still_reads_as_one(self) -> None:
        assert _read("第二个", "zh-CN", ZH_MAILS).index == 2


class TestAnAnswerThatChoosesNothing:
    @pytest.mark.parametrize(
        ("answer", "language"),
        [
            ("non", "fr"),
            ("annule", "fr"),
            ("laisse tomber", "fr"),
            ("cancel", "en"),
            ("never mind", "en"),
            ("nein", "de"),
            ("cancela", "es"),
            ("annulla", "it"),
            ("取消", "zh-CN"),
        ],
    )
    def test_a_refusal_cancels(self, answer: str, language: str) -> None:
        assert _read(answer, language).action == CHOICE_CANCEL

    @pytest.mark.parametrize(
        ("answer", "language"),
        [
            ("aucun", "fr"),
            ("aucun des deux", "fr"),
            ("aucun, merci", "fr"),
            ("none of them", "en"),
            ("neither", "en"),
            ("ninguno", "es"),
            ("keiner davon", "de"),
            ("nessuno", "it"),
            ("都不是", "zh-CN"),
        ],
    )
    def test_none_of_them_asks_for_a_new_lookup(self, answer: str, language: str) -> None:
        assert _read(answer, language).action == CHOICE_NONE

    @pytest.mark.parametrize("answer", ["", "   ", "oui", "ok", "hmm"])
    def test_anything_else_is_unclear(self, answer: str) -> None:
        assert _read(answer).action == CHOICE_UNCLEAR


class TestTheQuestionAndTheReaderAgree:
    @pytest.mark.parametrize(
        ("label", "language"),
        [
            ("None of these", "en"),
            ("Aucun de ceux-là", "fr"),
            ("Keines davon", "de"),
            ("Ninguno de estos", "es"),
            ("Nessuno di questi", "it"),
            ("都不是", "zh-CN"),
        ],
    )
    def test_the_cards_none_button_read_as_typed_is_none(self, label: str, language: str) -> None:
        # The web card's « none » label (locales/*/translation.json): a person
        # may type what they see instead of clicking it.
        assert _read(label, language).action == CHOICE_NONE

    @pytest.mark.parametrize(
        ("message", "language"),
        [
            ("Number 2", "en"),
            ("Le numéro 2", "fr"),
            ("Nummer 2", "de"),
            ("El número 2", "es"),
            ("Il numero 2", "it"),
            ("第2个", "zh-CN"),
        ],
    )
    def test_the_message_a_click_sends_read_as_typed_is_the_same_choice(
        self, message: str, language: str
    ) -> None:
        # chat.hitl.choice.chosen (locales/*/translation.json), typed by hand.
        assert (_read(message, language).action, _read(message, language).index) == (
            CHOICE_SELECT,
            2,
        )

    @pytest.mark.parametrize("language", sorted(DISAMBIGUATION_ANSWER_WORDS))
    def test_the_words_the_question_suggests_are_read(self, language: str) -> None:
        # The question says « answer “none” or “cancel” »: both must be read so.
        none, cancel = DISAMBIGUATION_ANSWER_WORDS[language]
        assert _read(none, language).action == CHOICE_NONE
        assert _read(cancel, language).action == CHOICE_CANCEL


class TestTheResumePayload:
    def test_a_choice_travels_with_its_position(self) -> None:
        assert ChoiceAnswer(CHOICE_SELECT, 2).resume() == {
            "action": CHOICE_SELECT,
            FIELD_SELECTED_INDEX: 2,
        }
        assert ChoiceAnswer(CHOICE_NONE).resume() == {"action": CHOICE_NONE}

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            ({"action": "select", "selected_index": 2}, ChoiceAnswer(CHOICE_SELECT, 2)),
            ({"action": "none"}, ChoiceAnswer(CHOICE_NONE)),
            ({"action": "cancel"}, ChoiceAnswer(CHOICE_CANCEL)),
            ({"action": "select", "selected_index": 9}, ChoiceAnswer(CHOICE_UNCLEAR)),
            ({"action": "select", "selected_index": "2"}, ChoiceAnswer(CHOICE_UNCLEAR)),
            ({"action": "select", "selected_index": True}, ChoiceAnswer(CHOICE_UNCLEAR)),
            ({"action": "approve"}, ChoiceAnswer(CHOICE_UNCLEAR)),
            ("2", ChoiceAnswer(CHOICE_UNCLEAR)),
            (None, ChoiceAnswer(CHOICE_UNCLEAR)),
        ],
    )
    def test_a_resume_is_read_back_strictly(self, payload: object, expected: ChoiceAnswer) -> None:
        assert ChoiceAnswer.from_resume(payload, options=3) == expected
