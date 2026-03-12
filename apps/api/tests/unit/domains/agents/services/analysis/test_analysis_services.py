"""
Unit tests for analysis services.

Tests for GoalInferrer, RoutingDecider, and MemoryResolver services.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.analysis.query_intelligence import UserGoal
from src.domains.agents.services.analysis.goal_inferrer import (
    GoalInferrer,
    get_goal_inferrer,
    reset_goal_inferrer,
)
from src.domains.agents.services.analysis.memory_resolver import (
    MemoryResolver,
    get_memory_resolver,
    reset_memory_resolver,
)
from src.domains.agents.services.analysis.routing_decider import (
    RoutingDecider,
    get_routing_decider,
    reset_routing_decider,
)

# =============================================================================
# GoalInferrer Tests
# =============================================================================


class TestGoalInferrer:
    """Tests for GoalInferrer class."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_goal_inferrer()

    def test_pattern_matching_search_contacts(self):
        """Test goal inference for search contacts."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="find john's contact",
            intent="search",
            domains=["contacts"],
            messages=[],
        )
        assert goal == UserGoal.COMMUNICATE
        assert "Contact search" in reasoning

    def test_pattern_matching_send_emails(self):
        """Test goal inference for sending emails."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="send an email to john",
            intent="send",
            domains=["emails"],
            messages=[],
        )
        assert goal == UserGoal.COMMUNICATE
        assert "Send email" in reasoning

    def test_pattern_matching_search_events(self):
        """Test goal inference for searching events."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="find meetings tomorrow",
            intent="search",
            domains=["events"],
            messages=[],
        )
        assert goal == UserGoal.PLAN_ORGANIZE

    def test_pattern_matching_create_events(self):
        """Test goal inference for creating events."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="create a meeting",
            intent="create",
            domains=["events"],
            messages=[],
        )
        assert goal == UserGoal.PLAN_ORGANIZE

    def test_pattern_matching_search_drive(self):
        """Test goal inference for searching drive."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="find that document",
            intent="search",
            domains=["drive"],
            messages=[],
        )
        assert goal == UserGoal.FIND_INFORMATION

    def test_pattern_matching_search_perplexity(self):
        """Test goal inference for web search."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="what is quantum computing",
            intent="search",
            domains=["perplexity"],
            messages=[],
        )
        assert goal == UserGoal.UNDERSTAND

    def test_pattern_matching_search_wikipedia(self):
        """Test goal inference for Wikipedia search."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="tell me about Napoleon",
            intent="search",
            domains=["wikipedia"],
            messages=[],
        )
        assert goal == UserGoal.UNDERSTAND

    def test_pattern_matching_create_tasks(self):
        """Test goal inference for creating tasks."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="create a task to call John",
            intent="create",
            domains=["tasks"],
            messages=[],
        )
        assert goal == UserGoal.TAKE_ACTION

    def test_default_goal_for_search(self):
        """Test default goal for search intent without domain match."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="search something",
            intent="search",
            domains=["unknown_domain"],
            messages=[],
        )
        assert goal == UserGoal.FIND_INFORMATION
        assert "Information search" in reasoning

    def test_default_goal_for_create(self):
        """Test default goal for create intent."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="create something",
            intent="create",
            domains=["unknown_domain"],
            messages=[],
        )
        assert goal == UserGoal.TAKE_ACTION

    def test_default_goal_for_update(self):
        """Test default goal for update intent."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="update something",
            intent="update",
            domains=[],
            messages=[],
        )
        assert goal == UserGoal.TAKE_ACTION

    def test_default_goal_for_delete(self):
        """Test default goal for delete intent."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="delete something",
            intent="delete",
            domains=[],
            messages=[],
        )
        assert goal == UserGoal.TAKE_ACTION

    def test_default_goal_for_chat(self):
        """Test default goal for chat intent."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="hello how are you",
            intent="chat",
            domains=[],
            messages=[],
        )
        assert goal == UserGoal.UNDERSTAND

    def test_default_goal_for_list(self):
        """Test default goal for list intent."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="list all items",
            intent="list",
            domains=[],
            messages=[],
        )
        assert goal == UserGoal.EXPLORE

    def test_context_inference_contact_to_send(self):
        """Test context-based inference from contact search to send."""
        inferrer = GoalInferrer()
        messages = [
            HumanMessage(content="find john's contact"),
            AIMessage(content="Found John Doe's contact"),
            HumanMessage(content="send him an email"),
        ]
        goal, reasoning = inferrer.infer(
            query="send him an email",
            intent="send",
            domains=[],
            messages=messages,
        )
        assert goal == UserGoal.COMMUNICATE
        assert "Following contact search" in reasoning

    def test_context_inference_email_to_search(self):
        """Test context-based inference from email to search."""
        inferrer = GoalInferrer()
        messages = [
            HumanMessage(content="find that email from yesterday"),
            AIMessage(content="Found email about project"),
            HumanMessage(content="search for more details"),
        ]
        goal, reasoning = inferrer.infer(
            query="search for more details",
            intent="search",
            domains=[],
            messages=messages,
        )
        assert goal == UserGoal.UNDERSTAND
        assert "Following email search" in reasoning

    def test_fallback_for_unknown_intent(self):
        """Test fallback for unknown intent."""
        inferrer = GoalInferrer()
        goal, reasoning = inferrer.infer(
            query="do something weird",
            intent="unknown_intent",
            domains=[],
            messages=[],
        )
        assert goal == UserGoal.FIND_INFORMATION
        assert reasoning == "Default"


