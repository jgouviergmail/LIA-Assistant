"""
Unit Tests - Semantic Expansion Service ISO-FUNCTIONAL

These tests validate that SemanticExpansionService reproduces
EXACTLY the current hardcoded behavior.

Step 1 validation criteria:
- Zero regression: behavior identical to current code
- ISO-functional: all existing use cases work
- Performance: latency <= baseline +10ms
"""

import pytest

from src.domains.agents.semantic.core_types import load_core_types
from src.domains.agents.semantic.expansion_service import (
    SemanticExpansionService,
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


class TestSemanticTypeRegistry:
    """Tests for TypeRegistry."""

    def test_registry_loads_core_types(self, registry):
        """Verify that core types are loaded."""
        assert len(registry) >= 96, "Should have 96+ types"

        # Verify explicit types
        assert "email_address" in registry
        assert "physical_address" in registry
        assert "phone_number" in registry
        assert "person_name" in registry
        assert "coordinate" in registry

    def test_registry_hierarchy(self, registry):
        """Verify the type hierarchy."""
        # physical_address → PostalAddress → Place → Thing
        path = registry.get_hierarchy_path("physical_address")
        assert "Thing" in path
        assert "Place" in path
        assert "PostalAddress" in path
        assert "physical_address" in path

        # Verify hierarchical order
        assert path.index("Thing") < path.index("Place")
        assert path.index("Place") < path.index("PostalAddress")
        assert path.index("PostalAddress") < path.index("physical_address")

    def test_registry_subsumption(self, registry):
        """Verify subsumption (is-a)."""
        # physical_address is a PostalAddress
        assert registry.is_subtype_of("physical_address", "PostalAddress")

        # physical_address is a Place (transitive)
        assert registry.is_subtype_of("physical_address", "Place")

        # physical_address is a Thing (transitive)
        assert registry.is_subtype_of("physical_address", "Thing")

        # NOT: Thing is NOT a physical_address
        assert not registry.is_subtype_of("Thing", "physical_address")

    def test_registry_wu_palmer_distance(self, registry):
        """Verify Wu & Palmer distance computation."""
        # Identical distance
        assert registry.compute_distance_wu_palmer("email_address", "email_address") == 1.0

        # Distance between email and phone (share ContactPoint)
        email_phone_dist = registry.compute_distance_wu_palmer("email_address", "phone_number")
        assert 0.5 < email_phone_dist < 1.0, "Should share parent ContactPoint"

        # Distance between unrelated types
        email_temp_dist = registry.compute_distance_wu_palmer("email_address", "temperature")
        assert email_temp_dist < email_phone_dist, "Unrelated types should be more distant"

    def test_registry_get_by_domain(self, registry):
        """Verify lookup by domain."""
        # Domain name is "contact" (singular), result_key is "contacts" (plural)
        contact_types = registry.get_by_domain("contact")

        # Contact must provide email_address and physical_address
        assert "email_address" in contact_types
        assert "physical_address" in contact_types
        assert "phone_number" in contact_types
        assert "person_name" in contact_types
        assert "contact_id" in contact_types

    def test_registry_validation(self, registry):
        """Verify that the hierarchy is valid."""
        errors = registry.validate_hierarchy()
        assert len(errors) == 0, f"Hierarchy should be valid, got errors: {errors}"


class TestSemanticExpansionServiceIsoFunctional:
    """Tests for the ISO-FUNCTIONAL expansion service."""

    @pytest.mark.asyncio
    async def test_expansion_physical_address_with_person(self, expansion_service):
        """
        ISO-FUNCTIONAL test: exact reproduction of current behavior.

        Query: "itinéraire chez mon frère"
        - has_person_reference: True (memory resolved "mon frère")
        - required_types: {physical_address}
        - Expected: domains + ["contacts"]

        Current hardcoded behavior:
        if has_person_reference and "physical_address" in required_types:
            domains_to_add.add("contacts")
        """
        result = await expansion_service.expand_domains_iso_functional(
            domains=["routes"],
            has_person_reference=True,
            required_semantic_types={"physical_address"},
            query="itinéraire chez mon frère",
        )

        # Verifications
        # Domain name is "contact" (singular)
        assert "routes" in result, "Original domain should be preserved"
        assert "contact" in result, "Contact should be added (provides physical_address)"
        assert len(result) == 2, "Should have exactly 2 domains"

    @pytest.mark.asyncio
    async def test_expansion_email_with_person(self, expansion_service):
        """
        Test: "rdv avec mon frère"
        - has_person_reference: True
        - required_types: {email_address}
        - Expected: domains + ["contacts"]
        """
        result = await expansion_service.expand_domains_iso_functional(
            domains=["calendar"],
            has_person_reference=True,
            required_semantic_types={"email_address"},
            query="rdv avec mon frère",
        )

        assert "calendar" in result
        assert "contact" in result, "Contact should be added (provides email_address)"

    @pytest.mark.asyncio
    async def test_expansion_both_types_with_person(self, expansion_service):
        """
        Test: multiple required types
        - has_person_reference: True
        - required_types: {physical_address, email_address}
        - Expected: domains + ["contacts"] (only once)
        """
        result = await expansion_service.expand_domains_iso_functional(
            domains=["calendar"],
            has_person_reference=True,
            required_semantic_types={"physical_address", "email_address"},
            query="rdv chez mon frère",
        )

        assert "calendar" in result
        assert "contact" in result
        # Contact should be added only ONCE (not twice)
        assert result.count("contact") == 1

    @pytest.mark.asyncio
    async def test_no_expansion_without_person(self, expansion_service):
        """
        CRITICAL test: NO expansion if no person reference.

        Query: "recherche mes 2 prochains rdv"
        - has_person_reference: False
        - required_types: {physical_address}
        - Expected: NO expansion (domains unchanged)

        This is the current ISO-FUNCTIONAL behavior:
        only a reference to ANOTHER person triggers expansion.
        """
        result = await expansion_service.expand_domains_iso_functional(
            domains=["calendar"],
            has_person_reference=False,
            required_semantic_types={"physical_address"},
            query="recherche mes 2 prochains rdv",
        )

        # NO expansion
        assert result == ["calendar"], "Should NOT expand without person reference"
        assert "contact" not in result

    @pytest.mark.asyncio
    async def test_no_expansion_already_present(self, expansion_service):
        """
        Test: contact already present, do not duplicate.

        - domains: ["routes", "contact"]
        - has_person_reference: True
        - required_types: {physical_address}
        - Expected: no duplication
        """
        result = await expansion_service.expand_domains_iso_functional(
            domains=["routes", "contact"],
            has_person_reference=True,
            required_semantic_types={"physical_address"},
            query="itinéraire chez mon frère",
        )

        assert result.count("contact") == 1, "Contact should not be duplicated"
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_no_expansion_other_types(self, expansion_service):
        """
        Test: types other than physical_address/email_address.

        - has_person_reference: True
        - required_types: {datetime, temperature}
        - Expected: NO expansion (types not supported by current expansion)
        """
        result = await expansion_service.expand_domains_iso_functional(
            domains=["calendar"],
            has_person_reference=True,
            required_semantic_types={"datetime", "temperature"},
            query="météo de mon rdv",
        )

        # NO expansion (datetime and temperature do not trigger expansion)
        assert result == ["calendar"]
        assert "contact" not in result

    @pytest.mark.asyncio
    async def test_empty_domains(self, expansion_service):
        """Test: empty domains."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=[],
            has_person_reference=True,
            required_semantic_types={"physical_address"},
            query="test",
        )

        assert result == [], "Empty domains should stay empty"

    @pytest.mark.asyncio
    async def test_empty_required_types(self, expansion_service):
        """Test: empty required types."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["calendar"],
            has_person_reference=True,
            required_semantic_types=set(),
            query="test",
        )

        assert result == ["calendar"], "No expansion with empty required types"


