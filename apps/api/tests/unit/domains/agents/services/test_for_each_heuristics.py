"""
Unit tests for FOR_EACH heuristics post-processing (CORRECTION 4).

Tests coverage:
- Explicit pattern detection ("for each", "to all", "delete all")
- Plural noun + mutation intent detection
- Quantifier + mutation intent detection
- Already detected by LLM passes through unchanged
- Non-matching queries return unchanged result
- Collection key inference from domains

Target: _apply_for_each_heuristics in
    domains/agents/services/query_analyzer_service.py

Note: All queries are ENGLISH because SemanticPivotService translates
      before analysis. French patterns would never match.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.domains.agents.services.query_analyzer_service import (
    _apply_for_each_heuristics,
)

# =============================================================================
# Fixtures
# =============================================================================


@dataclass
class MockAnalysisResult:
    """Minimal QueryAnalysisResult mock for testing heuristics."""

    intent: str = "action"
    primary_domain: str | None = "contact"
    secondary_domains: list[str] = field(default_factory=list)
    confidence: float = 0.85
    english_query: str = ""
    resolved_references: list[dict] = field(default_factory=list)
    reasoning: str = "test"
    is_mutation_intent: bool = False
    has_cardinality_risk: bool = False
    for_each_detected: bool = False
    for_each_collection_key: str | None = None
    cardinality_magnitude: int | None = None
    constraint_hints: dict[str, bool] = field(default_factory=dict)
    encyclopedia_keywords: list[str] = field(default_factory=list)
    is_news_query: bool = False
    raw_output: dict = field(default_factory=dict)

    @property
    def domains(self) -> list[str]:
        if self.primary_domain:
            return [self.primary_domain] + self.secondary_domains
        return self.secondary_domains

    @property
    def is_action(self) -> bool:
        return self.intent == "action"


# =============================================================================
# Tests: Explicit Patterns (EN only)
# =============================================================================


class TestExplicitPatterns:
    """Heuristic 1: Explicit iteration patterns in English."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("send an email to each of my contacts", True),
            ("delete all my tasks", True),
            ("send to all my contacts", True),
            ("remove all events from calendar", True),
            ("to everyone in my contact list", True),
            ("each one of them should get a message", True),
            ("all of them need to be updated", True),
            ("for each contact find their email", True),
        ],
    )
    def test_explicit_patterns_detected(self, query: str, expected: bool) -> None:
        """Explicit FOR_EACH patterns should be detected."""
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is expected

    @pytest.mark.parametrize(
        "query",
        [
            "search john doe",
            "weather tomorrow",
            "what time is it",
            "find a restaurant nearby",
        ],
    )
    def test_non_matching_queries_unchanged(self, query: str) -> None:
        """Non-matching queries should not trigger FOR_EACH."""
        result = MockAnalysisResult(english_query=query)
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is False


# =============================================================================
# Tests: Plural + Mutation
# =============================================================================


class TestPluralMutation:
    """Heuristic 2: Plural collection noun + mutation intent."""

    def test_plural_contacts_with_mutation(self) -> None:
        """'contacts' + mutation intent should trigger FOR_EACH."""
        query = "send a message to my contacts"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="contact",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is True

    def test_plural_emails_with_mutation(self) -> None:
        """'emails' + mutation intent should trigger FOR_EACH."""
        query = "delete old emails from inbox"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="email",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is True

    def test_plural_without_mutation_no_trigger(self) -> None:
        """Plural noun WITHOUT mutation should NOT trigger FOR_EACH."""
        query = "show me my contacts"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=False,
            primary_domain="contact",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is False

    def test_mutation_without_plural_no_trigger(self) -> None:
        """Mutation WITHOUT plural noun should NOT trigger FOR_EACH."""
        query = "delete the appointment"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="event",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is False


# =============================================================================
# Tests: Quantifier + Mutation
# =============================================================================


class TestQuantifierMutation:
    """Heuristic 3: Quantifier pattern + mutation intent."""

    def test_quantifier_first_5_with_mutation(self) -> None:
        """'the first 5' + mutation intent should trigger FOR_EACH."""
        query = "delete the first 5 emails"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="email",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        # Note: "emails" is a plural hint AND mutation → triggers via heuristic 2
        assert enhanced.for_each_detected is True

    def test_quantifier_last_3_with_mutation(self) -> None:
        """'my last 3' + mutation should trigger FOR_EACH."""
        query = "cancel my last 3 events"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="event",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is True

    @pytest.mark.parametrize(
        "query",
        [
            "delete the first task",
            "remove the last event",
            "cancel my first appointment",
        ],
    )
    def test_ordinal_without_digit_no_trigger(self, query: str) -> None:
        """Ordinal selection ('the first task') must NOT trigger FOR_EACH."""
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="task",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is False


# =============================================================================
# Tests: LLM already detected
# =============================================================================


class TestLLMAlreadyDetected:
    """If LLM already detected FOR_EACH, heuristics should pass through."""

    def test_llm_detection_preserved(self) -> None:
        """LLM-detected for_each should be returned unchanged."""
        result = MockAnalysisResult(
            english_query="search john",
            for_each_detected=True,
            for_each_collection_key="contacts",
        )
        enhanced = _apply_for_each_heuristics(result, "search john", result.domains)
        assert enhanced.for_each_detected is True
        assert enhanced.for_each_collection_key == "contacts"


# =============================================================================
# Tests: Collection key inference
# =============================================================================


class TestCollectionKeyInference:
    """Collection key should be inferred from domains when not already set."""

    def test_contact_domain_infers_contacts(self) -> None:
        """Contact domain should infer 'contacts' collection key."""
        query = "send to all my friends"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="contact",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is True
        assert enhanced.for_each_collection_key == "contacts"

    def test_email_domain_infers_emails(self) -> None:
        """Email domain should infer 'emails' collection key."""
        query = "delete all my emails"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="email",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is True
        assert enhanced.for_each_collection_key == "emails"

    def test_event_domain_infers_events(self) -> None:
        """Event domain should infer 'events' collection key."""
        query = "cancel all my events"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="event",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is True
        assert enhanced.for_each_collection_key == "events"

    def test_has_cardinality_risk_set(self) -> None:
        """Enhanced result should set has_cardinality_risk=True."""
        query = "send to all my contacts"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="contact",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.has_cardinality_risk is True

    def test_for_each_detected_implies_iteration(self) -> None:
        """When heuristics activate for_each, the result should have for_each_detected=True."""
        query = "send to all my contacts"
        result = MockAnalysisResult(
            english_query=query,
            is_mutation_intent=True,
            primary_domain="contact",
        )
        enhanced = _apply_for_each_heuristics(result, query.lower(), result.domains)
        assert enhanced.for_each_detected is True
        assert enhanced.has_cardinality_risk is True
