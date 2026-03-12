"""
Tests Unitaires - Semantic Linking Service (Phase 2 - 2026-01)

Tests for the semantic linking features:
- expand_domains_semantic(): Generalized domain expansion
- generate_jinja2_suggestions(): Jinja2 reference generation
- generate_linking_hints_for_plan(): Plan-level hint generation

These tests validate the new semantic linking features that enable
cross-domain parameter linking based on semantic_type matching.
"""

import pytest

from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.expansion_service import (
    SemanticExpansionService,
    generate_jinja2_suggestions,
    generate_linking_hints_for_plan,
    reset_expansion_service,
)
from src.domains.agents.semantic.type_registry import reset_registry


@pytest.fixture
def registry():
    """Registry with core types loaded."""
    reset_registry()
    from src.domains.agents.semantic.type_registry import get_registry

    reg = get_registry()
    load_core_types(reg)
    yield reg
    reset_registry()


@pytest.fixture
def expansion_service(registry):
    """Expansion service with registry."""
    reset_expansion_service()
    service = SemanticExpansionService(registry=registry)
    yield service
    reset_expansion_service()


@pytest.fixture
def agent_registry():
    """
    Initialize agent registry with tool manifests.
    Required for generate_jinja2_suggestions tests.
    """
    from src.domains.agents.registry import get_global_registry, reset_global_registry

    reset_global_registry()
    agent_reg = get_global_registry()

    # Ensure the registry is properly initialized with manifests
    # The registry auto-loads manifests when needed
    yield agent_reg

    reset_global_registry()


