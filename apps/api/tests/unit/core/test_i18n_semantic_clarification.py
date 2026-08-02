"""A rejected plan must ask the user a real question, never show its diagnosis.

The defect this closes, measured in production 2026-08-02 (4 occurrences in 30
days): when a mutation plan exhausted its auto-replans, ``semantic_validator_node``
recycled the ISSUE DESCRIPTION as the clarification question. The user, whose
account is in French, received::

    for_each pattern issue detected
    Fabricated placeholder contact detail: step_2.to='jerome@example.com'

The first is jargon; the second leaks an implementation path AND a fabricated
address the user could mistake for a real one. The comment above that code
claimed "the issue descriptions are already localized" — measured false on all
five programmatic-rejection sites, every one an English literal whose own
docstring says it is "for the trace and the replan prompt".

So the questions live here instead: one per ``SemanticIssueType``, in the six
supported languages, written for someone who has never read the code.
"""

from __future__ import annotations

import pytest

from src.core.i18n import DEFAULT_LANGUAGE
from src.core.i18n_hitl import (
    _SEMANTIC_ISSUE_QUESTIONS,
    HitlMessages,
)
from src.domains.agents.orchestration.validation_models import SemanticIssueType

pytestmark = pytest.mark.unit

#: The backend-canonical codes. `zh-CN`, never `zh` (CLAUDE.md: the backend
#: keys on zh-CN and `normalize_language` is the single funnel).
_LANGS = {"fr", "en", "es", "de", "it", "zh-CN"}


class TestEveryIssueTypeCanBeAsked:
    """Completeness: an issue with no question is an issue with no question ASKED."""

    def test_every_semantic_issue_type_has_an_entry(self) -> None:
        missing = [t.value for t in SemanticIssueType if t.value not in _SEMANTIC_ISSUE_QUESTIONS]
        assert not missing, (
            f"{len(missing)} SemanticIssueType(s) without a clarification question: {missing}. "
            f"A missing entry falls back to a generic question, which is exactly the "
            f"regression this table exists to prevent."
        )

    @pytest.mark.parametrize("issue_type", [t.value for t in SemanticIssueType])
    def test_each_entry_covers_the_six_languages(self, issue_type: str) -> None:
        entry = _SEMANTIC_ISSUE_QUESTIONS.get(issue_type, {})
        assert set(entry) == _LANGS, (
            f"{issue_type} covers {sorted(entry)} instead of {sorted(_LANGS)} — a user "
            f"whose account is in a missing language would silently get English."
        )

    def test_no_entry_is_keyed_on_something_the_enum_never_yields(self) -> None:
        """The completeness check has to hold in BOTH directions.

        ``SemanticIssueType`` declares ``MISSING_DEPENDENCY`` and
        ``AMBIGUOUS_INTENT`` as ALIASES — their ``.value`` is
        ``ghost_dependency`` / ``dangerous_ambiguity``, and iterating the enum
        never yields the alias name. A table keyed on the alias name therefore
        holds a question no lookup can ever reach, while counting as coverage
        for a reader. That is precisely how this table was first written.
        """
        unreachable = sorted(set(_SEMANTIC_ISSUE_QUESTIONS) - {t.value for t in SemanticIssueType})
        assert not unreachable, (
            f"{len(unreachable)} question(s) no SemanticIssueType can yield: {unreachable}. "
            f"An enum alias is not a key — use the value it aliases."
        )


class TestQuestionsAreWrittenForAUser:
    """A clarification is read by a person, not by a maintainer."""

    @pytest.mark.parametrize("issue_type", [t.value for t in SemanticIssueType])
    def test_no_technical_jargon_leaks_into_a_question(self, issue_type: str) -> None:
        """No identifier, no code path, no internal vocabulary.

        `for_each`, `step_2.to`, `$steps` and friends are what the user actually
        received in production. None of them means anything to them.
        """
        forbidden = ("for_each", "$steps", "step_", "_tool", "placeholder", "cardinality", "None")
        offenders: list[str] = []
        for lang, text in _SEMANTIC_ISSUE_QUESTIONS[issue_type].items():
            for token in forbidden:
                if token in text:
                    offenders.append(f"{lang}: {token!r} in {text!r}")
        assert not offenders, f"{issue_type} exposes internal vocabulary: {offenders}"

    @pytest.mark.parametrize("issue_type", [t.value for t in SemanticIssueType])
    def test_each_question_actually_asks_something(self, issue_type: str) -> None:
        """A clarification that does not ask leaves the user with nothing to do."""
        for lang, text in _SEMANTIC_ISSUE_QUESTIONS[issue_type].items():
            assert text.strip(), f"{issue_type}/{lang} is empty"
            assert text.rstrip().endswith(("?", "？")), (
                f"{issue_type}/{lang} is not a question: {text!r}. The user is being "
                f"asked to unblock the turn — the sentence must make that obvious."
            )

    def test_french_keeps_the_product_tone(self) -> None:
        """The app addresses the user informally ("tu"), everywhere else already."""
        formal = [
            t
            for t, entry in _SEMANTIC_ISSUE_QUESTIONS.items()
            if "vous" in entry["fr"].lower().split()
        ]
        assert not formal, f"French questions drifting to 'vous': {formal}"


