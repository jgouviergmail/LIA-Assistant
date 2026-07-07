"""
Tests for v3 Architecture Components.

Architecture v3 - Intelligence, Autonomie, Pertinence.

These tests validate:
1. QueryIntelligence - User goal inference
2. SmartCatalogueService - Catalogue filtering with Panic Mode
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
        from src.domains.agents.registry.catalogue import (
            CostProfile,
            ParameterSchema,
            PermissionProfile,
            ToolManifest,
        )

        def _manifest(name: str, description: str, param: str, param_desc: str) -> ToolManifest:
            return ToolManifest(
                name=name,
                agent="contacts_agent",
                description=description,
                parameters=[
                    ParameterSchema(
                        name=param, type="string", required=True, description=param_desc
                    )
                ],
                outputs=[],
                cost=CostProfile(),
                permissions=PermissionProfile(),
            )

        manifests = [
            _manifest("search_contacts", "Search contacts", "query", "Search query"),
            _manifest("get_contact_detail", "Get contact details", "contact_id", "Contact ID"),
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
