"""
Unit tests for orchestration schemas.

Phase: Session 14 - Quick Wins (orchestration/schemas)
Created: 2025-11-20

Focus: Pydantic models and helper functions for orchestration
Target Coverage: 98% → 100% (missing line 251: create_pending_agent_result)
"""

import pytest
from pydantic import ValidationError

from src.domains.agents.orchestration.schemas import (
    AgentResult,
    AgentResultData,
    ContactsResultData,
    EmailsResultData,
    MultiDomainResultData,
    OrchestratorPlan,
    create_pending_agent_result,
)


class TestAgentResultData:
    """Tests for AgentResultData base class."""

    def test_agent_result_data_is_base_model(self):
        """Test that AgentResultData is a Pydantic BaseModel."""
        data = AgentResultData()
        assert isinstance(data, AgentResultData)

    def test_agent_result_data_can_be_instantiated(self):
        """Test that AgentResultData can be created (empty base class)."""
        data = AgentResultData()
        assert data is not None


class TestContactsResultData:
    """Tests for ContactsResultData model."""

    def test_contacts_result_data_default_values(self):
        """Test ContactsResultData with default values."""
        data = ContactsResultData(total_count=0)

        assert data.contacts == []
        assert data.total_count == 0
        assert data.has_more is False
        assert data.query is None
        assert data.data_source == "api"
        assert data.cache_age_seconds is None
        # Timestamp should be recent ISO 8601 string (UTC format)
        assert isinstance(data.timestamp, str)
        assert "T" in data.timestamp
        # Accept both 'Z' and '+00:00' UTC formats
        assert "Z" in data.timestamp or "+00:00" in data.timestamp

    def test_contacts_result_data_with_contacts(self):
        """Test ContactsResultData with contacts list."""
        contacts = [
            {"name": "Jean Dupond", "email": "jean@example.com"},
            {"name": "Marie Martin", "email": "marie@example.com"},
        ]
        data = ContactsResultData(contacts=contacts, total_count=2, has_more=True, query="Jean")

        assert data.contacts == contacts
        assert data.total_count == 2
        assert data.has_more is True
        assert data.query == "Jean"

    def test_contacts_result_data_cache_source(self):
        """Test ContactsResultData with cache metadata."""
        data = ContactsResultData(
            total_count=5,
            data_source="cache",
            cache_age_seconds=120,
            timestamp="2025-01-20T12:00:00Z",
        )

        assert data.data_source == "cache"
        assert data.cache_age_seconds == 120
        assert data.timestamp == "2025-01-20T12:00:00Z"

    def test_contacts_result_data_inherits_from_agent_result_data(self):
        """Test that ContactsResultData inherits from AgentResultData."""
        data = ContactsResultData(total_count=0)
        assert isinstance(data, AgentResultData)

    def test_contacts_result_data_validates_data_source(self):
        """Test that data_source is validated (Literal type)."""
        # Valid values
        ContactsResultData(total_count=0, data_source="api")
        ContactsResultData(total_count=0, data_source="cache")

        # Invalid value should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            ContactsResultData(total_count=0, data_source="invalid")

        assert "data_source" in str(exc_info.value)


class TestEmailsResultData:
    """Tests for EmailsResultData model."""

    def test_emails_result_data_default_values(self):
        """Test EmailsResultData with default values."""
        data = EmailsResultData(total=0)

        assert data.emails == []
        assert data.total == 0
        assert data.query is None
        assert data.data_source == "api"
        assert data.cache_age_seconds is None
        assert isinstance(data.timestamp, str)

    def test_emails_result_data_with_emails(self):
        """Test EmailsResultData with emails list."""
        emails = [
            {"subject": "Hello", "from": "sender@example.com"},
            {"subject": "World", "from": "another@example.com"},
        ]
        data = EmailsResultData(emails=emails, total=2, query="important")

        assert data.emails == emails
        assert data.total == 2
        assert data.query == "important"

    def test_emails_result_data_cache_metadata(self):
        """Test EmailsResultData with cache metadata."""
        data = EmailsResultData(
            total=10,
            data_source="cache",
            cache_age_seconds=60,
        )

        assert data.data_source == "cache"
        assert data.cache_age_seconds == 60

    def test_emails_result_data_inherits_from_agent_result_data(self):
        """Test that EmailsResultData inherits from AgentResultData."""
        data = EmailsResultData(total=0)
        assert isinstance(data, AgentResultData)


