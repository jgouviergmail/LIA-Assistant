"""
Tests for v3 Architecture Components.

Architecture v3 - Intelligence, Autonomie, Pertinence.

These tests validate:
1. QueryIntelligence - User goal inference
2. SmartCatalogueService - Catalogue filtering with Panic Mode
3. SmartPlannerService - Template matching and escape hatch
4. AutonomousExecutor - Self-healing with safeguards
5. RelevanceEngine - Smart ranking with episodic memory
6. FeedbackLoopService - Pattern learning
7. ResponseFormatter - Warm formatting
"""

from unittest.mock import MagicMock

import pytest

from src.domains.agents.analysis.query_intelligence import (
    QueryIntelligence,
    SemanticFallback,
    ToolFilter,
    UserGoal,
)


class TestQueryIntelligence:
    """Test QueryIntelligence dataclass."""

    def test_create_basic_intelligence(self):
        """Test creating basic QueryIntelligence."""
        intelligence = QueryIntelligence(
            original_query="recherche les contacts jean",
            english_query="search contacts jean",
            immediate_intent="search",
            immediate_confidence=0.95,
            user_goal=UserGoal.COMMUNICATE,
            goal_reasoning="Contact search = probably to communicate",
            domains=["contacts"],
            primary_domain="contacts",
            domain_scores={"contacts": 0.95},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=True,
            confidence=0.95,
            reasoning_trace=["Intent: search", "Domain: contacts"],
        )

        assert intelligence.original_query == "recherche les contacts jean"
        assert intelligence.user_goal == UserGoal.COMMUNICATE
        assert intelligence.primary_domain == "contacts"
        assert "contacts" in intelligence.domains

    def test_user_goal_enum(self):
        """Test UserGoal enum values."""
        assert UserGoal.FIND_INFORMATION.value == "find_info"
        assert UserGoal.TAKE_ACTION.value == "take_action"
        assert UserGoal.COMMUNICATE.value == "communicate"
        assert UserGoal.PLAN_ORGANIZE.value == "plan_organize"
        assert UserGoal.UNDERSTAND.value == "understand"
        assert UserGoal.EXPLORE.value == "explore"

    def test_tool_filter_from_intelligence(self):
        """Test creating ToolFilter from QueryIntelligence."""
        intelligence = QueryIntelligence(
            original_query="recherche les contacts",
            english_query="search contacts",
            immediate_intent="search",
            immediate_confidence=0.9,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="Search intent",
            domains=["contacts"],
            primary_domain="contacts",
            domain_scores={},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=True,
            confidence=0.9,
            reasoning_trace=[],
        )

        tool_filter = ToolFilter.from_intelligence(intelligence)

        # ARCHITECTURE v3.1: domain-only filtering — categories stays empty
        # (the LLM sees the complete domain toolset and reasons about deps)
        assert tool_filter.domains == ["contacts"]
        assert tool_filter.categories == []
        assert tool_filter.include_sub_agent_tools is True

    def test_semantic_fallback_threshold(self):
        """SemanticFallback compares against the settings-driven threshold."""
        threshold = SemanticFallback.get_threshold()

        assert SemanticFallback.should_fallback(threshold - 0.01)  # Below threshold
        assert not SemanticFallback.should_fallback(threshold)  # At threshold
        assert not SemanticFallback.should_fallback(1.0)  # Well above


