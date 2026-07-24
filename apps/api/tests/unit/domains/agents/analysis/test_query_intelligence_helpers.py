"""Unit tests for query_intelligence_helpers (serialization round-trip).

Regression coverage for the 2026-07 codebase audit (wave 1):
- ``reconstruct_query_intelligence`` omitted ``semantic_filter_terms`` even
  though ``to_serializable_dict`` serializes it, so the field silently reset
  to ``()`` after every LangGraph checkpoint resume (HITL interrupts).
- The generic round-trip test compares the FULL serialized dict before and
  after reconstruction, so any future field added to ``to_serializable_dict``
  without its ``reconstruct_query_intelligence`` counterpart fails loudly
  (CLAUDE.md systemic rule on serialization pairs).
"""

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.analysis.query_intelligence_helpers import (
    reconstruct_query_intelligence,
)


def _make_full_query_intelligence() -> QueryIntelligence:
    """Build a QueryIntelligence with a non-default value for every serialized field.

    ``resolved_context`` stays ``None`` on purpose: it is serialized in the dict
    but reconstructed from its own state key (``STATE_KEY_RESOLVED_CONTEXT``),
    as documented in ``get_query_intelligence_from_state``.
    """
    return QueryIntelligence(
        original_query="trouve mes emails médicaux urgents",
        english_query="find my urgent medical emails",
        english_enriched_query="find urgent medical emails for jean dupond",
        immediate_intent="search",
        immediate_confidence=0.91,
        user_goal=UserGoal.TAKE_ACTION,
        goal_reasoning="user wants to locate then act on emails",
        implicit_intents=["may forward them"],
        domains=["email", "contact"],
        primary_domain="email",
        domain_scores={"email": 0.88, "contact": 0.41},
        domain_calibrated_scores={"email": 0.72, "contact": 0.28},
        turn_type="REFERENCE_ACTION",
        resolved_context=None,
        source_turn_id=7,
        source_domain="email",
        resolved_references={"my wife": "jean dupond"},
        anticipated_needs=["may want reminder"],
        fallback_strategies=["broaden search"],
        suggested_enrichments=["recent emails with contact"],
        route_to="response",  # non-default: the default is "planner"
        bypass_llm=True,
        confidence=0.87,
        user_language="en",  # non-default: settings.default_language is "fr"
        reasoning_trace=["step 1", "step 2"],
        intelligent_mechanisms={"semantic_pivot": True},
        is_mutation_intent=True,
        has_cardinality_risk=True,
        constraint_hints={"has_quality": True},
        for_each_detected=True,
        for_each_collection_key="emails",
        cardinality_magnitude=999,
        cardinality_mode="all",
        encyclopedia_keywords=["cardiology"],
        is_news_query=True,
        is_app_help_query=True,
        detected_skill_name="email_triage",
        semantic_filter_terms=("medical", "urgent"),
        has_temporal_reference=True,
    )


@pytest.mark.unit
def test_round_trip_preserves_all_serialized_fields():
    """serialize -> reconstruct -> serialize must be the identity on the dict."""
    original = _make_full_query_intelligence()

    serialized = original.to_serializable_dict()
    reconstructed = reconstruct_query_intelligence(serialized)

    assert reconstructed.to_serializable_dict() == serialized


@pytest.mark.unit
def test_round_trip_preserves_semantic_filter_terms_as_tuple():
    """semantic_filter_terms survives the round-trip with its tuple type."""
    original = _make_full_query_intelligence()

    reconstructed = reconstruct_query_intelligence(original.to_serializable_dict())

    assert reconstructed.semantic_filter_terms == ("medical", "urgent")
    assert isinstance(reconstructed.semantic_filter_terms, tuple)


@pytest.mark.unit
def test_reconstruct_defaults_semantic_filter_terms_to_empty_tuple():
    """Legacy checkpoints without the key reconstruct to the dataclass default."""
    serialized = _make_full_query_intelligence().to_serializable_dict()
    serialized.pop("semantic_filter_terms")

    reconstructed = reconstruct_query_intelligence(serialized)

    assert reconstructed.semantic_filter_terms == ()


@pytest.mark.unit
def test_round_trip_preserves_has_temporal_reference():
    """has_temporal_reference survives serialize -> reconstruct."""
    original = _make_full_query_intelligence()

    reconstructed = reconstruct_query_intelligence(original.to_serializable_dict())

    assert reconstructed.has_temporal_reference is True


@pytest.mark.unit
def test_reconstruct_defaults_has_temporal_reference_to_false():
    """Legacy checkpoints without the key reconstruct to the dataclass default."""
    serialized = _make_full_query_intelligence().to_serializable_dict()
    serialized.pop("has_temporal_reference")

    reconstructed = reconstruct_query_intelligence(serialized)

    assert reconstructed.has_temporal_reference is False