class TestAccessor:
    """`get_semantic_issue_question` behaves like its siblings in this module."""

    def test_returns_the_requested_language(self) -> None:
        fr = HitlMessages.get_semantic_issue_question(
            SemanticIssueType.CARDINALITY_MISMATCH.value, "fr"
        )
        assert fr == _SEMANTIC_ISSUE_QUESTIONS["cardinality_mismatch"]["fr"]

    @pytest.mark.parametrize("raw", ["zh", "zh_CN", "zh-cn", "zh-CN"])
    def test_every_chinese_variant_lands_on_the_backend_canonical_code(self, raw: str) -> None:
        assert (
            HitlMessages.get_semantic_issue_question("cardinality_mismatch", raw)
            == _SEMANTIC_ISSUE_QUESTIONS["cardinality_mismatch"]["zh-CN"]
        )

    def test_regional_variant_falls_back_to_its_base_language(self) -> None:
        assert (
            HitlMessages.get_semantic_issue_question("cardinality_mismatch", "fr-FR")
            == _SEMANTIC_ISSUE_QUESTIONS["cardinality_mismatch"]["fr"]
        )

    def test_unsupported_language_falls_back_to_the_application_default(self) -> None:
        """The module's contract, shared by its ~20 sibling accessors.

        ``_normalize_language`` maps anything unsupported to DEFAULT_LANGUAGE,
        NOT to English. An accessor behaving differently from all the others
        would be a trap for the next reader.
        """
        assert (
            HitlMessages.get_semantic_issue_question("cardinality_mismatch", "ja")
            == _SEMANTIC_ISSUE_QUESTIONS["cardinality_mismatch"][DEFAULT_LANGUAGE]
        )

    def test_unknown_issue_type_yields_the_generic_clarification_fallback(self) -> None:
        """Never empty, never a KeyError: an unknown type still gets a real question."""
        text = HitlMessages.get_semantic_issue_question("something_new_and_unmapped", "fr")
        assert text.strip()
        assert text.rstrip().endswith("?")


class TestBootAssertActuallyGuards:
    """The ADR-085 assert must FAIL on a hole, not merely exist.

    A completeness assert that cannot fail is worse than none: it reads as a
    guarantee on every review while guarding nothing. These cases amputate the
    table three ways and require the boot check to refuse each one.
    """

    def test_nominal_table_passes(self) -> None:
        HitlMessages.assert_semantic_issue_questions_coverage()

    def test_a_type_without_a_question_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        victim = next(iter(SemanticIssueType)).value
        amputated = {k: v for k, v in _SEMANTIC_ISSUE_QUESTIONS.items() if k != victim}
        monkeypatch.setattr("src.core.i18n_hitl._SEMANTIC_ISSUE_QUESTIONS", amputated)

        with pytest.raises(AssertionError, match="without a clarification question"):
            HitlMessages.assert_semantic_issue_questions_coverage()

    def test_a_question_no_type_can_yield_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The alias trap, pinned: ``MISSING_DEPENDENCY`` is not a key."""
        polluted = dict(_SEMANTIC_ISSUE_QUESTIONS)
        polluted["missing_dependency"] = dict.fromkeys(_LANGS, "orphan")
        monkeypatch.setattr("src.core.i18n_hitl._SEMANTIC_ISSUE_QUESTIONS", polluted)

        with pytest.raises(AssertionError, match="no SemanticIssueType can yield"):
            HitlMessages.assert_semantic_issue_questions_coverage()

    def test_an_entry_missing_a_language_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        victim = next(iter(SemanticIssueType)).value
        truncated = dict(_SEMANTIC_ISSUE_QUESTIONS)
        truncated[victim] = {k: v for k, v in truncated[victim].items() if k != "zh-CN"}
        monkeypatch.setattr("src.core.i18n_hitl._SEMANTIC_ISSUE_QUESTIONS", truncated)

        with pytest.raises(AssertionError, match="missing languages"):
            HitlMessages.assert_semantic_issue_questions_coverage()