class TestGoalInferrerSingleton:
    """Tests for GoalInferrer singleton functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_goal_inferrer()

    def test_get_goal_inferrer_returns_same_instance(self):
        """Test that get_goal_inferrer returns singleton."""
        inferrer1 = get_goal_inferrer()
        inferrer2 = get_goal_inferrer()
        assert inferrer1 is inferrer2

    def test_reset_goal_inferrer_creates_new_instance(self):
        """Test that reset creates new instance."""
        inferrer1 = get_goal_inferrer()
        reset_goal_inferrer()
        inferrer2 = get_goal_inferrer()
        assert inferrer1 is not inferrer2


# =============================================================================
# RoutingDecider Tests
# =============================================================================


class TestRoutingDecider:
    """Tests for RoutingDecider class."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_routing_decider()

    def test_chat_intent_without_domains_routes_to_response(self):
        """Test that chat intent without domains routes to response."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="chat",
            intent_confidence=0.8,
            domains=[],
            semantic_score=0.3,
        )
        assert route == "response"
        assert bypass is False

    def test_chat_with_low_semantic_routes_to_response(self):
        """Test that chat with low semantic score routes to response."""
        decider = RoutingDecider(chat_semantic_threshold=0.4)
        route, confidence, bypass = decider.decide(
            intent="chat",
            intent_confidence=0.7,
            domains=["contacts"],
            semantic_score=0.3,  # Below threshold
        )
        assert route == "response"

    def test_search_intent_with_domains_routes_to_planner(self):
        """Test that search intent with domains routes to planner."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="search",
            intent_confidence=0.8,
            domains=["contacts"],
            semantic_score=0.5,
        )
        assert route == "planner"
        assert bypass is True

    def test_create_intent_with_domains_routes_to_planner(self):
        """Test that create intent with domains routes to planner."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="create",
            intent_confidence=0.9,
            domains=["events"],
            semantic_score=0.6,
        )
        assert route == "planner"
        assert bypass is True

    def test_update_intent_with_domains_routes_to_planner(self):
        """Test that update intent with domains routes to planner."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="update",
            intent_confidence=0.8,
            domains=["contacts"],
            semantic_score=0.5,
        )
        assert route == "planner"
        assert bypass is True

    def test_delete_intent_with_domains_routes_to_planner(self):
        """Test that delete intent with domains routes to planner."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="delete",
            intent_confidence=0.9,
            domains=["events"],
            semantic_score=0.7,
        )
        assert route == "planner"
        assert bypass is True

    def test_send_intent_with_domains_routes_to_planner(self):
        """Test that send intent with domains routes to planner."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="send",
            intent_confidence=0.85,
            domains=["emails"],
            semantic_score=0.6,
        )
        assert route == "planner"
        assert bypass is True

    def test_high_semantic_score_routes_to_planner(self):
        """Test that high semantic score routes to planner with bypass."""
        decider = RoutingDecider(high_semantic_threshold=0.7)
        route, confidence, bypass = decider.decide(
            intent="unknown",
            intent_confidence=0.5,
            domains=["contacts"],
            semantic_score=0.8,  # High score
        )
        assert route == "planner"
        assert bypass is True
        assert confidence == 0.8  # Uses semantic score

    def test_no_domains_fallback_to_response(self):
        """Test that no domains falls back to response."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="unknown",
            intent_confidence=0.5,
            domains=[],
            semantic_score=0.4,
        )
        assert route == "response"
        assert bypass is False

    def test_default_routes_to_planner_with_domains(self):
        """Test that unknown intent with domains defaults to planner."""
        decider = RoutingDecider()
        route, confidence, bypass = decider.decide(
            intent="custom_intent",
            intent_confidence=0.5,
            domains=["contacts"],
            semantic_score=0.5,  # Below high threshold
        )
        assert route == "planner"
        assert bypass is False

    def test_min_confidence_enforced_for_data_intents(self):
        """Test that min_confidence is enforced for data intents."""
        decider = RoutingDecider(min_confidence=0.5)
        route, confidence, bypass = decider.decide(
            intent="search",
            intent_confidence=0.2,  # Low confidence
            domains=["contacts"],
            semantic_score=0.3,
        )
        assert route == "planner"
        assert confidence >= 0.5  # Min confidence enforced

    def test_custom_thresholds(self):
        """Test custom threshold configuration."""
        decider = RoutingDecider(
            chat_semantic_threshold=0.5,
            high_semantic_threshold=0.8,
            min_confidence=0.4,
        )
        assert decider.chat_semantic_threshold == 0.5
        assert decider.high_semantic_threshold == 0.8
        assert decider.min_confidence == 0.4


class TestRoutingDeciderSingleton:
    """Tests for RoutingDecider singleton functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_routing_decider()

    def test_get_routing_decider_returns_same_instance(self):
        """Test that get_routing_decider returns singleton."""
        decider1 = get_routing_decider()
        decider2 = get_routing_decider()
        assert decider1 is decider2

    def test_reset_routing_decider_creates_new_instance(self):
        """Test that reset creates new instance."""
        decider1 = get_routing_decider()
        reset_routing_decider()
        decider2 = get_routing_decider()
        assert decider1 is not decider2

    def test_get_routing_decider_with_custom_thresholds(self):
        """Test singleton creation with custom thresholds."""
        decider = get_routing_decider(
            chat_semantic_threshold=0.6,
            high_semantic_threshold=0.9,
        )
        assert decider.chat_semantic_threshold == 0.6
        assert decider.high_semantic_threshold == 0.9


