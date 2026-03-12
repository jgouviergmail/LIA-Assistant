"""
Integration Tests - Semantic Expansion ISO-FUNCTIONAL

End-to-end tests to validate the integration of the semantic typing
system with QueryAnalyzerService and the rest of the system.

Validation:
- ISO-FUNCTIONAL behavior (exactly as before)
- Integration with query_analyzer_service
- Zero regression on existing queries
"""

from unittest.mock import Mock, patch

import pytest

from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.expansion_service import (
    get_expansion_service,
    reset_expansion_service,
)
from src.domains.agents.semantic.type_registry import get_registry, reset_registry
from src.domains.agents.services.query_analyzer_service import (
    get_query_analyzer_service,
    reset_query_analyzer_service,
)


@pytest.fixture(autouse=True)
def setup_semantic_system():
    """Setup: load semantic types before each test."""
    reset_registry()
    reset_expansion_service()

    # Load core types
    registry = get_registry()
    load_core_types(registry)

    yield

    # Cleanup
    reset_registry()
    reset_expansion_service()


@pytest.fixture
def query_analyzer_service():
    """Fixture for QueryAnalyzerService."""
    # Reset singleton for isolated tests
    reset_query_analyzer_service()
    # Note: In real integration, we would use the actual service
    # For these tests, we mock the dependencies
    service = get_query_analyzer_service()
    yield service
    reset_query_analyzer_service()


class TestQueryAnalyzerIntegration:
    """Integration tests with QueryAnalyzerService."""

    @pytest.mark.asyncio
    async def test_expand_domains_routes_with_person_reference(self, query_analyzer_service):
        """
        Test ISO-FONCTIONNEL: "itinéraire chez mon frère"

        - Domain: routes
        - has_person_reference: True
        - required_types: {physical_address}
        - Expected: ["routes", "contacts"]
        """
        # Simulate agent_registry providing required_types
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            # Mock agent registry
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "physical_address": ["get_route_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            # Call the method
            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["routes"],
                has_person_reference=True,
                reasoning_trace=[],
            )

            # ISO-FUNCTIONAL verifications
            assert "routes" in result, "Original domain should be preserved"
            assert "contacts" in result, "Contacts should be added (provides physical_address)"
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_expand_domains_calendar_with_person_reference(self, query_analyzer_service):
        """
        Test ISO-FONCTIONNEL: "rdv avec mon frère"

        - Domain: calendar
        - has_person_reference: True
        - required_types: {email_address}
        - Expected: ["calendar", "contacts"]
        """
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "email_address": ["create_event_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["calendar"],
                has_person_reference=True,
                reasoning_trace=[],
            )

            assert "calendar" in result
            assert "contacts" in result

    @pytest.mark.asyncio
    async def test_no_expansion_without_person_reference(self, query_analyzer_service):
        """
        CRITICAL ISO-FUNCTIONAL test: "recherche mes 2 prochains rdv"

        - Domain: calendar
        - has_person_reference: False  <- NO person reference
        - required_types: {datetime}
        - Expected: ["calendar"] (NO expansion)
        """
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "datetime": ["search_events_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["calendar"],
                has_person_reference=False,  # <- NO person reference
                reasoning_trace=[],
            )

            # NO expansion
            assert result == ["calendar"]
            assert "contacts" not in result

    @pytest.mark.asyncio
    async def test_expansion_with_multiple_types(self, query_analyzer_service):
        """
        Test: multiple required types.

        - Domain: calendar
        - has_person_reference: True
        - required_types: {email_address, physical_address}
        - Expected: ["calendar", "contacts"] (contacts added only once)
        """
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "email_address": ["create_event_tool"],
                "physical_address": ["create_event_tool"],
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["calendar"],
                has_person_reference=True,
                reasoning_trace=[],
            )

            assert "calendar" in result
            assert "contacts" in result
            # Contacts should only be added once
            assert result.count("contacts") == 1

    @pytest.mark.asyncio
    async def test_expansion_reasoning_trace(self, query_analyzer_service):
        """Test that reasoning_trace is correctly populated."""
        reasoning_trace = []

        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "physical_address": ["get_route_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["routes"],
                has_person_reference=True,
                reasoning_trace=reasoning_trace,
            )

            assert "routes" in result
            assert "contacts" in result
            # Verify that reasoning_trace was populated
            assert len(reasoning_trace) > 0
            assert any("expansion" in str(r).lower() for r in reasoning_trace)

    @pytest.mark.asyncio
    async def test_expansion_with_empty_required_types(self, query_analyzer_service):
        """Test: no required types."""
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            # No required types
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {}
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["calendar"],
                has_person_reference=True,
                reasoning_trace=[],
            )

            # No expansion if no required types
            assert result == ["calendar"]

    @pytest.mark.asyncio
    async def test_expansion_error_handling(self, query_analyzer_service):
        """Test: error handling when registry fails."""
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            # Simulate an error
            mock_registry.side_effect = Exception("Registry error")

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["routes"],
                has_person_reference=True,
                reasoning_trace=[],
            )

            # Fallback: return original domains
            assert result == ["routes"]


