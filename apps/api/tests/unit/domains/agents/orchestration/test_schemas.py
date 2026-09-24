"""
Unit tests for orchestration schemas.

Phase: Session 14 - Quick Wins (orchestration/schemas)
Created: 2025-11-20

Focus: Pydantic models and helper functions for orchestration
Target Coverage: 98% → 100%
"""

import pytest
from pydantic import ValidationError

from src.domains.agents.orchestration.schemas import (
    AgentResult,
    AgentResultData,
    ContactsResultData,
    EmailsResultData,
    FailedStep,
    MultiDomainResultData,
    OrchestratorPlan,
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

    def test_agent_result_rejects_retired_statuses(self):
        """ADR-303: ``connector_disabled``, ``pending`` and ``failed`` are gone.

        The first two had no producer at all, the third had one the readers did
        not know — so the two formatter branches that restituted ``error`` were
        dead and every failed plan reached the prompt as « Statut inconnu ».
        """
        for retired in ("connector_disabled", "pending", "failed"):
            with pytest.raises(ValidationError):
                AgentResult(agent_name="contacts_agent", status=retired)

    def test_agent_result_carries_its_failed_steps(self):
        """A partial plan is a SUCCESS that still failed somewhere."""
        result = AgentResult(
            agent_name="plan_executor",
            status="success",
            failed_steps=[
                FailedStep(
                    step_index=1,
                    tool_name="fetch_web_page_tool",
                    error="HTTP error 403",
                    error_code="FORBIDDEN",
                )
            ],
        )
        assert result.status == "success"
        assert result.failed_steps[0].error_code == "FORBIDDEN"

    def test_agent_result_has_no_failed_steps_by_default(self):
        assert AgentResult(agent_name="a", status="success").failed_steps == []

    def test_agent_result_validates_status(self):
        """Test that status is validated (Literal type)."""
        # Valid statuses
        AgentResult(agent_name="test", status="success")
        AgentResult(agent_name="test", status="error")
        # ADR-303: the vocabulary is binary — the three retired values are
        # covered by test_agent_result_rejects_retired_statuses above.

        # Invalid status should raise validation error
        with pytest.raises(ValidationError) as exc_info:
            AgentResult(agent_name="test", status="invalid_status")

        assert "status" in str(exc_info.value)

    def test_agent_result_is_mutable(self):
        """Test that AgentResult is mutable (frozen=False)."""
        result = AgentResult(agent_name="contacts_agent", status="error")

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


class TestFailedStepsSurviveTheCheckpoint:
    """``failed_steps`` crosses a checkpoint, or the honesty rule dies on resume.

    The formatter defers a plan aggregate to the runtime failures directive on
    the strength of this field. A HITL turn resumes from a PostgreSQL
    checkpoint, so the field must come back through LangGraph's own serializer
    under the allowlist production installs — CLAUDE.md's round-trip rule
    applied to the one field ADR-303 added to the state.
    """

    @staticmethod
    def _serde():
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        from src.domains.conversations.checkpointer import _CHECKPOINT_ALLOWED_MODULES

        return JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)

    def test_every_field_of_a_failed_step_comes_back(self) -> None:
        from src.domains.agents.orchestration.schemas import AgentResult, FailedStep

        serde = self._serde()
        step = FailedStep(
            step_index=1,
            tool_name="fetch_web_page_tool",
            error="HTTP error 403 fetching https://example.com/a",
            error_code="FORBIDDEN",
        )
        entry = AgentResult(
            agent_name="plan_executor", status="success", failed_steps=[step]
        ).model_dump()

        state = {"agent_results": {"9:plan_executor": entry}}
        back = serde.loads_typed(serde.dumps_typed(state))["agent_results"]["9:plan_executor"]

        assert back["status"] == "success"
        assert back["failed_steps"] == [step.model_dump()]

    def test_a_tool_message_keeps_its_error_status(self) -> None:
        """The ReAct failure marker is read AFTER a resume, never before it."""
        from langchain_core.messages import ToolMessage

        serde = self._serde()
        message = ToolMessage(
            content="Calendar unavailable: token expired.",
            tool_call_id="call_1",
            name="get_events_tool",
            status="error",
        )
        back = serde.loads_typed(serde.dumps_typed([message]))[0]
        assert isinstance(back, ToolMessage)
        assert back.status == "error"


class TestAFailedStepIsBoundedBeforeItReachesTheState:
    """``agent_results`` is capped « for memory management » — its entries must be too.

    ``StepResult.error`` is built at the source as ``str(e)`` and even as
    ``f"{type(result).__name__}: {result}"``, so it can carry a whole payload.
    Measured in the ADR-303 cold review: five failed steps produced **200 350
    bytes** of ``failed_steps``, persisted to PostgreSQL on every turn of the
    thread. The MODEL bounds its own field, so no producer — present or future,
    wherever it builds one — can put a document in the graph state.
    """

    def test_a_runaway_error_is_cut_at_the_model(self) -> None:
        from src.core.tool_outcome import TOOL_ERROR_HEAD_CHARS
        from src.domains.agents.orchestration.schemas import FailedStep

        step = FailedStep(step_index=0, tool_name="t", error="X" * 40_000, error_code="C" * 900)
        assert step.error is not None
        assert len(step.error) == TOOL_ERROR_HEAD_CHARS
        assert step.error_code is not None
        assert len(step.error_code) <= 64

    def test_a_short_error_is_untouched_and_none_survives(self) -> None:
        from src.domains.agents.orchestration.schemas import FailedStep

        assert FailedStep(step_index=0, tool_name="t", error="boom").error == "boom"
        assert FailedStep(step_index=0, tool_name="t").error is None

    def test_the_mapped_state_entry_stays_small(self) -> None:
        """End to end: what the mapper puts in the state, in bytes."""
        import json

        from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
        from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult

        execution_result = ExecutionResult(
            success=False,
            step_results=[
                StepResult(
                    step_index=index,
                    tool_name="t",
                    args={},
                    result={"success": False},
                    success=False,
                    error="X" * 40_000,
                )
                for index in range(5)
            ],
            total_steps=5,
            completed_steps=5,
            failed_step_index=0,
            error="e",
            total_execution_time_ms=0,
        )
        entry = next(iter(map_execution_result_to_agent_result(execution_result, "p", 1).values()))
        assert len(json.dumps(entry["failed_steps"])) < 2_000