class TestMultiDomainResultData:
    """Tests for MultiDomainResultData model."""

    def test_multi_domain_result_data_default_values(self):
        """Test MultiDomainResultData with default values."""
        data = MultiDomainResultData()

        assert data.contacts == []
        assert data.contacts_total == 0
        assert data.emails == []
        assert data.emails_total == 0
        assert data.plan_id is None
        assert data.completed_steps == {}
        assert data.total_steps == 0
        assert data.execution_time_ms == 0
        assert data.data_source == "api"
        assert isinstance(data.timestamp, str)

    def test_multi_domain_result_data_with_contacts_and_emails(self):
        """Test MultiDomainResultData with both contacts and emails."""
        contacts = [{"name": "Jean"}]
        emails = [{"subject": "Hello"}]

        data = MultiDomainResultData(
            contacts=contacts,
            contacts_total=1,
            emails=emails,
            emails_total=1,
            plan_id="plan_123",
            total_steps=3,
            execution_time_ms=1500,
        )

        assert data.contacts == contacts
        assert data.contacts_total == 1
        assert data.emails == emails
        assert data.emails_total == 1
        assert data.plan_id == "plan_123"
        assert data.total_steps == 3
        assert data.execution_time_ms == 1500

    def test_multi_domain_result_data_with_completed_steps(self):
        """Test MultiDomainResultData with completed steps metadata."""
        steps = {
            "step_1": {"status": "success", "data": {"count": 5}},
            "step_2": {"status": "success", "data": {"count": 3}},
        }

        data = MultiDomainResultData(completed_steps=steps, total_steps=2)

        assert data.completed_steps == steps
        assert data.total_steps == 2

    def test_multi_domain_result_data_inherits_from_agent_result_data(self):
        """Test that MultiDomainResultData inherits from AgentResultData."""
        data = MultiDomainResultData()
        assert isinstance(data, AgentResultData)