class TestExpansionServiceHelpers:
    """Tests for the service helper methods."""

    def test_get_providers_for_type(self, expansion_service):
        """Test get_providers_for_type."""
        # physical_address providers (domain names are singular)
        providers = expansion_service.get_providers_for_type("physical_address")
        assert "contact" in providers
        assert "place" in providers
        assert "event" in providers
        assert "route" in providers

        # email_address providers (domain names are singular)
        email_providers = expansion_service.get_providers_for_type("email_address")
        assert "contact" in email_providers
        assert "email" in email_providers
        assert "event" in email_providers

    def test_get_providers_unknown_type(self, expansion_service):
        """Test get_providers with unknown type."""
        providers = expansion_service.get_providers_for_type("unknown_type_xyz")
        assert providers == [], "Unknown type should return empty list"

    def test_get_types_for_domain(self, expansion_service):
        """Test get_types_for_domain."""
        # Domain name is "contact" (singular)
        contact_types = expansion_service.get_types_for_domain("contact")

        # Verify types provided by contact
        assert "email_address" in contact_types
        assert "physical_address" in contact_types
        assert "phone_number" in contact_types
        assert "person_name" in contact_types
        assert "contact_id" in contact_types

    def test_validate_expansion_logic(self, expansion_service):
        """Validate that the ISO-FUNCTIONAL logic is correct."""
        validation = expansion_service.validate_expansion_logic()

        assert validation["valid"] is True, f"Validation errors: {validation['errors']}"
        assert len(validation["errors"]) == 0

        # Verify stats
        stats = validation["registry_stats"]
        assert stats["total_types"] >= 96