class TestSmartCatalogueService:
    """Test SmartCatalogueService with Panic Mode.

    Tool availability now flows through the per-request ContextVar
    ``request_tool_manifests_ctx`` (single source of truth), not through a
    registry accessor — the fixture populates it with real manifests.
    """

    @pytest.fixture(autouse=True)
    def request_manifests(self):
        """Populate the per-request manifests ContextVar with real manifests."""
        from src.core.context import panic_mode_used, request_tool_manifests_ctx
        from src.domains.agents.registry.manifest_builder import ToolManifestBuilder

        manifests = [
            ToolManifestBuilder("search_contacts", "contacts_agent")
            .with_description("Search contacts")
            .add_parameter("query", "string", required=True, description="Search query")
            .build(),
            ToolManifestBuilder("get_contact_detail", "contacts_agent")
            .with_description("Get contact details")
            .add_parameter("contact_id", "string", required=True, description="Contact ID")
            .build(),
        ]
        manifests_token = request_tool_manifests_ctx.set(manifests)
        panic_token = panic_mode_used.set(False)
        yield
        request_tool_manifests_ctx.reset(manifests_token)
        panic_mode_used.reset(panic_token)

    @pytest.fixture
    def mock_registry(self):
        """Registry double (kept for the service constructor signature)."""
        return MagicMock()

    def test_filter_by_domain_and_intent(self, mock_registry):
        """Test filtering by domain and intent."""
        from src.domains.agents.services.smart_catalogue_service import SmartCatalogueService

        service = SmartCatalogueService(mock_registry)

        intelligence = QueryIntelligence(
            original_query="recherche",
            english_query="search",
            immediate_intent="search",
            immediate_confidence=0.9,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="",
            domains=["contacts"],
            primary_domain="contacts",
            domain_scores={},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=True,
            confidence=0.9,
            reasoning_trace=[],
        )

        filtered = service.filter_for_intelligence(intelligence)

        # Should only include search tools
        assert filtered.tool_count > 0
        assert "contacts" in filtered.domains_included

    def test_panic_mode_expands_catalogue(self, mock_registry):
        """Test Panic Mode expands the catalogue."""
        from src.domains.agents.services.smart_catalogue_service import SmartCatalogueService

        service = SmartCatalogueService(mock_registry)

        intelligence = QueryIntelligence(
            original_query="recherche",
            english_query="search",
            immediate_intent="search",
            immediate_confidence=0.9,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="",
            domains=["contacts"],
            primary_domain="contacts",
            domain_scores={},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=True,
            confidence=0.9,
            reasoning_trace=[],
        )

        # Normal filter
        normal = service.filter_for_intelligence(intelligence, panic_mode=False)

        # Panic mode filter
        service.reset_panic_mode()
        panic = service.filter_for_intelligence(intelligence, panic_mode=True)

        # Panic mode should include more tools or same
        assert panic.tool_count >= normal.tool_count

    def test_panic_mode_only_once(self, mock_registry):
        """Test Panic Mode can only be used once per request."""
        from src.domains.agents.services.smart_catalogue_service import SmartCatalogueService

        service = SmartCatalogueService(mock_registry)

        intelligence = QueryIntelligence(
            original_query="recherche",
            english_query="search",
            immediate_intent="search",
            immediate_confidence=0.9,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="",
            domains=["contacts"],
            primary_domain="contacts",
            domain_scores={},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=True,
            confidence=0.9,
            reasoning_trace=[],
        )

        from src.core.context import panic_mode_used

        # First panic mode call
        service.filter_for_intelligence(intelligence, panic_mode=True)

        # Second panic mode call should return normal filter
        service.filter_for_intelligence(intelligence, panic_mode=True)

        # Panic usage is tracked per-request via ContextVar (not on the
        # service instance — singletons must not hold per-request state)
        assert panic_mode_used.get() is True


class TestRelevanceEngine:
    """Test RelevanceEngine with episodic memory."""

    @pytest.fixture
    def engine(self):
        """Create RelevanceEngine instance."""
        from src.domains.agents.services.relevance_engine import RelevanceEngine

        return RelevanceEngine()

    @pytest.fixture
    def sample_intelligence(self):
        """Create sample QueryIntelligence."""
        return QueryIntelligence(
            original_query="recherche restaurant",
            english_query="search restaurant",
            immediate_intent="search",
            immediate_confidence=0.9,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="",
            domains=["places"],
            primary_domain="places",
            domain_scores={},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=True,
            confidence=0.9,
            reasoning_trace=[],
        )

    def test_rank_empty_results(self, engine, sample_intelligence):
        """Test ranking with empty results."""
        filtered = engine.rank_and_filter([], sample_intelligence)

        assert filtered.total_found == 0
        assert filtered.total_shown == 0
        assert len(filtered.primary_results) == 0

    def test_rank_with_results(self, engine, sample_intelligence):
        """Test ranking with actual results."""
        results = [
            {"name": "Le Zinc", "formattedAddress": "Saint-Maur", "rating": 4.5},
            {"name": "Chez Papa", "formattedAddress": "Paris", "rating": 4.0},
        ]

        filtered = engine.rank_and_filter(results, sample_intelligence)

        assert filtered.total_found == 2
        assert filtered.total_shown <= 2
        assert len(filtered.all_results()) > 0

    def test_smart_limit_by_intent(self, engine):
        """Smart limiting adapts to confidence and user goal.

        Current contract (2026-01: "detail" intent removed): high-confidence
        searches return few results, exploration returns many.
        """

        def _intel(intent: str, confidence: float, goal: UserGoal) -> QueryIntelligence:
            return QueryIntelligence(
                original_query="q",
                english_query="q",
                immediate_intent=intent,
                immediate_confidence=confidence,
                user_goal=goal,
                goal_reasoning="",
                domains=["contacts"],
                primary_domain="contacts",
                domain_scores={},
                turn_type="ACTION",
                route_to="planner",
                bypass_llm=True,
                confidence=confidence,
                reasoning_trace=[],
            )

        # High-confidence search -> precise, few results
        assert engine._determine_limit(_intel("search", 0.95, UserGoal.FIND_INFORMATION)) == 3
        # Exploration -> broad, many results
        assert engine._determine_limit(_intel("chat", 0.5, UserGoal.EXPLORE)) == 10
        # Understanding -> intermediate
        assert engine._determine_limit(_intel("chat", 0.5, UserGoal.UNDERSTAND)) == 7