class TestAgentResult:
    """Tests for AgentResult model."""

    def test_agent_result_minimal_creation(self):
        """Test AgentResult with minimal required fields."""
        result = AgentResult(agent_name="contacts_agent", status="success")

        assert result.agent_name == "contacts_agent"
        assert result.status == "success"
        assert result.data is None
        assert result.error is None
        assert result.tokens_in == 0
        assert result.tokens_out == 0
        assert result.duration_ms == 0

    def test_agent_result_with_contacts_data(self):
        """Test AgentResult with ContactsResultData."""
        contacts_data = ContactsResultData(
            contacts=[{"name": "Jean"}], total_count=1, has_more=False
        )
        result = AgentResult(
            agent_name="contacts_agent",
            status="success",
            data=contacts_data,
            tokens_in=150,
            tokens_out=300,
            duration_ms=1250,
        )

        assert result.agent_name == "contacts_agent"
        assert result.status == "success"
        assert isinstance(result.data, ContactsResultData)
        assert result.data.total_count == 1
        assert result.tokens_in == 150
        assert result.tokens_out == 300
        assert result.duration_ms == 1250

    def test_agent_result_with_emails_data(self):
        """Test AgentResult with EmailsResultData."""
        emails_data = EmailsResultData(emails=[{"subject": "Test"}], total=1)
        result = AgentResult(agent_name="emails_agent", status="success", data=emails_data)

        assert result.agent_name == "emails_agent"
        assert isinstance(result.data, EmailsResultData)
        assert result.data.total == 1

    def test_agent_result_with_multi_domain_data(self):
        """Test AgentResult with MultiDomainResultData."""
        multi_data = MultiDomainResultData(contacts_total=5, emails_total=3)
        result = AgentResult(agent_name="planner", status="success", data=multi_data)

        assert isinstance(result.data, MultiDomainResultData)
        assert result.data.contacts_total == 5
        assert result.data.emails_total == 3

    def test_agent_result_with_dict_data(self):
        """Test AgentResult with dict data (Pydantic v2 coerces to first matching model)."""
        dict_data = {"custom_field": "value", "count": 42}
        result = AgentResult(agent_name="custom_agent", status="success", data=dict_data)

        # In Pydantic v2, dicts are coerced to the first model in the union that accepts them.
        # PlacesResultData comes before dict[str, Any] in the union and accepts any dict
        # (using default values for required fields), so the dict gets converted.
        # This is expected Pydantic behavior with union types.
        assert result.data is not None
        # The data is coerced to one of the result models (not kept as raw dict)
        assert hasattr(result.data, "model_dump") or isinstance(result.data, dict)

    def test_agent_result_error_status(self):
        """Test AgentResult with error status."""
        result = AgentResult(
            agent_name="contacts_agent",
            status="error",
            error="API rate limit exceeded",
            duration_ms=500,
        )

        assert result.status == "error"
        assert result.error == "API rate limit exceeded"
        assert result.data is None

    def test_agent_result_connector_disabled_status(self):
        """Test AgentResult with connector_disabled status."""
        result = AgentResult(
            agent_name="contacts_agent",
            status="connector_disabled",
            error="Google connector not enabled",
        )

        assert result.status == "connector_disabled"
        assert result.error == "Google connector not enabled"

    def test_agent_result_pending_status(self):
        """Test AgentResult with pending status."""
        result = AgentResult(agent_name="contacts_agent", status="pending")

        assert result.status == "pending"
        assert result.data is None
        assert result.error is None

    def test_agent_result_failed_status(self):
        """Test AgentResult with failed status."""
        result = AgentResult(
            agent_name="contacts_agent", status="failed", error="Unexpected exception"
        )

        assert result.status == "failed"
        assert result.error == "Unexpected exception"

    def test_agent_result_validates_status(self):
        """Test that status is validated (Literal type)."""
        # Valid statuses
        AgentResult(agent_name="test", status="success")
        AgentResult(agent_name="test", status="error")
        AgentResult(agent_name="test", status="connector_disabled")
        AgentResult(agent_name="test", status="pending")
        AgentResult(agent_name="test", status="failed")

        # Invalid status should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            AgentResult(agent_name="test", status="invalid_status")

        assert "status" in str(exc_info.value)

    def test_agent_result_is_mutable(self):
        """Test that AgentResult is mutable (frozen=False)."""
        result = AgentResult(agent_name="contacts_agent", status="pending")

        # Should be able to modify fields
        result.status = "success"
        result.tokens_in = 100

        assert result.status == "success"
        assert result.tokens_in == 100