class TestPerformance:
    """Performance tests (latency <= baseline +10ms)."""

    @pytest.mark.asyncio
    async def test_expansion_performance(self, expansion_service):
        """
        Expansion performance test.

        Step 1 criterion: latency <= baseline +10ms
        """
        import time

        # Run multiple times to get average
        total_time = 0
        iterations = 10

        for _ in range(iterations):
            start = time.perf_counter()
            result = await expansion_service.expand_domains_iso_functional(
                domains=["routes"],
                has_person_reference=True,
                required_semantic_types={"physical_address", "email_address"},
                query="test",
            )
            duration_ms = (time.perf_counter() - start) * 1000
            total_time += duration_ms

            assert result == ["routes", "contact"]

        avg_duration_ms = total_time / iterations
        assert (
            avg_duration_ms < 10
        ), f"Average expansion took {avg_duration_ms:.2f}ms (should be <10ms)"


class TestEdgeCases:
    """Edge case tests."""

    @pytest.mark.asyncio
    async def test_multiple_domains_expansion(self, expansion_service):
        """Test with multiple domains."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["routes", "calendar"],
            has_person_reference=True,
            required_semantic_types={"physical_address", "email_address"},
            query="test",
        )

        assert "routes" in result
        assert "calendar" in result
        assert "contact" in result
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_type_not_in_registry(self, expansion_service):
        """Test with type not in the registry."""
        # Fictitious unregistered type
        result = await expansion_service.expand_domains_iso_functional(
            domains=["calendar"],
            has_person_reference=True,
            required_semantic_types={"unknown_fictional_type"},
            query="test",
        )

        # No error, simply no expansion
        assert result == ["calendar"]

    @pytest.mark.asyncio
    async def test_only_email_address(self, expansion_service):
        """Test with only email_address (not physical_address)."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["email"],
            has_person_reference=True,
            required_semantic_types={"email_address"},
            query="test",
        )

        # Contact should be added (singular domain name)
        assert "contact" in result

    @pytest.mark.asyncio
    async def test_only_physical_address(self, expansion_service):
        """Test with only physical_address (not email_address)."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["route"],
            has_person_reference=True,
            required_semantic_types={"physical_address"},
            query="test",
        )

        # Contact should be added (singular domain name)
        assert "contact" in result