class TestAutonomousExecutor:
    """Test AutonomousExecutor with safeguards."""

    @pytest.fixture
    def executor(self):
        """Create AutonomousExecutor instance."""
        from src.domains.agents.services.autonomous_executor import AutonomousExecutor

        return AutonomousExecutor()

    def test_safeguard_check_initial(self, executor):
        """Test safeguard check at start."""
        executor._reset_safeguards()

        can_continue, reason = executor._check_safeguards("step_1")

        assert can_continue
        assert reason == ""

    def test_safeguard_max_recoveries(self, executor):
        """Test safeguard blocks after max recoveries."""
        executor._reset_safeguards()
        executor._total_recoveries = executor.MAX_TOTAL_RECOVERIES

        can_continue, reason = executor._check_safeguards("step_1")

        assert not can_continue
        assert "Max total recoveries" in reason

    def test_circuit_breaker_triggers(self, executor):
        """Test circuit breaker after consecutive failures."""
        executor._reset_safeguards()
        executor._consecutive_failures = executor.CIRCUIT_BREAKER_THRESHOLD

        can_continue, reason = executor._check_safeguards("step_1")

        assert not can_continue
        assert "Circuit breaker" in reason

    def test_strategy_blacklisting(self, executor):
        """Test strategy blacklisting after failure."""
        from src.domains.agents.services.autonomous_executor import RecoveryStrategy

        executor._reset_safeguards()

        # Blacklist a strategy
        executor._blacklist_strategy("step_1", RecoveryStrategy.BROADEN_SEARCH)

        # Check it's blacklisted
        assert executor._is_strategy_blacklisted("step_1", RecoveryStrategy.BROADEN_SEARCH)

        # Other strategies should not be blacklisted
        assert not executor._is_strategy_blacklisted("step_1", RecoveryStrategy.RETRY_SAME)


class TestFeedbackLoopService:
    """Test FeedbackLoopService pattern learning."""

    @pytest.fixture
    def service(self):
        """Create FeedbackLoopService instance."""
        from src.domains.agents.services.feedback_loop import FeedbackLoopService

        return FeedbackLoopService()

    @pytest.mark.asyncio
    async def test_record_recovery(self, service):
        """Test recording a recovery attempt."""
        from src.domains.agents.services.feedback_loop import RecoveryOutcome

        await service.record_recovery(
            original_query="jean",
            original_params={"query": "jean"},
            strategy="broaden_search",
            recovered_params={"query": "H"},
            outcome=RecoveryOutcome.SUCCESS,
            domain="contacts",
            tool_name="search_contacts",
        )

        # Check it was recorded
        records = await service.storage.get_all()
        assert len(records) == 1
        assert records[0].recovery_strategy == "broaden_search"

    @pytest.mark.asyncio
    async def test_pattern_learning(self, service):
        """Test pattern learning from successes."""
        from src.domains.agents.services.feedback_loop import RecoveryOutcome

        # Record multiple successes with same pattern
        for _ in range(5):
            await service.record_recovery(
                original_query="jean",
                original_params={"query": "jean"},
                strategy="broaden_search",
                recovered_params={"query": "H"},
                outcome=RecoveryOutcome.SUCCESS,
                domain="contacts",
                tool_name="search_contacts",
            )

        # Check pattern was learned
        insights = await service.get_pattern_insights(domain="contacts")

        assert len(insights) > 0
        # High success rate should have high confidence
        assert any(p.confidence > 0.5 for p in insights)

    @pytest.mark.asyncio
    async def test_preemptive_suggestions(self, service):
        """Test preemptive strategy suggestions."""
        from src.domains.agents.services.feedback_loop import RecoveryOutcome

        # Record multiple successes
        for _ in range(5):
            await service.record_recovery(
                original_query="jean",
                original_params={"query": "jean"},
                strategy="broaden_search",
                recovered_params={"query": "H"},
                outcome=RecoveryOutcome.SUCCESS,
                domain="contacts",
                tool_name="search_contacts",
            )

        # Request suggestions for similar pattern
        intelligence = QueryIntelligence(
            original_query="Foo",  # Short name like "jean"
            english_query="Foo",
            immediate_intent="search",
            immediate_confidence=0.9,
            user_goal=UserGoal.FIND_INFORMATION,
            goal_reasoning="",
            domains=["contacts"],
            primary_domain="contacts",
            domain_scores={},
            turn_type="ACTION",
            route_to="planner",
            bypass_llm=True,
            confidence=0.9,
            reasoning_trace=[],
        )

        suggestions = await service.suggest_preemptive_strategies(intelligence)

        # Should suggest broaden_search based on learned pattern
        assert "broaden_search" in suggestions
