"""End-to-end guard: a HITL turn (EDIT + REJECT + AMBIGUOUS) for a German/Chinese
user emits no French in any of the messages surfaced to the conversation.

Covers the messages that are actually EMITTED on a HITL resume:
- the reformulated intent that replaces the user's turn on an EDIT,
- the enriched HumanMessage injected on a REJECT,
- the user-rejection summary fed to the response node,
- the static notices the resume mapper emits when the classifier produced no
  usable question (demoted EDIT, ambiguous answer).

That last surface is here because it was missing: the mapper hardcoded French
("Peux-tu préciser ce que tu veux modifier ?", "Réponse ambiguë…") and the
draft-critique interaction streams that text VERBATIM to the user, so every
non-French user saw French on the most common HITL branch of all.
"""

from __future__ import annotations

import pytest

from src.core.i18n_hitl import HitlMessages, HitlResumeMessage
from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt
from src.domains.agents.services.hitl.resumption_strategies import (
    build_edit_reformulated_intent,
)

pytestmark = [pytest.mark.unit]

# French-specific fragments that must never appear for a non-FR user.
_FRENCH_FRAGMENTS = (
    "recherche",
    "envoie à",
    "exécute",
    "avec les paramètres modifiés",
    "annule",
    "refus utilisateur",
    "l'utilisateur",
    "réponse attendue",
    "a refusé",
    "aucun problème",
    "destinataire",
    "brouillon",
)


def _assert_no_french(text: str, lang: str, where: str) -> None:
    low = text.lower()
    for fragment in _FRENCH_FRAGMENTS:
        assert fragment not in low, f"[{lang}/{where}] French '{fragment}' leaked: {text!r}"


@pytest.mark.parametrize(
    "lang,edit_marker,reject_marker,refusal_marker",
    [
        ("de", "suche", "BENUTZERABLEHNUNG", "Der Benutzer hat diese Aktion abgelehnt"),
        ("zh", "搜索", "用户拒绝", "用户拒绝了此操作"),
    ],
)
def test_hitl_edit_and_reject_emit_no_french(
    lang: str, edit_marker: str, reject_marker: str, refusal_marker: str
) -> None:
    # --- EDIT: reformulated intent that replaces the user's message ---
    edit_query = build_edit_reformulated_intent(
        [{"modification_type": "edit_params", "new_parameters": {"query": "jean"}}], lang
    )
    assert edit_query is not None
    _assert_no_french(edit_query, lang, "edit.query")
    assert edit_marker in edit_query

    edit_generic = build_edit_reformulated_intent(
        [{"modification_type": "edit_params", "new_parameters": {"max_results": 10}}], lang
    )
    assert edit_generic is not None
    _assert_no_french(edit_generic, lang, "edit.generic")
    assert "max_results=10" in edit_generic

    # --- REJECT: enriched HumanMessage injected into the conversation ---
    user_refusal = "nein" if lang == "de" else "取消"
    reject_msg = HitlMessages.get_reject_enriched_message(user_refusal, lang)
    _assert_no_french(reject_msg, lang, "reject.enriched")
    assert reject_marker in reject_msg
    assert user_refusal in reject_msg

    # --- Rejection summary fed to the response node ---
    summary = format_agent_results_for_prompt(
        {"3:reminder_agent": {"status": "success", "data": {"user_rejected": True}}},
        current_turn_id=3,
        user_language=lang,
    )
    _assert_no_french(summary, lang, "agent_results.rejection")
    assert refusal_marker in summary

    # --- AMBIGUOUS: the static notices the resume mapper emits itself ---
    for message in HitlResumeMessage:
        text = HitlMessages.get_resume_message(message, lang)
        _assert_no_french(text, lang, f"resume.{message.value}")
        assert text.strip(), f"[{lang}] resume message {message.value} is empty"


@pytest.mark.parametrize("lang", ["de", "zh", "es", "it", "en"])
def test_resume_mapper_notices_reach_the_user_in_their_language(lang: str) -> None:
    """The mapper's own fallbacks — not the classifier's — are localized.

    These three payloads are what a non-French user actually receives when the
    classifier returns nothing usable: the draft is re-presented with the
    clarify question, or the operation is rejected with the ambiguity notice.
    """
    from src.domains.agents.services.hitl_classifier import ClassificationResult
    from src.domains.agents.services.orchestration.approval_decision import (
        _map_draft_critique_result,
        _map_for_each_result,
        _map_generic_result,
    )

    ambiguous = ClassificationResult(
        decision="AMBIGUOUS",
        confidence=0.4,
        reasoning="unclear",
        clarification_question=None,  # the classifier produced none
    )

    draft = _map_draft_critique_result(ambiguous, "draft-1", "hmm", "run-1", lang)
    assert draft["action"] == "clarify"
    assert draft["clarification_question"] == HitlMessages.get_resume_message(
        HitlResumeMessage.CLARIFY_WHAT_TO_CHANGE, lang
    )

    for_each = _map_for_each_result(ambiguous, "hmm", "run-1", lang)
    assert for_each["decision"] == "REJECT"
    assert for_each["rejection_reason"] == HitlMessages.get_resume_message(
        HitlResumeMessage.AMBIGUOUS_CANCELLED, lang
    )

    generic = _map_generic_result(ambiguous, [], "run-1", lang)
    assert generic["decision"] == "REJECT"
    assert generic["rejection_reason"] == HitlMessages.get_resume_message(
        HitlResumeMessage.AMBIGUOUS_SPECIFY, lang
    )

    if lang != "fr":
        for payload, key in (
            (draft, "clarification_question"),
            (for_each, "rejection_reason"),
            (generic, "rejection_reason"),
        ):
            _assert_no_french(payload[key], lang, key)


def test_classifier_question_wins_over_the_static_notice() -> None:
    """A question the LLM produced is more specific than any fallback.

    Both demotion branches used to overwrite (or ignore) it; the mapper must
    surface it untouched when present.
    """
    from src.domains.agents.services.hitl_classifier import ClassificationResult
    from src.domains.agents.services.orchestration.approval_decision import (
        _map_draft_critique_result,
    )

    result = ClassificationResult(
        decision="AMBIGUOUS",
        confidence=0.4,
        reasoning="unclear",
        clarification_question="Welchen Betreff möchtest du?",
    )
    payload = _map_draft_critique_result(result, "draft-1", "hmm", "run-1", "de")
    assert payload["clarification_question"] == "Welchen Betreff möchtest du?"


def test_resume_messages_are_exhaustive() -> None:
    """Every HitlResumeMessage has a template in all six languages.

    Kind coverage here; language coverage is enforced by the i18n parity guard.
    """
    from src.core.i18n import SUPPORTED_LANGUAGES
    from src.core.i18n_hitl import _RESUME_MESSAGES

    missing_kinds = set(HitlResumeMessage) - set(_RESUME_MESSAGES)
    assert not missing_kinds, f"resume messages missing kinds: {sorted(missing_kinds)}"
    for kind, langs in _RESUME_MESSAGES.items():
        missing_langs = set(SUPPORTED_LANGUAGES) - set(langs)
        assert not missing_langs, f"{kind}: missing languages {sorted(missing_langs)}"