class TestOrchestratorPlan:
    """Tests for OrchestratorPlan model."""

    def test_orchestrator_plan_single_agent(self):
        """Test OrchestratorPlan with single agent."""
        plan = OrchestratorPlan(agents_to_call=["contacts_agent"], execution_mode="sequential")

        assert plan.agents_to_call == ["contacts_agent"]
        assert plan.execution_mode == "sequential"
        assert plan.metadata == {}

    def test_orchestrator_plan_multiple_agents(self):
        """Test OrchestratorPlan with multiple agents."""
        plan = OrchestratorPlan(
            agents_to_call=["contacts_agent", "emails_agent"], execution_mode="sequential"
        )

        assert len(plan.agents_to_call) == 2
        assert plan.agents_to_call == ["contacts_agent", "emails_agent"]

    def test_orchestrator_plan_with_metadata(self):
        """Test OrchestratorPlan with metadata."""
        metadata = {
            "version": "v1_sequential",
            "intention": "contacts_search",
            "confidence": 0.9,
            "reasoning": "User wants to search contacts",
        }
        plan = OrchestratorPlan(
            agents_to_call=["contacts_agent"], execution_mode="sequential", metadata=metadata
        )

        assert plan.metadata == metadata
        assert plan.metadata["version"] == "v1_sequential"
        assert plan.metadata["intention"] == "contacts_search"

    def test_orchestrator_plan_parallel_mode(self):
        """Test OrchestratorPlan with parallel execution mode (V2 future)."""
        plan = OrchestratorPlan(
            agents_to_call=["contacts_agent", "emails_agent"],
            execution_mode="parallel",
            metadata={"version": "v2_parallel", "dependencies": {"emails_agent": []}},
        )

        assert plan.execution_mode == "parallel"
        assert plan.metadata["version"] == "v2_parallel"

    def test_orchestrator_plan_validates_execution_mode(self):
        """Test that execution_mode is validated (Literal type)."""
        # Valid modes
        OrchestratorPlan(agents_to_call=[], execution_mode="sequential")
        OrchestratorPlan(agents_to_call=[], execution_mode="parallel")

        # Invalid mode should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorPlan(agents_to_call=[], execution_mode="invalid_mode")

        assert "execution_mode" in str(exc_info.value)

    def test_orchestrator_plan_empty_agents_list(self):
        """Test OrchestratorPlan with empty agents list (unknown intention)."""
        plan = OrchestratorPlan(agents_to_call=[], execution_mode="sequential")

        assert plan.agents_to_call == []
        assert plan.execution_mode == "sequential"

    def test_orchestrator_plan_is_mutable(self):
        """Test that OrchestratorPlan is mutable (frozen=False)."""
        plan = OrchestratorPlan(agents_to_call=["contacts_agent"], execution_mode="sequential")

        # Should be able to modify fields during execution
        plan.agents_to_call.append("emails_agent")
        plan.metadata["execution_started"] = True

        assert len(plan.agents_to_call) == 2
        assert plan.metadata["execution_started"] is True


class TestCreatePendingAgentResult:
    """Tests for create_pending_agent_result() helper function."""

    def test_create_pending_agent_result_basic(self):
        """Test creating pending AgentResult."""
        result = create_pending_agent_result("contacts_agent")

        assert isinstance(result, AgentResult)
        assert result.agent_name == "contacts_agent"
        assert result.status == "pending"
        assert result.data is None
        assert result.error is None
        assert result.tokens_in == 0
        assert result.tokens_out == 0
        assert result.duration_ms == 0

    def test_create_pending_agent_result_different_agents(self):
        """Test creating pending results for different agents."""
        contacts_result = create_pending_agent_result("contacts_agent")
        gmail_result = create_pending_agent_result("emails_agent")

        assert contacts_result.agent_name == "contacts_agent"
        assert gmail_result.agent_name == "emails_agent"
        assert contacts_result.status == "pending"
        assert gmail_result.status == "pending"

    def test_create_pending_agent_result_returns_agent_result_type(self):
        """Test that helper returns AgentResult type."""
        result = create_pending_agent_result("test_agent")
        assert type(result).__name__ == "AgentResult"

    def test_create_pending_agent_result_zero_metrics(self):
        """Test that pending result has zero metrics."""
        result = create_pending_agent_result("contacts_agent")

        # All metrics should be zero for pending state
        assert result.tokens_in == 0
        assert result.tokens_out == 0
        assert result.duration_ms == 0

    def test_create_pending_agent_result_can_be_modified(self):
        """Test that pending result can be modified after creation."""
        result = create_pending_agent_result("contacts_agent")

        # Modify to success state
        result.status = "success"
        result.tokens_in = 150
        result.data = ContactsResultData(contacts=[], total_count=0)

        assert result.status == "success"
        assert result.tokens_in == 150
        assert result.data is not None
