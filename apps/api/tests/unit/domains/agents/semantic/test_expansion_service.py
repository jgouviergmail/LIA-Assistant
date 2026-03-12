"""
Unit tests for semantic expansion service.

Tests for SemanticExpansionService that handles domain expansion
based on semantic type matching.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.semantic.expansion_service import (
    SemanticExpansionService,
    get_expansion_service,
    reset_expansion_service,
)
from src.domains.agents.semantic.semantic_type import SemanticType, TypeCategory
from src.domains.agents.semantic.type_registry import TypeRegistry


@pytest.fixture
def mock_registry():
    """Create a mock registry with test types."""
    registry = TypeRegistry()

    # Register test types
    types = [
        SemanticType(
            name="Thing",
            category=TypeCategory.IDENTITY,
        ),
        SemanticType(
            name="email_address",
            parent="Thing",
            category=TypeCategory.IDENTITY,
            source_domains=["contact", "email"],
            used_in_tools=["send_email_tool", "get_contact_tool"],
        ),
        SemanticType(
            name="physical_address",
            parent="Thing",
            category=TypeCategory.LOCATION,
            source_domains=["contact", "place", "route"],
            used_in_tools=["get_route_tool", "search_place_tool"],
        ),
        SemanticType(
            name="phone_number",
            parent="Thing",
            category=TypeCategory.IDENTITY,
            source_domains=["contact"],
            used_in_tools=["get_contact_tool"],
        ),
        SemanticType(
            name="person_name",
            parent="Thing",
            category=TypeCategory.IDENTITY,
            source_domains=["contact"],
            used_in_tools=["get_contact_tool"],
        ),
        SemanticType(
            name="coordinate",
            parent="Thing",
            category=TypeCategory.LOCATION,
            source_domains=["place", "route"],
            used_in_tools=["get_route_tool"],
        ),
        SemanticType(
            name="datetime",
            parent="Thing",
            category=TypeCategory.TEMPORAL,
            source_domains=["event", "task"],
            used_in_tools=["create_event_tool"],
        ),
    ]

    for type_def in types:
        registry.register(type_def)

    return registry


@pytest.fixture
def expansion_service(mock_registry):
    """Create expansion service with mock registry."""
    return SemanticExpansionService(registry=mock_registry)


class TestSemanticExpansionServiceInit:
    """Tests for SemanticExpansionService initialization."""

    def test_init_with_registry(self, mock_registry):
        """Test initialization with provided registry."""
        service = SemanticExpansionService(registry=mock_registry)

        assert service.registry is mock_registry

    @patch("src.domains.agents.semantic.expansion_service.get_registry")
    @patch("src.domains.agents.semantic.expansion_service.load_core_types")
    def test_init_uses_global_registry_when_none(self, mock_load, mock_get_registry):
        """Test that init uses global registry when none provided."""
        mock_registry = MagicMock()
        mock_registry.__len__ = MagicMock(return_value=10)
        mock_get_registry.return_value = mock_registry

        service = SemanticExpansionService(registry=None)

        mock_get_registry.assert_called_once()
        assert service.registry is mock_registry

    @patch("src.domains.agents.semantic.expansion_service.get_registry")
    @patch("src.domains.agents.semantic.expansion_service.load_core_types")
    def test_init_loads_core_types_when_empty(self, mock_load, mock_get_registry):
        """Test that init loads core types when registry is empty."""
        mock_registry = MagicMock()
        mock_registry.__len__ = MagicMock(return_value=0)
        mock_get_registry.return_value = mock_registry

        SemanticExpansionService(registry=None)

        mock_load.assert_called_once_with(mock_registry)


class TestExpandDomainsIsoFunctional:
    """Tests for expand_domains_iso_functional method."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_domains(self, expansion_service):
        """Test that empty domains returns empty."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=[],
            has_person_reference=True,
            required_semantic_types={"email_address"},
            query="test query",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_no_expansion_without_person_reference(self, expansion_service):
        """Test that no expansion happens without person reference."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["route"],
            has_person_reference=False,
            required_semantic_types={"physical_address"},
            query="itinéraire vers Paris",
        )

        assert result == ["route"]
        assert "contact" not in result

    @pytest.mark.asyncio
    async def test_expands_with_person_reference_and_email(self, expansion_service):
        """Test expansion when person reference and email_address required."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["email"],
            has_person_reference=True,
            required_semantic_types={"email_address"},
            query="envoie un email à mon frère",
        )

        assert "email" in result
        assert "contact" in result

    @pytest.mark.asyncio
    async def test_expands_with_person_reference_and_address(self, expansion_service):
        """Test expansion when person reference and physical_address required."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["route"],
            has_person_reference=True,
            required_semantic_types={"physical_address"},
            query="itinéraire chez mon frère",
        )

        assert "route" in result
        assert "contact" in result

    @pytest.mark.asyncio
    async def test_no_duplicate_contact(self, expansion_service):
        """Test that contact is not added if already present."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["contact"],
            has_person_reference=True,
            required_semantic_types={"email_address"},
            query="email de mon frère",
        )

        # Should have exactly one "contact"
        assert result.count("contact") == 1

    @pytest.mark.asyncio
    async def test_skips_unknown_semantic_types(self, expansion_service):
        """Test that unknown semantic types are skipped."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["email"],
            has_person_reference=True,
            required_semantic_types={"unknown_type"},
            query="test",
        )

        # No expansion for unknown type
        assert result == ["email"]

    @pytest.mark.asyncio
    async def test_no_expansion_for_non_contact_provider(self, expansion_service):
        """Test no expansion when type not provided by contact."""
        result = await expansion_service.expand_domains_iso_functional(
            domains=["event"],
            has_person_reference=True,
            required_semantic_types={"datetime"},  # Not provided by contact
            query="rdv demain",
        )

        assert result == ["event"]
        assert "contact" not in result


