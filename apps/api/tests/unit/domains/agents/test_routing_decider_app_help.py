"""Tests for RoutingDecider Rule 0 — is_app_help_query override."""

from __future__ import annotations

import pytest

from src.domains.agents.services.analysis.routing_decider import RoutingDecider

# ============================================================================
# TestAppHelpRouting
# ============================================================================


@pytest.mark.unit
class TestAppHelpRouting:
    """Rule 0: is_app_help_query=True should always route to response."""

    def test_app_help_routes_to_response(self) -> None:
        """App help query should always go to response, regardless of intent/domains."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="search",
            intent_confidence=0.95,
            domains=["event"],
            semantic_score=0.9,
            is_app_help_query=True,
        )

        assert route == "response"
        assert bypass is False

    def test_app_help_overrides_data_intent(self) -> None:
        """Even with data intent + domains, app help should go to response."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="create",
            intent_confidence=0.99,
            domains=["event", "contact"],
            semantic_score=0.95,
            is_app_help_query=True,
        )

        assert route == "response"

    def test_non_app_help_follows_normal_rules(self) -> None:
        """Without app help flag, normal routing rules apply."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="search",
            intent_confidence=0.9,
            domains=["email"],
            semantic_score=0.8,
            is_app_help_query=False,
        )

        assert route == "planner"

    def test_app_help_default_is_false(self) -> None:
        """Default value of is_app_help_query should be False."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="search",
            intent_confidence=0.9,
            domains=["email"],
            semantic_score=0.8,
        )

        assert route == "planner"

    def test_app_help_with_chat_intent(self) -> None:
        """App help with chat intent should still route to response."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="chat",
            intent_confidence=0.8,
            domains=[],
            semantic_score=0.3,
            is_app_help_query=True,
        )

        assert route == "response"

    def test_app_help_preserves_confidence(self) -> None:
        """App help routing should pass through the intent confidence."""
        decider = RoutingDecider()
        _, confidence, _ = decider.decide(
            intent="search",
            intent_confidence=0.75,
            domains=["event"],
            semantic_score=0.9,
            is_app_help_query=True,
        )

        assert confidence == 0.75
