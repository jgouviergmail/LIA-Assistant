"""
Unit tests for entity resolution service.

Tests for EntityResolutionService that handles automatic entity resolution
with disambiguation for contact references.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.context.entity_resolution import (
    ACTION_TO_FIELD_MAPPING,
    DisambiguationContext,
    DisambiguationType,
    EntityResolutionService,
    ResolutionStatus,
    ResolvedEntity,
    get_entity_resolution_service,
)


class TestResolutionStatus:
    """Tests for ResolutionStatus enum."""

    def test_resolved_status_exists(self):
        """Test that RESOLVED status exists."""
        assert ResolutionStatus.RESOLVED.value == "resolved"

    def test_disambiguation_needed_status_exists(self):
        """Test that DISAMBIGUATION_NEEDED status exists."""
        assert ResolutionStatus.DISAMBIGUATION_NEEDED.value == "disambiguation_needed"

    def test_not_found_status_exists(self):
        """Test that NOT_FOUND status exists."""
        assert ResolutionStatus.NOT_FOUND.value == "not_found"

    def test_no_target_field_status_exists(self):
        """Test that NO_TARGET_FIELD status exists."""
        assert ResolutionStatus.NO_TARGET_FIELD.value == "no_target_field"

    def test_error_status_exists(self):
        """Test that ERROR status exists."""
        assert ResolutionStatus.ERROR.value == "error"


class TestDisambiguationType:
    """Tests for DisambiguationType enum."""

    def test_multiple_entities_type_exists(self):
        """Test that MULTIPLE_ENTITIES type exists."""
        assert DisambiguationType.MULTIPLE_ENTITIES.value == "multiple_entities"

    def test_multiple_fields_type_exists(self):
        """Test that MULTIPLE_FIELDS type exists."""
        assert DisambiguationType.MULTIPLE_FIELDS.value == "multiple_fields"


class TestResolvedEntity:
    """Tests for ResolvedEntity dataclass."""

    def test_create_minimal_entity(self):
        """Test creating entity with minimal fields."""
        entity = ResolvedEntity(status=ResolutionStatus.RESOLVED)

        assert entity.status == ResolutionStatus.RESOLVED
        assert entity.resolved_value is None
        assert entity.resolved_item is None
        assert entity.disambiguation_context is None
        assert entity.error_message is None
        assert entity.confidence == 0.0

    def test_create_resolved_entity(self):
        """Test creating resolved entity with value."""
        entity = ResolvedEntity(
            status=ResolutionStatus.RESOLVED,
            resolved_value="jean@example.com",
            resolved_item={"name": "Jean", "email": "jean@example.com"},
            confidence=1.0,
        )

        assert entity.resolved_value == "jean@example.com"
        assert entity.resolved_item["name"] == "Jean"
        assert entity.confidence == 1.0

    def test_create_error_entity(self):
        """Test creating entity with error."""
        entity = ResolvedEntity(
            status=ResolutionStatus.ERROR,
            error_message="Test error message",
        )

        assert entity.status == ResolutionStatus.ERROR
        assert entity.error_message == "Test error message"


class TestDisambiguationContext:
    """Tests for DisambiguationContext dataclass."""

    def test_create_minimal_context(self):
        """Test creating context with minimal fields."""
        context = DisambiguationContext(
            disambiguation_type=DisambiguationType.MULTIPLE_ENTITIES,
            domain="contacts",
            original_query="Jean",
            intended_action="send_email",
            target_field="email",
        )

        assert context.disambiguation_type == DisambiguationType.MULTIPLE_ENTITIES
        assert context.domain == "contacts"
        assert context.candidates == []
        assert context.registry_ids == []

    def test_to_dict_serialization(self):
        """Test that to_dict serializes correctly."""
        context = DisambiguationContext(
            disambiguation_type=DisambiguationType.MULTIPLE_FIELDS,
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="send_email",
            target_field="email",
            candidates=[{"index": 1, "value": "jean@work.com"}],
            registry_ids=["contact_123"],
        )

        result = context.to_dict()

        assert result["disambiguation_type"] == "multiple_fields"
        assert result["domain"] == "contacts"
        assert result["original_query"] == "Jean Dupont"
        assert result["intended_action"] == "send_email"
        assert result["target_field"] == "email"
        assert len(result["candidates"]) == 1
        assert result["registry_ids"] == ["contact_123"]


class TestActionToFieldMapping:
    """Tests for ACTION_TO_FIELD_MAPPING constant."""

    def test_send_email_requires_email(self):
        """Test that send_email maps to email fields."""
        fields = ACTION_TO_FIELD_MAPPING["send_email"]
        assert "email" in fields or "emails" in fields

    def test_call_requires_phone(self):
        """Test that call maps to phone fields."""
        fields = ACTION_TO_FIELD_MAPPING["call"]
        assert "phone" in fields or "phones" in fields

    def test_default_action_exists(self):
        """Test that default action mapping exists."""
        assert "default" in ACTION_TO_FIELD_MAPPING

    def test_create_event_requires_email(self):
        """Test that create_event maps to email for invitations."""
        fields = ACTION_TO_FIELD_MAPPING["create_event"]
        assert "email" in fields or "emails" in fields


class TestEntityResolutionServiceGetTargetFields:
    """Tests for _get_target_fields method."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return EntityResolutionService()

    def test_returns_override_when_provided(self, service):
        """Test that override takes precedence."""
        result = service._get_target_fields("send_email", override="custom_field")
        assert result == ["custom_field"]

    def test_returns_mapped_fields_for_action(self, service):
        """Test that mapped fields returned for known action."""
        result = service._get_target_fields("send_email")
        assert "email" in result or "emails" in result

    def test_returns_default_for_unknown_action(self, service):
        """Test that default fields returned for unknown action."""
        result = service._get_target_fields("unknown_action")
        assert result == ACTION_TO_FIELD_MAPPING["default"]

    def test_normalizes_tool_suffix(self, service):
        """Test that _tool suffix is removed."""
        result = service._get_target_fields("send_email_tool")
        assert "email" in result or "emails" in result


