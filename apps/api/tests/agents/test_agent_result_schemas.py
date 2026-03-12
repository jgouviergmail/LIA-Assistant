"""
Unit tests for AgentResult Pydantic schemas.

Phase 3.2.5: Tests for AgentResult, AgentResultData, ContactsResultData.
Validates runtime validation after migration from TypedDict to BaseModel.
"""

import pytest
from pydantic import ValidationError

from src.domains.agents.orchestration.schemas import (
    AgentResult,
    AgentResultData,
    ContactsResultData,
    create_pending_agent_result,
)


class TestAgentResultData:
    """Tests for AgentResultData base class."""

    def test_create_empty_agent_result_data(self):
        """Test creating empty AgentResultData instance."""
        # When: Create empty instance
        data = AgentResultData()

        # Then: Valid instance
        assert isinstance(data, AgentResultData)

    def test_agent_result_data_is_extensible(self):
        """Test that AgentResultData can be inherited."""

        # Given: Custom subclass
        class CustomResultData(AgentResultData):
            custom_field: str = "test"

        # When: Create instance
        data = CustomResultData()

        # Then: Has custom field
        assert data.custom_field == "test"


class TestContactsResultData:
    """Tests for ContactsResultData schema."""

    def test_create_contacts_result_data_with_defaults(self):
        """Test creating ContactsResultData with only total_count."""
        # When: Create with minimal fields
        data = ContactsResultData(total_count=5)

        # Then: Defaults applied
        assert data.contacts == []
        assert data.total_count == 5
        assert data.has_more is False
        assert data.query is None
        assert data.data_source == "api"
        assert data.cache_age_seconds is None

    def test_create_contacts_result_data_with_all_fields(self):
        """Test creating ContactsResultData with all fields."""
        # Given: Full data
        contacts = [{"name": "Jean"}, {"name": "Marie"}]

        # When: Create instance
        data = ContactsResultData(
            contacts=contacts,
            total_count=2,
            has_more=False,
            query="Jean",
            data_source="cache",
            cache_age_seconds=120,
        )

        # Then: All fields set
        assert len(data.contacts) == 2
        assert data.contacts[0]["name"] == "Jean"
        assert data.total_count == 2
        assert data.has_more is False
        assert data.query == "Jean"
        assert data.data_source == "cache"
        assert data.cache_age_seconds == 120

    def test_contacts_result_data_validates_data_source_literal(self):
        """Test that data_source only accepts 'api' or 'cache'."""
        # When/Then: Invalid data_source raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            ContactsResultData(total_count=1, data_source="invalid")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("data_source",) for e in errors)