class TestExpandDomainsSemantic:
    """Tests for expand_domains_semantic() - Generalized expansion."""

    @pytest.mark.asyncio
    async def test_expands_all_providers_not_just_contacts(self, expansion_service):
        """
        Verify that expand_domains_semantic checks ALL providers,
        not just "contacts" like the ISO-FUNCTIONAL version.
        """
        result = await expansion_service.expand_domains_semantic(
            primary_domains=["emails"],
            required_semantic_types={"email_address"},
            threshold=0.0,  # Low threshold to include all providers
            query="test",
        )

        # Should find contact as provider of email_address (singular domain name)
        assert "contact" in result
        assert "email" in result or "emails" in result  # Original domain preserved

    @pytest.mark.asyncio
    async def test_threshold_filtering(self, expansion_service):
        """
        Verify that threshold parameter controls provider inclusion.

        - threshold < 1.0: All providers in source_domains are added
        - threshold = 1.0: No providers are added
        """
        # Low threshold - should include providers
        result_low = await expansion_service.expand_domains_semantic(
            primary_domains=["emails"],
            required_semantic_types={"email_address"},
            threshold=0.5,
            query="test",
        )

        # Threshold 1.0 - should include NO providers
        result_max = await expansion_service.expand_domains_semantic(
            primary_domains=["emails"],
            required_semantic_types={"email_address"},
            threshold=1.0,
            query="test",
        )

        # Low threshold should have more domains than max threshold
        assert len(result_low) > len(result_max)
        assert result_max == ["emails"]  # Only original domain with threshold=1.0

    @pytest.mark.asyncio
    async def test_no_expansion_empty_domains(self, expansion_service):
        """Empty domains should stay empty."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=[],
            required_semantic_types={"email_address"},
            threshold=0.7,
            query="test",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_no_expansion_empty_types(self, expansion_service):
        """Empty required types should not expand."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=["emails"],
            required_semantic_types=set(),
            threshold=0.7,
            query="test",
        )

        assert result == ["emails"]

    @pytest.mark.asyncio
    async def test_unknown_type_graceful_handling(self, expansion_service):
        """Unknown semantic type should not cause error."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=["emails"],
            required_semantic_types={"unknown_fictional_type_xyz"},
            threshold=0.7,
            query="test",
        )

        # Should return original domains without error
        assert result == ["emails"]


class TestGetPrimaryTypeForDomain:
    """Tests for _get_primary_type_for_domain() helper."""

    def test_known_domains_have_primary_types(self, expansion_service):
        """Known domains should return their primary types (singular domain names)."""
        assert expansion_service._get_primary_type_for_domain("contact") == "person_name"
        assert expansion_service._get_primary_type_for_domain("email") == "message_id"
        assert expansion_service._get_primary_type_for_domain("event") == "event_id"
        assert expansion_service._get_primary_type_for_domain("task") == "task_id"
        assert expansion_service._get_primary_type_for_domain("file") == "file_id"
        assert expansion_service._get_primary_type_for_domain("place") == "place_id"
        assert expansion_service._get_primary_type_for_domain("route") == "physical_address"

    def test_unknown_domain_returns_text(self, expansion_service):
        """Unknown domains should return 'text' as fallback."""
        assert expansion_service._get_primary_type_for_domain("unknown_domain") == "text"


class TestGenerateJinja2Suggestions:
    """Tests for generate_jinja2_suggestions() function."""

    def test_returns_empty_for_unknown_tool(self, agent_registry):
        """Unknown tool should return empty list."""
        result = generate_jinja2_suggestions(
            target_tool="unknown_tool_xyz",
            target_param="param",
            available_step_ids=["step1"],
        )

        assert result == []

    def test_returns_empty_for_param_without_semantic_type(self, agent_registry):
        """Parameter without semantic_type should return empty list."""
        # Most parameters don't have semantic_type explicitly set
        result = generate_jinja2_suggestions(
            target_tool="get_tasks_tool",
            target_param="max_results",  # This param has no semantic_type
            available_step_ids=["get_contacts"],
        )

        assert result == []

    def test_max_suggestions_limit(self, agent_registry):
        """Should respect max_suggestions limit."""
        result = generate_jinja2_suggestions(
            target_tool="get_route_tool",
            target_param="destination",
            available_step_ids=["step1", "step2", "step3", "step4", "step5", "step6"],
            max_suggestions=2,
        )

        assert len(result) <= 2


class TestGenerateLinkingHintsForPlan:
    """Tests for generate_linking_hints_for_plan() function."""

    def test_empty_plan_returns_empty_hints(self, agent_registry):
        """Empty plan should return empty hints."""
        result = generate_linking_hints_for_plan([])
        assert result == {}

    def test_single_step_no_hints(self, agent_registry):
        """Single step plan has no preceding steps, so no hints."""
        result = generate_linking_hints_for_plan(
            [
                {"step_id": "get_contacts", "tool_name": "get_contacts_tool", "parameters": {}},
            ]
        )

        # First step has no preceding steps, so no hints possible
        assert result == {}

    def test_plan_with_unknown_tools(self, agent_registry):
        """Plan with unknown tools should not cause errors."""
        result = generate_linking_hints_for_plan(
            [
                {"step_id": "step1", "tool_name": "unknown_tool_xyz", "parameters": {}},
                {"step_id": "step2", "tool_name": "another_unknown", "parameters": {}},
            ]
        )

        # Should return empty without errors
        assert result == {}

    def test_respects_max_suggestions_per_param(self, agent_registry):
        """Should respect max_suggestions_per_param parameter."""
        result = generate_linking_hints_for_plan(
            plan_steps=[
                {"step_id": "get_contacts", "tool_name": "get_contacts_tool", "parameters": {}},
                {"step_id": "send_email", "tool_name": "send_email_tool", "parameters": {}},
            ],
            max_suggestions_per_param=1,
        )

        # All hints should have at most 1 suggestion
        for hints_list in result.values():
            assert len(hints_list) <= 1


class TestSemanticLinkingIntegration:
    """Integration tests for semantic linking workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow_contacts_to_email(self, expansion_service, agent_registry):
        """
        Test complete workflow: contact → email linking.

        Scenario: User wants to send email to a contact.
        1. get_contacts provides email_address
        2. send_email needs email_address (to parameter)
        3. Semantic linking should suggest the connection
        """
        # Step 1: Verify contact provides email_address (singular domain name)
        contact_types = expansion_service.get_types_for_domain("contact")
        assert "email_address" in contact_types

        # Step 2: Verify expansion would add contact for email domain
        expanded = await expansion_service.expand_domains_semantic(
            primary_domains=["email"],
            required_semantic_types={"email_address"},
            threshold=0.5,
            query="send email to Jean",
        )
        assert "contact" in expanded

    @pytest.mark.asyncio
    async def test_full_workflow_contacts_to_routes(self, expansion_service, agent_registry):
        """
        Test complete workflow: contact → route linking.

        Scenario: User wants route to a contact's address.
        1. get_contacts provides physical_address
        2. get_route needs physical_address (destination parameter)
        3. Semantic linking should suggest the connection
        """
        # Step 1: Verify contact provides physical_address (singular domain name)
        contact_types = expansion_service.get_types_for_domain("contact")
        assert "physical_address" in contact_types

        # Step 2: Verify expansion would add contact for route domain
        expanded = await expansion_service.expand_domains_semantic(
            primary_domains=["route"],
            required_semantic_types={"physical_address"},
            threshold=0.5,
            query="directions to Jean's house",
        )
        assert "contact" in expanded


class TestPerformanceSemantic:
    """Performance tests for semantic linking."""

    @pytest.mark.asyncio
    async def test_expansion_performance(self, expansion_service):
        """
        Test performance of expand_domains_semantic.

        Target: <50ms for typical queries.
        """
        import time

        total_time = 0
        iterations = 10

        for _ in range(iterations):
            start = time.perf_counter()
            await expansion_service.expand_domains_semantic(
                primary_domains=["emails", "calendar"],
                required_semantic_types={"email_address", "physical_address"},
                threshold=0.7,
                query="test performance",
            )
            duration_ms = (time.perf_counter() - start) * 1000
            total_time += duration_ms

        avg_duration_ms = total_time / iterations
        assert (
            avg_duration_ms < 50
        ), f"Average expansion took {avg_duration_ms:.2f}ms (should be <50ms)"

    def test_jinja2_suggestions_performance(self, agent_registry):
        """
        Test performance of generate_jinja2_suggestions.

        Target: <20ms per call.
        """
        import time

        total_time = 0
        iterations = 10

        for _ in range(iterations):
            start = time.perf_counter()
            generate_jinja2_suggestions(
                target_tool="get_route_tool",
                target_param="destination",
                available_step_ids=["get_contacts", "get_events", "search_places"],
                max_suggestions=5,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            total_time += duration_ms

        avg_duration_ms = total_time / iterations
        assert (
            avg_duration_ms < 20
        ), f"Average jinja2 suggestions took {avg_duration_ms:.2f}ms (should be <20ms)"
