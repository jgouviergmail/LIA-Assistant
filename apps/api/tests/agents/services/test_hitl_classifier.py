"""
Tests for HitlResponseClassifier.

Tests classification of natural language responses into approve/reject/edit/ambiguous.
"""

import os

import pytest

from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

# Skip all tests if OPENAI_API_KEY is not set (integration tests that call real LLM)
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for integration tests with real LLM",
)


@pytest.fixture
def classifier():
    """Create classifier instance for tests."""
    return HitlResponseClassifier(model="gpt-4.1-nano")


@pytest.fixture
def sample_action_context():
    """Sample action context for search contacts."""
    return [
        {
            "tool_name": "search_contacts_tool",
            "tool_args": {"query": "jean"},
            "tool_description": "Recherche contacts par nom",
        }
    ]


# ============================================================================
# APPROVE Classification Tests
# ============================================================================


@pytest.mark.asyncio
async def test_classify_approve_oui(classifier, sample_action_context):
    """Test classification of 'oui' as APPROVE."""
    result = await classifier.classify(user_response="oui", action_context=sample_action_context)

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8  # High confidence for clear approval
    assert result.reasoning is not None
    # edited_params should be None or empty dict for APPROVE
    assert result.edited_params is None or result.edited_params == {}
    assert result.clarification_question is None