class TestAgentResult:
    """Tests for AgentResult schema."""

    def test_create_success_agent_result(self):
        """Test creating a successful AgentResult."""
        # Given: Success data
        data = ContactsResultData(contacts=[{"name": "Jean"}], total_count=1)

        # When: Create AgentResult
        result = AgentResult(
            agent_name="contacts_agent",
            status="success",
            data=data,
            tokens_in=100,
            tokens_out=200,
            duration_ms=500,
        )

        # Then: Valid result
        assert result.agent_name == "contacts_agent"
        assert result.status == "success"
        assert isinstance(result.data, ContactsResultData)
        assert result.data.total_count == 1
        assert result.error is None
        assert result.tokens_in == 100
        assert result.tokens_out == 200
        assert result.duration_ms == 500

    def test_create_error_agent_result(self):
        """Test creating an error AgentResult."""
        # When: Create error result
        result = AgentResult(
            agent_name="contacts_agent",
            status="error",
            error="Connection timeout",
            tokens_in=50,
            tokens_out=10,
            duration_ms=5000,
        )

        # Then: Error fields set
        assert result.status == "error"
        assert result.error == "Connection timeout"
        assert result.data is None

    def test_agent_result_with_dict_data(self):
        """Test AgentResult with dict data (not ContactsResultData)."""
        # Given: Generic dict data
        data = {"plan_id": "plan123", "completed_steps": 2}

        # When: Create result
        result = AgentResult(agent_name="plan_executor", status="success", data=data)

        # Then: Dict data preserved
        assert result.data == data
        assert result.data["plan_id"] == "plan123"

    def test_agent_result_validates_status_literal(self):
        """Test that status only accepts valid literals."""
        # When/Then: Invalid status raises ValidationError
        with pytest.raises(ValidationError) as exc_info:
            AgentResult(agent_name="test", status="invalid_status")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("status",) for e in errors)

    def test_agent_result_with_defaults(self):
        """Test AgentResult with default values for optional fields."""
        # When: Create with minimal fields
        result = AgentResult(agent_name="test_agent", status="pending")

        # Then: Defaults applied
        assert result.data is None
        assert result.error is None
        assert result.tokens_in == 0
        assert result.tokens_out == 0
        assert result.duration_ms == 0

    def test_agent_result_model_dump(self):
        """Test that model_dump() serializes correctly."""
        # Given: AgentResult instance with explicit ContactsResultData
        # Note: Pydantic v2 with Union types performs coercion, so we use a specific ResultData type
        from src.domains.agents.orchestration.schemas import ContactsResultData

        contacts_data = ContactsResultData(
            contacts=[{"name": "John", "email": "john@example.com"}],
            total_count=1,
            has_more=False,
        )
        result = AgentResult(
            agent_name="contacts_agent",
            status="success",
            data=contacts_data,
            tokens_in=100,
            tokens_out=200,
            duration_ms=500,
        )

        # When: Serialize to dict
        dumped = result.model_dump()

        # Then: All fields present
        assert dumped["agent_name"] == "contacts_agent"
        assert dumped["status"] == "success"
        # Data field contains ContactsResultData serialized form
        assert "contacts" in dumped["data"]
        assert "total_count" in dumped["data"]
        assert dumped["data"]["total_count"] == 1
        assert dumped["error"] is None
        assert dumped["tokens_in"] == 100
        assert dumped["tokens_out"] == 200
        assert dumped["duration_ms"] == 500

    def test_agent_result_model_dump_exclude_none(self):
        """Test model_dump with exclude_none=True."""
        # Given: AgentResult with None fields
        result = AgentResult(agent_name="test", status="pending")

        # When: Serialize excluding None
        dumped = result.model_dump(exclude_none=True)

        # Then: None fields excluded
        assert "data" not in dumped
        assert "error" not in dumped
        assert "agent_name" in dumped
        assert "status" in dumped

    def test_agent_result_allows_modification(self):
        """Test that AgentResult is not frozen (can be modified)."""
        # Given: AgentResult instance
        result = AgentResult(agent_name="test", status="pending")

        # When: Modify field (should not raise FrozenInstanceError)
        result.status = "success"
        result.data = {"result": "ok"}

        # Then: Modification successful
        assert result.status == "success"
        assert result.data == {"result": "ok"}


class TestCreatePendingAgentResult:
    """Tests for create_pending_agent_result helper function."""

    def test_create_pending_agent_result_returns_pending_status(self):
        """Test that helper creates pending result."""
        # When: Create pending result
        result = create_pending_agent_result("contacts_agent")

        # Then: Pending with zeros
        assert result.agent_name == "contacts_agent"
        assert result.status == "pending"
        assert result.data is None
        assert result.error is None
        assert result.tokens_in == 0
        assert result.tokens_out == 0
        assert result.duration_ms == 0

    def test_create_pending_agent_result_returns_agent_result_instance(self):
        """Test that helper returns AgentResult instance."""
        # When: Create pending result
        result = create_pending_agent_result("test_agent")

        # Then: Instance of AgentResult
        assert isinstance(result, AgentResult)


class TestAgentResultRoundTrip:
    """Tests for JSON serialization/deserialization round trips."""

    def test_agent_result_round_trip_with_contacts_data(self):
        """Test AgentResult survives JSON round trip with ContactsResultData."""
        # Given: AgentResult with ContactsResultData
        original = AgentResult(
            agent_name="contacts_agent",
            status="success",
            data=ContactsResultData(contacts=[{"name": "Jean"}], total_count=1, query="Jean"),
            tokens_in=100,
            tokens_out=200,
            duration_ms=500,
        )

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        restored = AgentResult.model_validate_json(json_str)

        # Then: Same data (Pydantic correctly reconstructs ContactsResultData!)
        assert restored.agent_name == original.agent_name
        assert restored.status == original.status
        assert restored.tokens_in == original.tokens_in
        # Pydantic smart deserialization: ContactsResultData is reconstructed
        assert isinstance(restored.data, ContactsResultData)
        assert restored.data.total_count == 1
        assert restored.data.query == "Jean"

    def test_agent_result_round_trip_with_dict_data(self):
        """Test AgentResult survives JSON round trip with dict data."""
        # Given: AgentResult with dict data
        original = AgentResult(
            agent_name="plan_executor",
            status="success",
            data={"plan_id": "plan123", "completed_steps": 2},
        )

        # When: Serialize and deserialize
        json_str = original.model_dump_json()
        restored = AgentResult.model_validate_json(json_str)

        # Then: Same data
        assert restored.agent_name == original.agent_name
        assert restored.status == original.status
        assert restored.data == original.data
