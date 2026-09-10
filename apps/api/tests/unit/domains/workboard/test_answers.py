"""What the person's comment means for the action LIA is waiting on (lot 7).

Three verdicts and one direction of safety: only a BARE approval approves,
only a bare refusal refuses, and everything else — an approval with a
condition, a refusal with an alternative, a question, a blank — is an
amendment LIA re-reads. Misreading « oui mais… » as « oui » would perform an
action the person did not want; misreading it as an amendment costs one more
question. Six languages, folded and tokenised the way the answer is.
"""

from __future__ import annotations

import pytest

from src.core.i18n_workboard import ANSWER_APPROVAL_PHRASES, ANSWER_REFUSAL_PHRASES
from src.domains.workboard.answers import Answer, classify_answer

pytestmark = pytest.mark.unit


class TestABareApproval:
    @pytest.mark.parametrize(
        "text",
        [
            "oui",
            "Oui.",
            "OK",
            "ok !",
            "D'accord",
            "Vas-y",
            "Oui, vas-y !",
            "oui merci",
            "c'est bon",
            "je confirme",
            "yes",
            "Yes please",
            "go ahead",
            "ok, go ahead",
            "confirmed",
            "do it",
            "ja",
            "Ja, bitte.",
            "einverstanden",
            "mach das",
            "sí",
            "Si",
            "vale",
            "adelante",
            "de acuerdo",
            "sì",
            "va bene",
            "procedi",
            "好的",
            "可以",
            "确认",
            "好的谢谢",
        ],
    )
    def test_it_approves(self, text: str) -> None:
        assert classify_answer(text) is Answer.APPROVE


class TestABareRefusal:
    @pytest.mark.parametrize(
        "text",
        [
            "non",
            "Non.",
            "non merci",
            "annule",
            "Annule tout",
            "laisse tomber",
            "pas d'accord",
            "no",
            "No thanks",
            "cancel",
            "cancel it",
            "never mind",
            "don't",
            "nein",
            "Nein, danke.",
            "abbrechen",
            "lass es",
            "cancela",
            "no gracias",
            "annulla",
            "lascia perdere",
            "no grazie",
            "取消",
            "不要",
            "算了",
        ],
    )
    def test_it_refuses(self, text: str) -> None:
        assert classify_answer(text) is Answer.REFUSE


class TestEverythingElseIsAnAmendment:
    @pytest.mark.parametrize(
        "text",
        [
            "Oui mais change le sujet",
            "oui, sauf le dernier paragraphe",
            "Non, envoie plutôt à Paul",
            "yes but wait until Monday",
            "no, send it to Paul instead",
            "Peux-tu ajouter Marie en copie ?",
            "Envoie plutôt à paul@example.org",
            "ja, aber erst morgen",
            "sí, pero sin el adjunto",
            "sì ma domani",
            "好的，但请明天发",
            "merci",
            "?",
            "",
            "   ",
            "oui non",
            "ok cancel",
        ],
    )
    def test_it_amends(self, text: str) -> None:
        assert classify_answer(text) is Answer.AMEND


class TestTheReadingIsRobust:
    def test_accents_and_case_do_not_matter(self) -> None:
        assert classify_answer("CONFIRMÉ") is Answer.APPROVE
        assert classify_answer("confirme") is Answer.APPROVE
        assert classify_answer("SÍ") is Answer.APPROVE

    def test_punctuation_is_not_part_of_the_answer(self) -> None:
        assert classify_answer("oui !!!") is Answer.APPROVE
        assert classify_answer("« non »") is Answer.REFUSE
        assert classify_answer("好的。") is Answer.APPROVE

    def test_a_soft_word_alone_means_nothing(self) -> None:
        for text in ("merci", "please", "danke", "tout", "it"):
            assert classify_answer(text) is Answer.AMEND, text

    def test_the_two_lexicons_never_overlap(self) -> None:
        """A word in both would make the order of the checks the decision."""
        from src.domains.workboard.answers import _tokens

        approvals = {_tokens(phrase) for phrase in ANSWER_APPROVAL_PHRASES}
        refusals = {_tokens(phrase) for phrase in ANSWER_REFUSAL_PHRASES}
        assert not approvals & refusals

    def test_every_language_has_both_families(self) -> None:
        for approval, refusal in (
            ("oui", "non"),
            ("yes", "no"),
            ("ja", "nein"),
            ("sí", "cancela"),
            ("sì", "annulla"),
            ("好的", "取消"),
        ):
            assert classify_answer(approval) is Answer.APPROVE, approval
            assert classify_answer(refusal) is Answer.REFUSE, refusal