@pytest.mark.asyncio
async def test_classify_approve_ok(classifier, sample_action_context):
    """Test classification of 'ok' as APPROVE."""
    result = await classifier.classify(user_response="ok", action_context=sample_action_context)

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_classify_approve_daccord(classifier, sample_action_context):
    """Test classification of "d'accord" as APPROVE."""
    result = await classifier.classify(
        user_response="d'accord", action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_classify_approve_vas_y(classifier, sample_action_context):
    """Test classification of 'vas-y' as APPROVE."""
    result = await classifier.classify(user_response="vas-y", action_context=sample_action_context)

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.7


@pytest.mark.asyncio
async def test_classify_approve_confirme(classifier, sample_action_context):
    """Test classification of 'confirme' as APPROVE."""
    result = await classifier.classify(
        user_response="confirme", action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_classify_approve_bien_sur(classifier, sample_action_context):
    """Test classification of 'bien sûr' as APPROVE."""
    result = await classifier.classify(
        user_response="bien sûr", action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.8


# ============================================================================
# REJECT Classification Tests
# ============================================================================


@pytest.mark.asyncio
async def test_classify_reject_non(classifier, sample_action_context):
    """Test classification of 'non' as REJECT."""
    result = await classifier.classify(user_response="non", action_context=sample_action_context)

    assert result.decision == "REJECT"
    assert result.confidence >= 0.8
    assert result.reasoning is not None
    # edited_params should be None or empty dict for REJECT
    assert result.edited_params is None or result.edited_params == {}


@pytest.mark.asyncio
async def test_classify_reject_stop(classifier, sample_action_context):
    """Test classification of 'stop' as REJECT."""
    result = await classifier.classify(user_response="stop", action_context=sample_action_context)

    assert result.decision == "REJECT"
    assert result.confidence >= 0.7


@pytest.mark.asyncio
async def test_classify_reject_annule(classifier, sample_action_context):
    """Test classification of 'annule' as REJECT."""
    result = await classifier.classify(user_response="annule", action_context=sample_action_context)

    assert result.decision == "REJECT"
    assert result.confidence >= 0.8


@pytest.mark.asyncio
async def test_classify_reject_ko(classifier, sample_action_context):
    """Test classification of 'ko' as REJECT."""
    result = await classifier.classify(user_response="ko", action_context=sample_action_context)

    assert result.decision == "REJECT"
    assert result.confidence >= 0.7


@pytest.mark.asyncio
async def test_classify_reject_pas_maintenant(classifier, sample_action_context):
    """Test classification of 'pas maintenant' as REJECT."""
    result = await classifier.classify(
        user_response="pas maintenant", action_context=sample_action_context
    )

    assert result.decision == "REJECT"
    assert result.confidence >= 0.7


# ============================================================================
# EDIT Classification Tests
# ============================================================================


@pytest.mark.asyncio
async def test_classify_edit_pas_x_mais_y(classifier, sample_action_context):
    """Test classification of 'pas X mais Y' as EDIT."""
    result = await classifier.classify(
        user_response="pas jean mais Huà", action_context=sample_action_context
    )

    assert result.decision == "EDIT"
    assert result.confidence >= 0.7
    assert result.reasoning is not None
    assert result.edited_params is not None
    assert "query" in result.edited_params or "Huà" in str(result.edited_params)


@pytest.mark.asyncio
async def test_classify_edit_plutot(classifier, sample_action_context):
    """Test classification of 'plutôt X' as EDIT."""
    result = await classifier.classify(
        user_response="plutôt Jean", action_context=sample_action_context
    )

    assert result.decision == "EDIT"
    assert result.confidence >= 0.7
    assert result.edited_params is not None


@pytest.mark.asyncio
async def test_classify_edit_change(classifier, sample_action_context):
    """Test classification of 'change X en Y' as EDIT."""
    result = await classifier.classify(
        user_response="change jean en Jean Dupont", action_context=sample_action_context
    )

    assert result.decision == "EDIT"
    assert result.confidence >= 0.7
    assert result.edited_params is not None


@pytest.mark.asyncio
async def test_classify_edit_corrige(classifier, sample_action_context):
    """Test classification of 'corrige...' as EDIT."""
    result = await classifier.classify(
        user_response="corrige ça, c'est Huà pas jean", action_context=sample_action_context
    )

    assert result.decision == "EDIT"
    assert result.confidence >= 0.7
    assert result.edited_params is not None


# ============================================================================
# AMBIGUOUS Classification Tests
# ============================================================================


@pytest.mark.asyncio
async def test_classify_ambiguous_peut_etre(classifier, sample_action_context):
    """Test classification of 'peut-être' as AMBIGUOUS."""
    result = await classifier.classify(
        user_response="peut-être", action_context=sample_action_context
    )

    assert result.decision == "AMBIGUOUS"
    assert result.confidence < 0.7  # Low confidence for ambiguous
    assert result.reasoning is not None
    assert result.clarification_question is not None


@pytest.mark.asyncio
async def test_classify_ambiguous_je_sais_pas(classifier, sample_action_context):
    """Test classification of 'je sais pas' as AMBIGUOUS."""
    result = await classifier.classify(
        user_response="je sais pas", action_context=sample_action_context
    )

    assert result.decision == "AMBIGUOUS"
    assert result.confidence < 0.7
    assert result.clarification_question is not None


@pytest.mark.asyncio
async def test_classify_ambiguous_hmm(classifier, sample_action_context):
    """Test classification of 'hmm' as AMBIGUOUS."""
    result = await classifier.classify(user_response="hmm", action_context=sample_action_context)

    assert result.decision == "AMBIGUOUS"
    assert result.confidence < 0.7
    assert result.clarification_question is not None


@pytest.mark.asyncio
async def test_classify_ambiguous_empty(classifier, sample_action_context):
    """Test classification of empty/dots as AMBIGUOUS."""
    result = await classifier.classify(user_response="...", action_context=sample_action_context)

    assert result.decision == "AMBIGUOUS"
    assert result.confidence < 0.7
    assert result.clarification_question is not None


# ============================================================================
# Edge Cases & Variations
# ============================================================================


@pytest.mark.asyncio
async def test_classify_typo_tolerance(classifier, sample_action_context):
    """Test classification tolerates typos."""
    result = await classifier.classify(
        user_response="oui bine sur",
        action_context=sample_action_context,  # Typo: bine -> bien
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.6  # Still confident despite typo


@pytest.mark.asyncio
async def test_classify_familier(classifier, sample_action_context):
    """Test classification with familiar language."""
    result = await classifier.classify(
        user_response="ouais vas-y", action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.7


@pytest.mark.asyncio
async def test_classify_multi_word_approve(classifier, sample_action_context):
    """Test classification with multi-word approval."""
    result = await classifier.classify(
        user_response="oui c'est bon", action_context=sample_action_context
    )

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.7


@pytest.mark.asyncio
async def test_classify_context_aware(classifier):
    """Test classification is context-aware (delete action)."""
    delete_context = [
        {
            "tool_name": "delete_contact",
            "tool_args": {"contact_id": "123"},
            "tool_description": "Supprime un contact",
        }
    ]

    result = await classifier.classify(user_response="oui", action_context=delete_context)

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.7


@pytest.mark.asyncio
async def test_classify_multiple_actions(classifier):
    """Test classification with multiple actions (future multi-HITL)."""
    multi_context = [
        {
            "tool_name": "search_contacts_tool",
            "tool_args": {"query": "jean"},
        },
        {
            "tool_name": "send_email",
            "tool_args": {"to": "test@example.com"},
        },
    ]

    result = await classifier.classify(user_response="oui pour tout", action_context=multi_context)

    assert result.decision == "APPROVE"
    assert result.confidence >= 0.6


# ============================================================================
# Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_classify_with_empty_context(classifier):
    """Test classification handles empty context gracefully."""
    result = await classifier.classify(user_response="oui", action_context=[])

    # Should still classify (context helps but isn't required)
    assert result.decision in ["APPROVE", "REJECT", "EDIT", "AMBIGUOUS"]
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_format_action_context_edge_cases(classifier):
    """Test _format_action_context with various edge cases."""
    # Empty context
    assert classifier._format_action_context([]) == "une action"

    # Single search action
    result = classifier._format_action_context(
        [{"tool_name": "search_tool", "tool_args": {"query": "test"}}]
    )
    assert "recherche" in result.lower()

    # Single delete action
    result = classifier._format_action_context([{"tool_name": "delete_contact", "tool_args": {}}])
    assert "suppression" in result.lower()

    # Multiple actions
    result = classifier._format_action_context([{}, {}, {}])
    assert "3 actions" in result


# ============================================================================
# Integration Test (Full Flow)
# ============================================================================


@pytest.mark.asyncio
async def test_full_conversation_flow(classifier, sample_action_context):
    """Test full HITL conversation flow: ambiguous → clarification → approve."""
    # Step 1: User gives ambiguous response
    result1 = await classifier.classify(
        user_response="peut-être", action_context=sample_action_context
    )

    assert result1.decision == "AMBIGUOUS"
    assert result1.clarification_question is not None

    # Step 2: User clarifies with approval
    result2 = await classifier.classify(
        user_response="oui vas-y", action_context=sample_action_context
    )

    assert result2.decision == "APPROVE"
    assert result2.confidence >= 0.7
