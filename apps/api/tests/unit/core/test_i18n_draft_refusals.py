"""What a refused confirmed draft's card reads, code by code.

On a confirmation no model writes the answer: the card IS the answer
(ADR-303 amendment 2026-10-14). A code is never shown; each one an owner
produces is either put into words here or DECLARED generic with the reason it
names nothing the person could act on. The census of what the code produces
is ``tests/unit/domains/agents/test_draft_refusal_vocabulary_guard.py``.
"""

from __future__ import annotations

import pytest

from src.core.i18n_draft_refusals import (
    GENERIC_REFUSAL_CODES,
    WORDED_REFUSAL_CODES,
    get_draft_refusal_message,
)
from src.core.i18n_drafts import (
    get_draft_already_claimed_message,
    get_draft_cancel_message,
    get_draft_error_message,
)
from src.core.i18n_types import Language

pytestmark = pytest.mark.unit

_LANGUAGES: tuple[Language, ...] = ("fr", "en", "es", "de", "it", "zh-CN")

#: Codes whose sentence was missing on 2026-10-14 — the gate's own refusals,
#: the application family's common causes and a cancel that could not withdraw.
_NEWLY_WORDED = (
    "CONFIRMATION_MISSING",
    "DEPENDENCY_ERROR",
    "EXPIRED",
    "STALE_STATE",
    "FORBIDDEN",
    "NOT_FOUND_OR_UNAUTHORIZED",
    "CAPABILITY_DISABLED",
    "BUSY",
    "RATE_LIMIT_EXCEEDED",
    "USAGE_LIMIT_EXCEEDED",
    "instance_budget_exhausted",
    "TIMEOUT",
    "CONSTRAINT_VIOLATION",
    "INVALID_INPUT",
    "CANCELLATION_UNAVAILABLE",
    "CANCELLED",
)


class TestEveryWordedCodeIsASentence:
    @pytest.mark.parametrize("language", _LANGUAGES)
    @pytest.mark.parametrize("code", sorted(WORDED_REFUSAL_CODES))
    def test_in_every_language_and_never_the_code_itself(
        self, code: str, language: Language
    ) -> None:
        sentence = get_draft_refusal_message(code, language)

        assert sentence
        assert code not in sentence
        assert sentence != get_draft_error_message(language) or code in {"ALREADY_CLAIMED"}

    @pytest.mark.parametrize("code", _NEWLY_WORDED)
    def test_the_causes_missing_on_2026_10_14_are_worded(self, code: str) -> None:
        assert code in WORDED_REFUSAL_CODES

    def test_the_six_languages_say_six_different_things(self) -> None:
        for code in sorted(WORDED_REFUSAL_CODES - {"ALREADY_CLAIMED"}):
            sentences = {get_draft_refusal_message(code, language) for language in _LANGUAGES}
            assert len(sentences) == len(_LANGUAGES), code


class TestOneCauseOneWording:
    @pytest.mark.parametrize(
        ("alias", "same_as"),
        [
            ("STALE_SELECTION", "STALE_STATE"),
            ("INTERACTION_EXPIRED", "EXPIRED"),
            ("NOT_FOUND", "NOT_FOUND_OR_UNAUTHORIZED"),
            ("EXTERNAL_API_ERROR", "DEPENDENCY_ERROR"),
        ],
    )
    def test_an_alias_reads_its_cause(self, alias: str, same_as: str) -> None:
        for language in _LANGUAGES:
            assert get_draft_refusal_message(alias, language) == get_draft_refusal_message(
                same_as, language
            )


class TestWhatASentenceMayClaim:
    """A sentence claims « nothing was done » only where every producer
    refuses BEFORE any effect; elsewhere it names the cause and asks to check."""

    def test_the_gate_s_missing_confirmation_says_nothing_ran(self) -> None:
        assert "rien n’a été exécuté" in get_draft_refusal_message("CONFIRMATION_MISSING", "fr")

    def test_a_cancel_that_could_not_withdraw_says_it_may_have_started(self) -> None:
        sentence = get_draft_refusal_message("CANCELLATION_UNAVAILABLE", "fr")
        assert "peut-être déjà commencé" in sentence
        assert "Vérifie" in sentence

    def test_a_committed_receipt_outranks_any_code(self) -> None:
        for code in ("STALE_STATE", "FORBIDDEN", "TIMEOUT", None):
            assert get_draft_refusal_message(
                code, "en", committed=True
            ) == get_draft_refusal_message("POST_COMMIT_FAILURE", "en")

    def test_an_already_claimed_draft_keeps_its_own_sentence(self) -> None:
        assert get_draft_refusal_message("ALREADY_CLAIMED", "de") == (
            get_draft_already_claimed_message("de")
        )

    @pytest.mark.parametrize("language", _LANGUAGES)
    def test_an_already_cancelled_command_reads_the_existing_cancellation_copy(
        self, language: Language
    ) -> None:
        assert get_draft_refusal_message("CANCELLED", language) == get_draft_cancel_message(
            "application_action", language
        )


class TestAGenericCodeIsADecision:
    def test_every_generic_code_carries_its_reason(self) -> None:
        for code, reason in GENERIC_REFUSAL_CODES.items():
            assert len(reason) > 20, code

    def test_a_generic_code_reads_the_generic_sentence(self) -> None:
        for code in GENERIC_REFUSAL_CODES:
            assert get_draft_refusal_message(code, "it") == get_draft_error_message("it")

    def test_no_code_is_both_worded_and_generic(self) -> None:
        assert not WORDED_REFUSAL_CODES & set(GENERIC_REFUSAL_CODES)
