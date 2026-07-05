"""End-to-end guard: a HITL turn (EDIT + REJECT) for a German/Chinese user emits
no French in any of the messages surfaced to the conversation.

Covers the messages that are actually EMITTED on a HITL resume:
- the reformulated intent that replaces the user's turn on an EDIT,
- the enriched HumanMessage injected on a REJECT,
- the user-rejection summary fed to the response node.
"""

from __future__ import annotations

import pytest

from src.core.i18n_hitl import HitlMessages
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
