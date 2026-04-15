"""Tests for RoutingDecider Rule 1 — detected_skill_name override.

When the QueryAnalyzer has semantically identified a skill, the router must
always send the request to the planner regardless of the domains list — so
that `SkillBypassStrategy` (for deterministic skills) or the LLM planner
(for non-deterministic) can shape the plan from the skill.

This protects against the failure mode where the LLM stored the skill name
only in the `skill_name` field without projecting it onto the functional
domains, leaving ``domains=[]`` and routing erroneously to response.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.analysis.routing_decider import RoutingDecider


@pytest.mark.unit
class TestSkillRouting:
    """Rule 1: detected_skill_name set → always route to planner."""

    def test_skill_detected_with_empty_domains_routes_to_planner(self) -> None:
        """Detected skill + empty domains → planner (not the no-domains fallback)."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="search",
            intent_confidence=0.95,
            domains=[],
            semantic_score=0.95,
            detected_skill_name="briefing-quotidien",
        )
        assert route == "planner"

    def test_skill_detected_with_domains_routes_to_planner(self) -> None:
        """Detected skill + some domains → planner."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="search",
            intent_confidence=0.9,
            domains=["event", "weather"],
            semantic_score=0.8,
            detected_skill_name="briefing-quotidien",
        )
        assert route == "planner"

    def test_skill_detected_with_chat_intent_still_routes_to_planner(self) -> None:
        """A skill identification overrides a chat intent (skill pipeline wins)."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="chat",
            intent_confidence=0.8,
            domains=[],
            semantic_score=0.3,
            detected_skill_name="briefing-quotidien",
        )
        assert route == "planner"

    def test_skill_not_detected_with_empty_domains_still_falls_back(self) -> None:
        """Without skill detection + empty domains → response (Rule 5)."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="search",
            intent_confidence=0.9,
            domains=[],
            semantic_score=0.8,
            detected_skill_name=None,
        )
        assert route == "response"

    def test_app_help_overrides_skill_detection(self) -> None:
        """Rule 0 (app help) wins over Rule 1 (skill detection)."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="search",
            intent_confidence=0.9,
            domains=["event"],
            semantic_score=0.9,
            is_app_help_query=True,
            detected_skill_name="briefing-quotidien",
        )
        assert route == "response"

    def test_skill_detection_never_bypasses_llm(self) -> None:
        """Skill routing returns bypass_llm=False — SkillBypass decides internally."""
        decider = RoutingDecider()
        _, _, bypass = decider.decide(
            intent="search",
            intent_confidence=0.95,
            domains=[],
            semantic_score=0.95,
            detected_skill_name="briefing-quotidien",
        )
        assert bypass is False

    def test_skill_detection_confidence_uses_min_floor(self) -> None:
        """Very low intent confidence is floored to min_confidence for planner routing."""
        decider = RoutingDecider(min_confidence=0.3)
        _, confidence, _ = decider.decide(
            intent="search",
            intent_confidence=0.1,
            domains=[],
            semantic_score=0.1,
            detected_skill_name="briefing-quotidien",
        )
        assert confidence == pytest.approx(0.3)

    def test_default_detected_skill_name_is_none(self) -> None:
        """Omitting detected_skill_name keeps legacy behaviour (no skill override)."""
        decider = RoutingDecider()
        route, _, _ = decider.decide(
            intent="search",
            intent_confidence=0.9,
            domains=[],
            semantic_score=0.8,
        )
        assert route == "response"
