"""The « which of these? » question, in six languages (ADR-367).

Several items the person was shown fit their words: the question names those
words, numbers the options and says how to answer — a number, « none of
them », or cancel.
"""

import pytest

from src.core.config import settings
from src.core.i18n import SUPPORTED_LANGUAGES
from src.core.i18n_hitl import DISAMBIGUATION_ANSWER_WORDS, HitlMessages, HitlMessageType

pytestmark = pytest.mark.unit

OPTIONS = ["Marc <m@example.com> · Photos", "Marc <m@example.com> · Facture"]


class TestTheFallback:
    def test_each_language_has_its_own(self) -> None:
        fallbacks = {
            HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, language)
            for language in SUPPORTED_LANGUAGES
        }
        assert len(fallbacks) == len(SUPPORTED_LANGUAGES)

    def test_an_unknown_language_reads_the_configured_default(self) -> None:
        assert HitlMessages.get_fallback(
            HitlMessageType.ENTITY_DISAMBIGUATION, "xyz"
        ) == HitlMessages.get_fallback(
            HitlMessageType.ENTITY_DISAMBIGUATION, settings.default_language
        )


class TestTheQuestion:
    def test_it_names_the_words_and_numbers_the_options(self) -> None:
        question = HitlMessages.format_disambiguation_question("Marc", OPTIONS, "fr")

        assert question.startswith("Plusieurs éléments affichés correspondent à « Marc » :")
        assert "**1.** Marc <m@example.com> · Photos\n**2.** Marc <m@example.com> · Facture" in (
            question
        )
        assert question.endswith("« aucun » si ce n'est aucun d'eux, ou « annule ».")

    @pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
    def test_every_language_says_how_to_answer(self, language: str) -> None:
        question = HitlMessages.format_disambiguation_question("Marc", OPTIONS, language)
        none, cancel = DISAMBIGUATION_ANSWER_WORDS[language]

        assert "Marc" in question and "**2.**" in question
        assert none in question and cancel in question

    def test_asked_again_it_says_the_answer_was_not_understood(self) -> None:
        first = HitlMessages.format_disambiguation_question("Marc", OPTIONS, "en")
        again = HitlMessages.format_disambiguation_question("Marc", OPTIONS, "en", reask=True)

        assert again == f"I didn't catch which one you mean.\n\n{first}"

    @pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
    def test_items_a_lookup_found_are_never_said_to_have_been_shown(self, language: str) -> None:
        found = HitlMessages.format_disambiguation_question("", OPTIONS, language, found=True)
        shown = HitlMessages.format_disambiguation_question("Marc", OPTIONS, language)

        assert found.split("\n\n")[0] != shown.split("\n\n")[0]
        assert "**2.**" in found
        assert all(word in found for word in DISAMBIGUATION_ANSWER_WORDS[language])

    def test_the_found_header_names_no_description(self) -> None:
        found = HitlMessages.format_disambiguation_question("", OPTIONS, "fr", found=True)
        assert found.startswith("J'ai trouvé plusieurs éléments qui peuvent correspondre :")
        assert "« »" not in found

    def test_no_option_reads_the_fallback(self) -> None:
        assert HitlMessages.format_disambiguation_question("Marc", [], "fr") == (
            HitlMessages.get_fallback(HitlMessageType.ENTITY_DISAMBIGUATION, "fr")
        )

    def test_a_language_variant_reads_its_language(self) -> None:
        assert HitlMessages.format_disambiguation_question("Marc", OPTIONS, "zh") == (
            HitlMessages.format_disambiguation_question("Marc", OPTIONS, "zh-CN")
        )