class TestEntityResolutionServiceExtractValue:
    """Tests for _extract_value method."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return EntityResolutionService()

    def test_extracts_plain_string(self, service):
        """Test extracting plain string value."""
        result = service._extract_value("jean@example.com")
        assert result == "jean@example.com"

    def test_extracts_from_dict_with_value_key(self, service):
        """Test extracting from dict with 'value' key."""
        result = service._extract_value({"value": "jean@example.com", "type": "work"})
        assert result == "jean@example.com"

    def test_extracts_from_dict_with_email_key(self, service):
        """Test extracting from dict with 'email' key."""
        result = service._extract_value({"email": "jean@example.com"})
        assert result == "jean@example.com"

    def test_extracts_from_dict_with_phone_key(self, service):
        """Test extracting from dict with 'phone' key."""
        result = service._extract_value({"phone": "+33612345678"})
        assert result == "+33612345678"

    def test_fallback_to_first_string_value(self, service):
        """Test fallback to first non-type string value."""
        result = service._extract_value({"type": "work", "custom": "value123"})
        assert result == "value123"

    def test_converts_other_types_to_string(self, service):
        """Test that other types are converted to string."""
        result = service._extract_value(12345)
        assert result == "12345"


class TestEntityResolutionServiceResolveForAction:
    """Tests for resolve_for_action method."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return EntityResolutionService()

    def test_returns_not_found_for_empty_items(self, service):
        """Test that NOT_FOUND returned for empty items."""
        result = service.resolve_for_action(
            items=[],
            domain="contacts",
            original_query="Jean",
            intended_action="send_email",
        )

        assert result.status == ResolutionStatus.NOT_FOUND
        assert result.error_message is not None

    def test_resolves_single_item_with_single_email(self, service):
        """Test resolution of single item with single email."""
        result = service.resolve_for_action(
            items=[{"name": "Jean Dupont", "email": "jean@example.com"}],
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="send_email",
        )

        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_value == "jean@example.com"
        assert result.confidence == 1.0

    def test_resolves_single_item_with_email_list_single_value(self, service):
        """Test resolution of single item with single-element email list."""
        result = service.resolve_for_action(
            items=[{"name": "Jean Dupont", "emails": ["jean@example.com"]}],
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="send_email",
        )

        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_value == "jean@example.com"

    def test_disambiguation_for_multiple_emails(self, service):
        """Test disambiguation needed for multiple emails."""
        result = service.resolve_for_action(
            items=[
                {
                    "name": "Jean Dupont",
                    "emails": ["jean@work.com", "jean@home.com"],
                    "resource_name": "contact_123",
                }
            ],
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="send_email",
        )

        assert result.status == ResolutionStatus.DISAMBIGUATION_NEEDED
        assert result.disambiguation_context is not None
        assert result.disambiguation_context["disambiguation_type"] == "multiple_fields"
        assert len(result.disambiguation_context["candidates"]) == 2

    @patch("src.domains.agents.context.entity_resolution.ContextTypeRegistry")
    def test_disambiguation_for_multiple_items(self, mock_registry, service):
        """Test disambiguation needed for multiple matching items."""
        # Mock the registry definition
        mock_definition = MagicMock()
        mock_definition.display_name_field = "name"
        mock_definition.primary_id_field = "resource_name"
        mock_registry.get_definition.return_value = mock_definition

        result = service.resolve_for_action(
            items=[
                {"name": "Jean Dupont", "email": "jean.d@example.com", "resource_name": "c1"},
                {"name": "Jean Martin", "email": "jean.m@example.com", "resource_name": "c2"},
            ],
            domain="contacts",
            original_query="Jean",
            intended_action="send_email",
        )

        assert result.status == ResolutionStatus.DISAMBIGUATION_NEEDED
        assert result.disambiguation_context is not None
        assert result.disambiguation_context["disambiguation_type"] == "multiple_entities"
        assert len(result.disambiguation_context["candidates"]) == 2

    def test_no_target_field_found(self, service):
        """Test NO_TARGET_FIELD when entity lacks required field."""
        result = service.resolve_for_action(
            items=[{"name": "Jean Dupont", "phone": "+33612345678"}],
            domain="contacts",
            original_query="Jean Dupont",
            intended_action="send_email",  # Needs email, not phone
        )

        assert result.status == ResolutionStatus.NO_TARGET_FIELD
        assert result.resolved_item is not None

    def test_target_field_override(self, service):
        """Test that target_field_override is respected."""
        result = service.resolve_for_action(
            items=[{"name": "Jean", "phone": "+33612345678", "custom": "value"}],
            domain="contacts",
            original_query="Jean",
            intended_action="send_email",
            target_field_override="custom",
        )

        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_value == "value"