# =============================================================================
# MemoryResolver Tests
# =============================================================================


class TestMemoryResolver:
    """Tests for MemoryResolver class."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_memory_resolver()

    @pytest.mark.asyncio
    async def test_retrieve_and_resolve_returns_tuple(self):
        """Test that retrieve_and_resolve returns tuple of facts and references."""
        resolver = MemoryResolver()
        config = MagicMock()

        with patch.object(
            resolver, "_retrieve_memory_facts", return_value=["fact1", "fact2"]
        ) as mock_retrieve:
            with patch.object(
                resolver, "_resolve_memory_references", return_value=None
            ) as mock_resolve:
                facts, refs = await resolver.retrieve_and_resolve(
                    query="test query",
                    user_id="user123",
                    config=config,
                )

                mock_retrieve.assert_called_once()
                mock_resolve.assert_called_once()
                assert facts == ["fact1", "fact2"]

    @pytest.mark.asyncio
    async def test_retrieve_and_resolve_no_facts_skips_resolution(self):
        """Test that resolution is skipped when no facts found."""
        resolver = MemoryResolver()
        config = MagicMock()

        with patch.object(resolver, "_retrieve_memory_facts", return_value=None) as mock_retrieve:
            with patch.object(resolver, "_resolve_memory_references") as mock_resolve:
                facts, refs = await resolver.retrieve_and_resolve(
                    query="test query",
                    user_id="user123",
                    config=config,
                )

                mock_retrieve.assert_called_once()
                mock_resolve.assert_not_called()
                assert facts is None
                assert refs is None

    @pytest.mark.asyncio
    async def test_retrieve_memory_facts_empty_query_returns_none(self):
        """Test that empty query returns None for memory facts."""
        resolver = MemoryResolver()
        config = MagicMock()

        result = await resolver._retrieve_memory_facts(
            query="",
            user_id="user123",
            config=config,
        )
        assert result is None

    @pytest.mark.asyncio
    @patch("src.domains.agents.context.store.get_tool_context_store", new_callable=AsyncMock)
    async def test_retrieve_memory_facts_no_store_returns_none(self, mock_get_store):
        """Test that no store returns None for memory facts."""
        mock_get_store.return_value = None
        resolver = MemoryResolver()
        config = MagicMock()

        result = await resolver._retrieve_memory_facts(
            query="test query",
            user_id="user123",
            config=config,
        )
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "src.domains.agents.middleware.memory_injection.get_memory_facts_for_query",
        new_callable=AsyncMock,
    )
    @patch("src.domains.agents.context.store.get_tool_context_store", new_callable=AsyncMock)
    async def test_retrieve_memory_facts_returns_facts(self, mock_get_store, mock_get_facts):
        """Test successful memory facts retrieval."""
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_get_facts.return_value = ["fact1", "fact2"]

        resolver = MemoryResolver()
        config = MagicMock()

        result = await resolver._retrieve_memory_facts(
            query="test query",
            user_id="user123",
            config=config,
        )
        assert result == ["fact1", "fact2"]

    @pytest.mark.asyncio
    @patch("src.domains.agents.context.store.get_tool_context_store", new_callable=AsyncMock)
    async def test_retrieve_memory_facts_handles_exception(self, mock_get_store):
        """Test that exceptions are handled gracefully."""
        mock_get_store.side_effect = Exception("Store error")
        resolver = MemoryResolver()
        config = MagicMock()

        result = await resolver._retrieve_memory_facts(
            query="test query",
            user_id="user123",
            config=config,
        )
        assert result is None

    @pytest.mark.asyncio
    @patch(
        "src.domains.agents.services.memory_reference_resolution_service.get_memory_reference_resolution_service"
    )
    async def test_resolve_memory_references_calls_service(self, mock_get_service):
        """Test that reference resolution calls the service."""
        mock_service = MagicMock()
        mock_service.resolve_pre_planner = AsyncMock(return_value=MagicMock())
        mock_get_service.return_value = mock_service

        resolver = MemoryResolver()
        config = MagicMock()

        await resolver._resolve_memory_references(
            query="find my wife",
            memory_facts=["Wife: Jane Smith"],
            config=config,
        )

        mock_service.resolve_pre_planner.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        "src.domains.agents.services.memory_reference_resolution_service.get_memory_reference_resolution_service"
    )
    async def test_resolve_memory_references_handles_exception(self, mock_get_service):
        """Test that resolution exceptions are handled gracefully."""
        mock_get_service.side_effect = Exception("Service error")
        resolver = MemoryResolver()
        config = MagicMock()

        result = await resolver._resolve_memory_references(
            query="find my wife",
            memory_facts=["Wife: Jane Smith"],
            config=config,
        )
        assert result is None


class TestMemoryResolverSingleton:
    """Tests for MemoryResolver singleton functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_memory_resolver()

    def test_get_memory_resolver_returns_same_instance(self):
        """Test that get_memory_resolver returns singleton."""
        resolver1 = get_memory_resolver()
        resolver2 = get_memory_resolver()
        assert resolver1 is resolver2

    def test_reset_memory_resolver_creates_new_instance(self):
        """Test that reset creates new instance."""
        resolver1 = get_memory_resolver()
        reset_memory_resolver()
        resolver2 = get_memory_resolver()
        assert resolver1 is not resolver2
