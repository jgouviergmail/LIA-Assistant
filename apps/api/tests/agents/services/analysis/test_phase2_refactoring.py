"""
Verification tests for Phase 2.1 - QueryAnalyzerService Refactoring.

These tests verify that the 3 specialized services are correctly extracted
and function independently.
"""

from src.domains.agents.analysis.query_intelligence import UserGoal
from src.domains.agents.services.analysis import (
    get_goal_inferrer,
    get_memory_resolver,
    get_routing_decider,
)


class TestMemoryResolver:
    """Tests for MemoryResolver."""

    def test_memory_resolver_initialization(self):
        """Test that MemoryResolver can be instantiated."""
        resolver = get_memory_resolver()
        assert resolver is not None

    def test_memory_resolver_singleton(self):
        """Test that get_memory_resolver returns the same instance (singleton)."""
        resolver1 = get_memory_resolver()
        resolver2 = get_memory_resolver()
        assert resolver1 is resolver2


class TestGoalInferrer:
    """Tests for GoalInferrer."""

    def test_goal_inferrer_initialization(self):
        """Test that GoalInferrer can be instantiated."""
        inferrer = get_goal_inferrer()
        assert inferrer is not None

    def test_goal_inferrer_singleton(self):
        """Test that get_goal_inferrer returns the same instance (singleton)."""
        inferrer1 = get_goal_inferrer()
        inferrer2 = get_goal_inferrer()
        assert inferrer1 is inferrer2

    def test_infer_search_contacts_goal(self):
        """Test inference for 'search contacts' -> COMMUNICATE."""
        inferrer = get_goal_inferrer()
        goal, reasoning = inferrer.infer(
            query="Find John's contact",
            intent="search",
            domains=["contacts"],
            messages=[],
        )
        assert goal == UserGoal.COMMUNICATE
        assert "Contact search" in reasoning

    def test_infer_search_drive_goal(self):
        """Test inference for 'search drive' -> FIND_INFORMATION."""
        inferrer = get_goal_inferrer()
        goal, reasoning = inferrer.infer(
            query="Find my documents",
            intent="search",
            domains=["drive"],
            messages=[],
        )
        assert goal == UserGoal.FIND_INFORMATION
        assert "File search" in reasoning

    def test_infer_create_task_goal(self):
        """Test inference for 'create task' -> TAKE_ACTION."""
        inferrer = get_goal_inferrer()
        goal, reasoning = inferrer.infer(
            query="Create a reminder",
            intent="create",
            domains=["tasks"],
            messages=[],
        )
        assert goal == UserGoal.TAKE_ACTION
        assert "Create task" in reasoning

    def test_infer_default_search_goal(self):
        """Test default inference for 'search' without pattern -> FIND_INFORMATION."""
        inferrer = get_goal_inferrer()
        goal, reasoning = inferrer.infer(
            query="What is the weather?",
            intent="search",
            domains=["weather"],
            messages=[],
        )
        assert goal == UserGoal.FIND_INFORMATION
        assert "Information search" in reasoning


class TestRoutingDecider:
    """Tests for RoutingDecider."""

    def test_routing_decider_initialization(self):
        """Test that RoutingDecider can be instantiated."""
        decider = get_routing_decider()
        assert decider is not None

    def test_routing_decider_singleton(self):
        """Test that get_routing_decider returns the same instance (singleton)."""
        decider1 = get_routing_decider()
        decider2 = get_routing_decider()
        assert decider1 is decider2

    def test_decide_chat_without_domains(self):
        """Test routing for chat intent without domains -> response."""
        decider = get_routing_decider()
        route, confidence, bypass = decider.decide(
            intent="chat",
            intent_confidence=0.8,
            domains=[],
            semantic_score=0.3,
        )
        assert route == "response"
        assert confidence > 0
        assert bypass is False  # No bypass for chat without domains

    def test_decide_search_with_domains(self):
        """Test routing for search intent with domains -> planner."""
        decider = get_routing_decider()
        route, confidence, bypass = decider.decide(
            intent="search",
            intent_confidence=0.9,
            domains=["contacts"],
            semantic_score=0.5,
        )
        assert route == "planner"
        assert confidence > 0
        assert bypass is True  # Bypass LLM due to clear rule

    def test_decide_high_semantic_score(self):
        """Test routing for high semantic score -> planner (requires domains)."""
        decider = get_routing_decider()
        route, confidence, bypass = decider.decide(
            intent="chat",
            intent_confidence=0.5,
            domains=["weather"],  # Domains requis pour Rule 3
            semantic_score=0.75,  # High semantic score
        )
        assert route == "planner"
        assert bypass is True  # Bypass LLM due to clear rule (high semantic)


class TestQueryAnalyzerServiceIntegration:
    """Integration tests to verify that QueryAnalyzerService uses the composed services."""

    def test_query_analyzer_service_initialization(self):
        """Test that QueryAnalyzerService can be instantiated with the composed services."""
        from src.domains.agents.services.query_analyzer_service import (
            get_query_analyzer_service,
        )

        analyzer = get_query_analyzer_service()
        assert analyzer is not None
        assert analyzer.memory_resolver is not None
        assert analyzer.context_resolver is not None
        assert analyzer.goal_inferrer is not None
        assert analyzer.routing_decider is not None
        assert analyzer.thresholds is not None

    def test_query_analyzer_service_singleton(self):
        """Test that get_query_analyzer_service returns the same instance (singleton)."""
        from src.domains.agents.services.query_analyzer_service import (
            get_query_analyzer_service,
        )

        analyzer1 = get_query_analyzer_service()
        analyzer2 = get_query_analyzer_service()
        assert analyzer1 is analyzer2
