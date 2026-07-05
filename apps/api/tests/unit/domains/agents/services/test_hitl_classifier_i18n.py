"""The HITL classifier few-shot examples must be language-neutral (English).

The classifier prompt receives few-shot examples for the detected action type.
They used to be hardcoded French utterances ("oui", "vas-y", "non annule"),
which biases classification for German/Spanish/Italian/Chinese users. Per the
codebase convention (LLM prompts are English), the examples are externalized to
a versioned prompt file in English; the user's actual response may be in ANY
language and is classified by intent structure, not by matching French words.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.constants import (
    ACTION_TYPE_DELETE,
    ACTION_TYPE_DRAFT_CRITIQUE,
    ACTION_TYPE_FOR_EACH_CONFIRMATION,
    ACTION_TYPE_GENERIC,
    ACTION_TYPE_PLAN_APPROVAL,
    ACTION_TYPE_SEARCH,
    ACTION_TYPE_SEND,
)
from src.domains.agents.services.hitl_classifier import (
    HitlResponseClassifier,
    _load_classifier_example_sections,
)

pytestmark = [pytest.mark.unit]

# French tokens that must not appear in the (now English) example blocks.
_FRENCH_MARKERS = (
    "vas-y",
    "annule",
    "laisse tomber",
    "c'est bon",
    "d'accord",
    "recherche ",
    "envoie à",
    "supprime",
    "réponse attendue",
    "refus sans",
    "modifie le",
    "retire les",
    "enlève",
)

_ALL_ACTION_TYPES = (
    ACTION_TYPE_SEARCH,
    ACTION_TYPE_SEND,
    ACTION_TYPE_DELETE,
    ACTION_TYPE_DRAFT_CRITIQUE,
    ACTION_TYPE_FOR_EACH_CONFIRMATION,
    ACTION_TYPE_GENERIC,
)


def _classifier() -> HitlResponseClassifier:
    with patch(
        "src.domains.agents.services.hitl_classifier.get_llm",
        return_value=MagicMock(),
    ):
        return HitlResponseClassifier()


@pytest.mark.parametrize("action_type", _ALL_ACTION_TYPES)
def test_contextual_examples_have_no_french(action_type: str) -> None:
    examples = _classifier()._get_contextual_examples(action_type, "").lower()
    for marker in _FRENCH_MARKERS:
        assert marker not in examples, f"French '{marker}' leaked into '{action_type}' examples"


@pytest.mark.parametrize("action_type", _ALL_ACTION_TYPES)
def test_contextual_examples_are_english_and_nonempty(action_type: str) -> None:
    examples = _classifier()._get_contextual_examples(action_type, "")
    assert examples.strip()
    assert "APPROVE" in examples and "REJECT" in examples


# The action-description context is fed into the SAME classifier prompt, so it
# must be English too (no residual French bias).


def test_format_action_context_is_english() -> None:
    clf = _classifier()
    assert clf._format_action_context([]) == "an action"
    ctx = clf._format_action_context(
        [{"tool_name": "search_contacts", "tool_args": {"query": "jean"}}]
    )
    low = ctx.lower()
    assert "search for" in low
    assert "recherche" not in low and "paramètre" not in low


def test_format_draft_critique_context_is_english() -> None:
    ctx = _classifier()._format_draft_critique_context(
        {"draft_type": "email", "draft_content": {"to": "a@b.com", "subject": "S", "body": "B"}}
    )
    low = ctx.lower()
    assert "email draft to" in low
    assert "brouillon" not in low and "contenu" not in low and "sujet" not in low


def test_format_plan_approval_context_is_english() -> None:
    ctx = _classifier()._format_plan_approval_context(
        {"plan_summary": {"steps": [], "total_steps": 2}}
    )
    low = ctx.lower()
    assert "execution plan with 2 steps" in low
    assert "exécution" not in low and "étapes" not in low


def test_format_for_each_context_is_english() -> None:
    ctx = _classifier()._format_for_each_context(
        {
            "total_affected": 3,
            "item_previews": [{"x": "a"}],
            "steps": [{"tool_name": "delete_emails"}],
        }
    )
    low = ctx.lower()
    assert "deletion on 3 item" in low
    assert "opération" not in low and "élément" not in low and "concernés" not in low


def test_classifier_example_sections_cover_all_action_types() -> None:
    """Every specialized action type has its OWN versioned section.

    Guards against a renamed/misspelled section key silently falling back to the
    generic 'default' block (which would drop action-specific EDIT guidance).
    """
    sections = _load_classifier_example_sections()
    expected = {
        ACTION_TYPE_SEARCH,
        ACTION_TYPE_SEND,
        ACTION_TYPE_DELETE,
        ACTION_TYPE_PLAN_APPROVAL,
        ACTION_TYPE_DRAFT_CRITIQUE,
        ACTION_TYPE_FOR_EACH_CONFIRMATION,
        "default",
    }
    missing = expected - set(sections)
    assert not missing, f"classifier example sections missing: {sorted(missing)}"
    for key in expected:
        assert sections[key].strip(), f"section '{key}' is empty"