class TestExpansionServiceValidation:
    """Validation tests for the expansion service."""

    def test_expansion_service_validation(self):
        """Validate that the expansion service is correctly configured."""
        service = get_expansion_service()
        validation = service.validate_expansion_logic()

        # Must be valid
        assert validation["valid"] is True, f"Validation errors: {validation['errors']}"

        # Verify stats
        stats = validation["registry_stats"]
        assert stats["total_types"] >= 96
        assert stats["total_domains"] > 0

    def test_contacts_provides_required_types(self):
        """Verify that contacts provides the required types."""
        service = get_expansion_service()

        # Contacts must provide physical_address
        address_providers = service.get_providers_for_type("physical_address")
        assert "contacts" in address_providers

        # Contacts must provide email_address
        email_providers = service.get_providers_for_type("email_address")
        assert "contacts" in email_providers

    def test_registry_contains_all_explicit_types(self):
        """Verify that the 5 explicit types exist."""
        registry = get_registry()

        explicit_types = [
            "email_address",
            "physical_address",
            "phone_number",
            "person_name",
            "coordinate",
        ]

        for type_name in explicit_types:
            assert type_name in registry, f"Type '{type_name}' should be in registry"
            type_def = registry.get(type_name)
            assert type_def is not None
            assert (
                len(type_def.source_domains) > 0
            ), f"Type '{type_name}' should have source domains"


class TestRegressionScenarios:
    """Non-regression tests on real-world scenarios."""

    @pytest.mark.asyncio
    async def test_scenario_routes_chez_frere(self, query_analyzer_service):
        """
        Real-world scenario: "itinéraire chez mon frère"

        Query: "itinéraire chez mon frère"
        Router: selects "routes"
        Memory: resolves "mon frère" -> "jean" (has_person_reference=True)
        Expansion: routes + contacts
        Expected: get_contacts_tool -> get_route_tool
        """
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "physical_address": ["get_route_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["routes"],
                has_person_reference=True,
                reasoning_trace=[],
            )

            assert result == ["routes", "contacts"]

    @pytest.mark.asyncio
    async def test_scenario_rdv_avec_frere(self, query_analyzer_service):
        """
        Real-world scenario: "rdv avec mon frère"

        Query: "rdv avec mon frère"
        Router: selects "calendar"
        Memory: resolves "mon frère" -> "jean" (has_person_reference=True)
        Expansion: calendar + contacts (for attendee email)
        Expected: get_contacts_tool -> create_event_tool
        """
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "email_address": ["create_event_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["calendar"],
                has_person_reference=True,
                reasoning_trace=[],
            )

            assert result == ["calendar", "contacts"]

    @pytest.mark.asyncio
    async def test_scenario_mes_prochains_rdv(self, query_analyzer_service):
        """
        Real-world scenario: "recherche mes 2 prochains rdv"

        Query: "recherche mes 2 prochains rdv"
        Router: selects "calendar"
        Memory: "mes" = user self, NOT another person (has_person_reference=False)
        Expansion: NONE
        Expected: ONLY calendar, NO contacts
        """
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "datetime": ["search_events_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["calendar"],
                has_person_reference=False,  # ← "mes" = self
                reasoning_trace=[],
            )

            # NO expansion
            assert result == ["calendar"]
            assert "contacts" not in result


class TestEdgeCasesIntegration:
    """Edge case tests in integration."""

    @pytest.mark.asyncio
    async def test_empty_domains_list(self, query_analyzer_service):
        """Test: empty domain list."""
        with patch("src.domains.agents.services.query_analyzer_service.get_global_registry"):
            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=[],
                has_person_reference=True,
                reasoning_trace=[],
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_contacts_already_in_domains(self, query_analyzer_service):
        """Test: contacts already in the domains."""
        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "physical_address": ["get_route_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["routes", "contacts"],  # contacts already present
                has_person_reference=True,
                reasoning_trace=[],
            )

            # No duplication
            assert result.count("contacts") == 1
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_expansion_reasons_parameter(self, query_analyzer_service):
        """Test: optional expansion_reasons parameter."""
        expansion_reasons = []

        with patch(
            "src.domains.agents.services.query_analyzer_service.get_global_registry"
        ) as mock_registry:
            mock_agent_reg = Mock()
            mock_agent_reg.get_required_semantic_types_for_domains.return_value = {
                "physical_address": ["get_route_tool"]
            }
            mock_registry.return_value = mock_agent_reg

            result = await query_analyzer_service._expand_domains_for_semantic_types(
                domains=["routes"],
                has_person_reference=True,
                reasoning_trace=[],
                expansion_reasons=expansion_reasons,
            )

            assert "contacts" in result
            # expansion_reasons should be populated
            assert len(expansion_reasons) > 0
            assert any("physical_address" in r for r in expansion_reasons)
