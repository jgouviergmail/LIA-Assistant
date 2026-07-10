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
        # Entity types (mirror the real ontology) — drive evidence-driven expansion
        SemanticType(
            name="Contact",
            parent="Thing",
            category=TypeCategory.IDENTITY,
            properties={
                "name": "person_name",
                "email": "email_address",
                "phone": "phone_number",
                "address": "physical_address",
            },
            source_domains=["contact"],
        ),
        SemanticType(
            name="CalendarEvent",
            parent="Thing",
            category=TypeCategory.TEMPORAL,
            properties={
                "location": "physical_address",
                "start_datetime": "event_start_datetime",
                "attendees": "email_address",
            },
            source_domains=["event"],
        ),
        SemanticType(
            name="Place",
            parent="Thing",
            category=TypeCategory.LOCATION,
            properties={
                "address": "physical_address",
                "phone": "phone_number",
                "coordinates": "coordinate",
            },
            source_domains=["place"],
        ),
        SemanticType(
            name="EmailMessage",
            parent="Thing",
            category=TypeCategory.CONTENT,
            properties={
                "sender": "email_address",
                "thread": "thread_id",
                "identifier": "message_id",
            },
            source_domains=["email"],
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


class TestExpandDomainsEvidenceDriven:
    """Tests for expand_domains_evidence_driven (replaces the never-wired
    threshold-based expand_domains_semantic)."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_domains(self, expansion_service):
        """Empty domains → nothing to expand."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=[],
            evidence_entities={"Contact"},
            required_semantic_types={"email_address"},
            max_added_domains=3,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_no_evidence_means_no_expansion(self, expansion_service):
        """Entity anchoring: without a referenced entity nothing is added —
        even when a required type has providers ('quel temps demain ?')."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["weather"],
            evidence_entities=set(),
            required_semantic_types={"physical_address"},
            max_added_domains=3,
        )
        assert result == ["weather"]

    @pytest.mark.asyncio
    async def test_person_evidence_adds_contact_like_iso_path(self, expansion_service):
        """Person evidence + physical_address required → contact only
        (identical outcome to the iso-functional path)."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["route"],
            evidence_entities={"Contact"},
            required_semantic_types={"physical_address"},
            max_added_domains=3,
        )
        assert result == ["route", "contact"]

    @pytest.mark.asyncio
    async def test_event_evidence_adds_calendar_domain(self, expansion_service):
        """'comment aller à ce rendez-vous ?' (event shown in a previous turn)
        → CalendarEvent provides physical_address (location) → event added."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["route"],
            evidence_entities={"CalendarEvent"},
            required_semantic_types={"physical_address"},
            max_added_domains=3,
        )
        assert result == ["route", "event"]

    @pytest.mark.asyncio
    async def test_place_evidence_adds_place_domain(self, expansion_service):
        """'comment aller au restaurant que tu m'as montré' (place shown in a
        previous turn) → Place provides physical_address → place added."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["route"],
            evidence_entities={"Place"},
            required_semantic_types={"physical_address"},
            max_added_domains=3,
        )
        assert result == ["route", "place"]

    @pytest.mark.asyncio
    async def test_email_evidence_adds_email_domain(self, expansion_service):
        """'invite l'expéditeur de ce mail à la réunion' (email shown in a
        previous turn) → EmailMessage provides email_address (sender) →
        email domain added so the plan can fetch the sender's address."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["event"],
            evidence_entities={"EmailMessage"},
            required_semantic_types={"email_address"},
            max_added_domains=3,
        )
        assert result == ["event", "email"]

    @pytest.mark.asyncio
    async def test_entity_without_matching_required_type_adds_nothing(self, expansion_service):
        """A referenced place does not help a plan whose required types are
        unrelated to what a Place provides (language_code)."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["wikipedia"],
            evidence_entities={"Place"},
            required_semantic_types={"language_code"},
            max_added_domains=3,
        )
        assert result == ["wikipedia"]

    @pytest.mark.asyncio
    async def test_cap_limits_added_domains(self, expansion_service):
        """The hard cap bounds catalogue growth deterministically."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["route"],
            evidence_entities={"Contact", "CalendarEvent", "Place"},
            required_semantic_types={"physical_address"},
            max_added_domains=1,
        )
        # Sorted entity order: CalendarEvent first → event wins the single slot.
        assert result == ["route", "event"]

    @pytest.mark.asyncio
    async def test_no_duplicate_domains(self, expansion_service):
        """A provider already selected is never duplicated."""
        result = await expansion_service.expand_domains_evidence_driven(
            domains=["contact"],
            evidence_entities={"Contact"},
            required_semantic_types={"email_address"},
            max_added_domains=3,
        )
        assert result.count("contact") == 1


class TestEvidenceEntityRegistry:
    """Boot-time completeness assert for the evidence entity mapping (ADR-085)."""

    def setup_method(self):
        reset_expansion_service()

    def teardown_method(self):
        reset_expansion_service()

    def test_real_ontology_passes_the_assert(self):
        """The shipped ontology must satisfy the evidence mapping (fail = boot refusal)."""
        from src.domains.agents.semantic.expansion_service import (
            assert_evidence_entity_types_complete,
        )

        assert_evidence_entity_types_complete()  # Must not raise

    def test_missing_entity_type_refuses_boot(self):
        """A mapping entry without an ontology counterpart raises RuntimeError."""
        from src.domains.agents.semantic import expansion_service as es

        with (
            patch.dict(
                es.EVIDENCE_ENTITY_TYPE_BY_DOMAIN,
                {"ghost": "GhostEntityType"},
            ),
            pytest.raises(RuntimeError, match="GhostEntityType"),
        ):
            es.assert_evidence_entity_types_complete()


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

    def test_manifest_param_consumers_union_into_output(self, monkeypatch):
        """Consumers declared by request manifests (parameter semantic_type)
        are unioned with the ontology's used_in_tools in the rendered lines."""
        from unittest.mock import MagicMock

        import src.core.context as ctx_mod
        from src.core.config import settings as real_settings
        from src.domains.agents.semantic.expansion_service import (
            generate_semantic_dependencies_for_prompt,
        )

        monkeypatch.setattr(real_settings, "semantic_linking_enabled", True, raising=False)

        param = MagicMock()
        param.semantic_type = "physical_address"
        manifest = MagicMock()
        manifest.name = "get_current_weather_tool"  # NOT in ontology used_in_tools
        manifest.parameters = [param]
        monkeypatch.setattr(ctx_mod, "get_request_tool_manifests", lambda: [manifest])

        result = generate_semantic_dependencies_for_prompt(
            ["contact"], include_jinja2_patterns=False
        )

        assert "physical_address" in result
        assert "get_current_weather_tool" in result

    def test_degrades_to_ontology_only_outside_request(self, monkeypatch):
        """Outside a request lifecycle (no manifests), the ontology links
        still render — historical behaviour preserved."""
        import src.core.context as ctx_mod
        from src.core.config import settings as real_settings
        from src.domains.agents.semantic.expansion_service import (
            generate_semantic_dependencies_for_prompt,
        )

        monkeypatch.setattr(real_settings, "semantic_linking_enabled", True, raising=False)
        monkeypatch.setattr(ctx_mod, "get_request_tool_manifests", lambda: [])

        result = generate_semantic_dependencies_for_prompt(
            ["contact"], include_jinja2_patterns=False
        )

        assert "physical_address" in result  # ontology used_in_tools still rendered


class TestCollectManifestParamConsumers:
    """Tests for collect_manifest_param_consumers helper."""

    def test_indexes_tools_by_param_semantic_type(self):
        from unittest.mock import MagicMock

        from src.domains.agents.semantic.expansion_service import (
            collect_manifest_param_consumers,
        )

        p1 = MagicMock()
        p1.semantic_type = "physical_address"
        p2 = MagicMock()
        p2.semantic_type = None  # untyped param ignored
        m1 = MagicMock()
        m1.name = "get_route_tool"
        m1.parameters = [p1, p2]
        m2 = MagicMock()
        m2.name = "get_places_tool"
        m2.parameters = [p1]

        result = collect_manifest_param_consumers([m1, m2])

        assert result == {"physical_address": {"get_route_tool", "get_places_tool"}}

    def test_handles_manifests_without_parameters(self):
        from unittest.mock import MagicMock

        from src.domains.agents.semantic.expansion_service import (
            collect_manifest_param_consumers,
        )

        m = MagicMock()
        m.parameters = None
        assert collect_manifest_param_consumers([m]) == {}
        assert collect_manifest_param_consumers([]) == {}


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