class TestEntityResolutionServiceResolveUserChoice:
    """Tests for resolve_user_choice method."""

    @pytest.fixture
    def service(self):
        """Create service instance."""
        return EntityResolutionService()

    def test_resolves_numeric_choice(self, service):
        """Test resolving numeric choice."""
        context = {
            "disambiguation_type": "multiple_fields",
            "candidates": [
                {"index": 1, "value": "jean@work.com"},
                {"index": 2, "value": "jean@home.com"},
            ],
        }

        result = service.resolve_user_choice(
            choice=1,
            disambiguation_context=context,
            items=[],
        )

        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_value == "jean@work.com"

    def test_resolves_string_numeric_choice(self, service):
        """Test resolving string numeric choice."""
        context = {
            "disambiguation_type": "multiple_fields",
            "candidates": [
                {"index": 1, "value": "jean@work.com"},
                {"index": 2, "value": "jean@home.com"},
            ],
        }

        result = service.resolve_user_choice(
            choice="2",
            disambiguation_context=context,
            items=[],
        )

        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_value == "jean@home.com"

    def test_returns_error_for_invalid_choice(self, service):
        """Test error returned for non-numeric choice."""
        context = {
            "disambiguation_type": "multiple_fields",
            "candidates": [{"index": 1, "value": "email"}],
        }

        result = service.resolve_user_choice(
            choice="invalid",
            disambiguation_context=context,
            items=[],
        )

        assert result.status == ResolutionStatus.ERROR

    def test_returns_error_for_out_of_range_choice(self, service):
        """Test error returned for out of range choice."""
        context = {
            "disambiguation_type": "multiple_fields",
            "candidates": [{"index": 1, "value": "email"}],
        }

        result = service.resolve_user_choice(
            choice=5,
            disambiguation_context=context,
            items=[],
        )

        assert result.status == ResolutionStatus.ERROR

    def test_resolves_multiple_entities_choice(self, service):
        """Test resolving multiple entities choice."""
        context = {
            "disambiguation_type": "multiple_entities",
            "candidates": [
                {"index": 1, "name": "Jean D", "email": "jean.d@example.com", "id": "c1"},
                {"index": 2, "name": "Jean M", "email": "jean.m@example.com", "id": "c2"},
            ],
        }
        items = [
            {"name": "Jean D", "email": "jean.d@example.com", "id": "c1"},
            {"name": "Jean M", "email": "jean.m@example.com", "id": "c2"},
        ]

        result = service.resolve_user_choice(
            choice=2,
            disambiguation_context=context,
            items=items,
        )

        assert result.status == ResolutionStatus.RESOLVED
        assert result.resolved_value == "jean.m@example.com"


class TestGetEntityResolutionService:
    """Tests for singleton accessor function."""

    def test_returns_service_instance(self):
        """Test that function returns service instance."""
        service = get_entity_resolution_service()

        assert isinstance(service, EntityResolutionService)

    def test_returns_same_instance(self):
        """Test that function returns same instance (singleton)."""
        service1 = get_entity_resolution_service()
        service2 = get_entity_resolution_service()

        assert service1 is service2