class TestGetProvidersForType:
    """Tests for get_providers_for_type method."""

    def test_returns_providers_for_known_type(self, expansion_service):
        """Test that providers are returned for known type."""
        providers = expansion_service.get_providers_for_type("email_address")

        assert "contact" in providers
        assert "email" in providers

    def test_returns_empty_for_unknown_type(self, expansion_service):
        """Test that empty list returned for unknown type."""
        providers = expansion_service.get_providers_for_type("unknown_type")
        assert providers == []


class TestGetTypesForDomain:
    """Tests for get_types_for_domain method."""

    def test_returns_types_for_known_domain(self, expansion_service):
        """Test that types are returned for known domain."""
        types = expansion_service.get_types_for_domain("contact")

        assert "email_address" in types
        assert "physical_address" in types
        assert "phone_number" in types

    def test_returns_empty_for_unknown_domain(self, expansion_service):
        """Test that empty set returned for unknown domain."""
        types = expansion_service.get_types_for_domain("unknown_domain")
        assert types == set()


class TestValidateExpansionLogic:
    """Tests for validate_expansion_logic method."""

    def test_returns_valid_for_complete_registry(self, expansion_service):
        """Test validation returns valid for complete registry."""
        result = expansion_service.validate_expansion_logic()

        assert result["valid"] is True
        assert result["errors"] == []
        assert "registry_stats" in result

    def test_detects_missing_explicit_types(self):
        """Test validation detects missing explicit types."""
        # Create registry missing some explicit types
        registry = TypeRegistry()
        registry.register(SemanticType(name="Thing", category=TypeCategory.IDENTITY))

        service = SemanticExpansionService(registry=registry)
        result = service.validate_expansion_logic()

        # Should have errors for missing types
        assert result["valid"] is False
        assert len(result["errors"]) > 0


class TestExpandDomainsSemantic:
    """Tests for expand_domains_semantic method."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_domains(self, expansion_service):
        """Test that empty domains returns empty."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=[],
            required_semantic_types={"email_address"},
            threshold=0.5,
            query="test",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_original_for_empty_types(self, expansion_service):
        """Test that original domains returned for empty types."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=["email"],
            required_semantic_types=set(),
            threshold=0.5,
            query="test",
        )

        assert result == ["email"]

    @pytest.mark.asyncio
    async def test_expands_all_providers(self, expansion_service):
        """Test that all providers are added for semantic types."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=["route"],
            required_semantic_types={"physical_address"},
            threshold=0.5,
            query="test",
        )

        # physical_address is provided by contact, place, route
        assert "contact" in result
        assert "place" in result

    @pytest.mark.asyncio
    async def test_threshold_1_disables_expansion(self, expansion_service):
        """Test that threshold=1.0 disables expansion."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=["route"],
            required_semantic_types={"physical_address"},
            threshold=1.0,  # Disables expansion
            query="test",
        )

        assert result == ["route"]

    @pytest.mark.asyncio
    async def test_no_duplicate_domains(self, expansion_service):
        """Test that domains are not duplicated."""
        result = await expansion_service.expand_domains_semantic(
            primary_domains=["contact"],
            required_semantic_types={"email_address"},
            threshold=0.5,
            query="test",
        )

        # contact should appear only once even though it's a provider
        assert result.count("contact") == 1


class TestGetPrimaryTypeForDomain:
    """Tests for _get_primary_type_for_domain method."""

    def test_returns_person_name_for_contact(self, expansion_service):
        """Test that contact domain returns person_name."""
        result = expansion_service._get_primary_type_for_domain("contact")
        assert result == "person_name"

    def test_returns_message_id_for_email(self, expansion_service):
        """Test that email domain returns message_id."""
        result = expansion_service._get_primary_type_for_domain("email")
        assert result == "message_id"

    def test_returns_text_for_unknown_domain(self, expansion_service):
        """Test that unknown domain returns text."""
        result = expansion_service._get_primary_type_for_domain("unknown_domain")
        assert result == "text"


class TestGlobalExpansionService:
    """Tests for global service functions."""

    def setup_method(self):
        """Reset global service before each test."""
        reset_expansion_service()

    def teardown_method(self):
        """Reset global service after each test."""
        reset_expansion_service()

    @patch("src.domains.agents.semantic.expansion_service.get_registry")
    @patch("src.domains.agents.semantic.expansion_service.load_core_types")
    def test_get_expansion_service_returns_singleton(self, mock_load, mock_get_registry):
        """Test that get_expansion_service returns same instance."""
        mock_registry = MagicMock()
        mock_registry.__len__ = MagicMock(return_value=10)
        mock_get_registry.return_value = mock_registry

        service1 = get_expansion_service()
        service2 = get_expansion_service()

        assert service1 is service2

    @patch("src.domains.agents.semantic.expansion_service.get_registry")
    @patch("src.domains.agents.semantic.expansion_service.load_core_types")
    def test_reset_expansion_service_clears_singleton(self, mock_load, mock_get_registry):
        """Test that reset clears the global instance."""
        mock_registry = MagicMock()
        mock_registry.__len__ = MagicMock(return_value=10)
        mock_get_registry.return_value = mock_registry

        service1 = get_expansion_service()
        reset_expansion_service()
        service2 = get_expansion_service()

        assert service1 is not service2


class TestGetOutputPathsBySemanticType:
    """Tests for _get_output_paths_by_semantic_type helper."""

    def test_returns_list_type(self):
        """Test that function returns a list."""
        from src.domains.agents.semantic.expansion_service import (
            _get_output_paths_by_semantic_type,
        )

        # Call with domains that likely don't exist - should return empty list
        paths = _get_output_paths_by_semantic_type(
            "nonexistent_type",
            ["nonexistent_domain"],
            max_paths=2,
        )

        assert isinstance(paths, list)


class TestGenerateSemanticDependenciesForPrompt:
    """Tests for generate_semantic_dependencies_for_prompt helper."""

    def test_returns_string_type(self):
        """Test that function returns a string."""
        from src.domains.agents.semantic.expansion_service import (
            generate_semantic_dependencies_for_prompt,
        )

        # Call with empty domains
        result = generate_semantic_dependencies_for_prompt([])

        assert isinstance(result, str)


class TestGenerateJinja2Suggestions:
    """Tests for generate_jinja2_suggestions helper."""

    def test_returns_list_type(self):
        """Test that function returns a list."""
        from src.domains.agents.semantic.expansion_service import (
            generate_jinja2_suggestions,
        )

        # Call with non-existent tool
        suggestions = generate_jinja2_suggestions(
            target_tool="nonexistent_tool_xyz",
            target_param="param",
            available_step_ids=["step1"],
        )

        assert isinstance(suggestions, list)


class TestGenerateLinkingHintsForPlan:
    """Tests for generate_linking_hints_for_plan helper."""

    def test_returns_dict_type(self):
        """Test that function returns a dict."""
        from src.domains.agents.semantic.expansion_service import (
            generate_linking_hints_for_plan,
        )

        hints = generate_linking_hints_for_plan([])

        assert isinstance(hints, dict)

    def test_handles_empty_plan(self):
        """Test that empty plan returns empty dict."""
        from src.domains.agents.semantic.expansion_service import (
            generate_linking_hints_for_plan,
        )

        hints = generate_linking_hints_for_plan([])

        assert hints == {}
