"""
Tests for TaskOrchestrator and orchestration logic.
"""

import pytest

from src.domains.agents.constants import make_agent_result_key
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration import (
    create_orchestration_plan,
    get_next_agent_from_plan,
    should_execute_agent,
)
from src.domains.agents.orchestration.schemas import AgentResult, OrchestratorPlan


@pytest.mark.asyncio
async def test_create_orchestration_plan_contacts_search():
    """Test orchestration plan creation for contacts search."""
    # Arrange
    router_output = RouterOutput(
        intention="contacts_search",
        confidence=0.9,
        context_label="contact",
        next_node="task_orchestrator",
        reasoning="User wants to search contacts",
    )

    state: MessagesState = {
        "messages": [],
        "metadata": {"user_id": "test-user", "session_id": "test-session", "run_id": "test-run"},
        "routing_history": [router_output],
        "agent_results": {},
        "orchestration_plan": None,
    }

    # Act
    plan = await create_orchestration_plan(router_output, state)

    # Assert
    assert isinstance(plan, OrchestratorPlan)
    assert plan.agents_to_call == ["contacts_agent"]
    assert plan.execution_mode == "sequential"
    assert plan.metadata["version"] == "v1_sequential"
    assert plan.metadata["intention"] == "contacts_search"
    assert plan.metadata["confidence"] == 0.9


@pytest.mark.asyncio
async def test_create_orchestration_plan_conversation():
    """Test orchestration plan for simple conversation (no agents)."""
    # Arrange
    router_output = RouterOutput(
        intention="conversation",
        confidence=0.95,
        context_label="general",
        next_node="response",
        reasoning="Simple greeting",
    )

    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [router_output],
        "agent_results": {},
        "orchestration_plan": None,
    }

    # Act
    plan = await create_orchestration_plan(router_output, state)

    # Assert
    assert plan.agents_to_call == []  # No agents for conversation
    assert plan.execution_mode == "sequential"


def test_get_next_agent_from_plan_first_agent():
    """Test getting first agent from plan."""
    # Arrange
    plan = OrchestratorPlan(
        agents_to_call=["contacts_agent", "emails_agent"],
        execution_mode="sequential",
        metadata={"version": "v1_sequential"},
    )

    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {},
        "orchestration_plan": plan,
    }

    # Act
    next_agent = get_next_agent_from_plan(state)

    # Assert
    assert next_agent == "contacts_agent"


def test_get_next_agent_from_plan_second_agent():
    """Test getting second agent after first executed."""
    # Arrange
    plan = OrchestratorPlan(
        agents_to_call=["contacts_agent", "emails_agent"],
        execution_mode="sequential",
        metadata={},
    )

    contacts_result: AgentResult = {
        "agent_name": "contacts_agent",
        "status": "success",
        "data": {"contacts": [], "total_count": 0},
        "error": None,
        "tokens_in": 100,
        "tokens_out": 200,
        "duration_ms": 500,
    }

    # Use composite key format: "turn_id:agent_name"
    turn_id = 0
    contacts_key = make_agent_result_key(turn_id, "contacts_agent")

    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {contacts_key: contacts_result},
        "orchestration_plan": plan,
        "current_turn_id": turn_id,
    }

    # Act
    next_agent = get_next_agent_from_plan(state)

    # Assert
    assert next_agent == "emails_agent"


def test_get_next_agent_from_plan_all_done():
    """Test getting next agent when all executed."""
    # Arrange
    plan = OrchestratorPlan(
        agents_to_call=["contacts_agent"],
        execution_mode="sequential",
        metadata={},
    )

    contacts_result: AgentResult = {
        "agent_name": "contacts_agent",
        "status": "success",
        "data": None,
        "error": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "duration_ms": 100,
    }

    # Use composite key format: "turn_id:agent_name"
    turn_id = 0
    contacts_key = make_agent_result_key(turn_id, "contacts_agent")

    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {contacts_key: contacts_result},
        "orchestration_plan": plan,
        "current_turn_id": turn_id,
    }

    # Act
    next_agent = get_next_agent_from_plan(state)

    # Assert
    assert next_agent is None  # All agents executed


def test_should_execute_agent_not_executed():
    """Test should execute agent when not yet executed."""
    # Arrange
    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {},
        "orchestration_plan": None,
    }

    # Act
    should_execute = should_execute_agent("contacts_agent", state)

    # Assert
    assert should_execute is True


def test_should_execute_agent_already_success():
    """Test should NOT execute agent when already succeeded."""
    # Arrange
    result: AgentResult = {
        "agent_name": "contacts_agent",
        "status": "success",
        "data": None,
        "error": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "duration_ms": 100,
    }

    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {"contacts_agent": result},
        "orchestration_plan": None,
    }

    # Act
    should_execute = should_execute_agent("contacts_agent", state)

    # Assert
    assert should_execute is False


def test_should_execute_agent_connector_disabled():
    """Test should NOT execute agent when connector disabled."""
    # Arrange
    result: AgentResult = {
        "agent_name": "contacts_agent",
        "status": "connector_disabled",
        "data": None,
        "error": "Connector not activated",
        "tokens_in": 0,
        "tokens_out": 0,
        "duration_ms": 50,
    }

    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {"contacts_agent": result},
        "orchestration_plan": None,
    }

    # Act
    should_execute = should_execute_agent("contacts_agent", state)

    # Assert
    assert should_execute is False  # Terminal state, don't retry


def test_should_execute_agent_error_state():
    """Test should execute agent when in error state (allows retry)."""
    # Arrange
    result: AgentResult = {
        "agent_name": "contacts_agent",
        "status": "error",
        "data": None,
        "error": "Network timeout",
        "tokens_in": 0,
        "tokens_out": 0,
        "duration_ms": 1000,
    }

    state: MessagesState = {
        "messages": [],
        "metadata": {},
        "routing_history": [],
        "agent_results": {"contacts_agent": result},
        "orchestration_plan": None,
    }

    # Act
    # Note: In V1, errors are not retried (agent skipped)
    # But should_execute_agent returns True to allow manual retry logic
    should_execute = should_execute_agent("contacts_agent", state)

    # Assert
    # Current implementation: error is terminal in V1, so False
    # Future V2: might implement retry logic
    assert should_execute is True  # Allows retry in future


# ==============================================================================
# Integration Tests (require database)
# ==============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_orchestration_flow_contacts(async_session):
    """
    Integration test: Full orchestration flow for contacts search.

    This test requires:
    - Database with test user
    - Google Contacts connector activated
    - Mock Google API responses

    Skipped in unit tests (requires @pytest.mark.integration).
    """
    pytest.skip("Integration test - requires full setup")


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def sample_router_output() -> RouterOutput:
    """Sample router output for testing."""
    return RouterOutput(
        intention="contacts_search",
        confidence=0.85,
        context_label="contact",
        next_node="task_orchestrator",
        reasoning="User wants to search contacts",
    )


@pytest.fixture
def sample_orchestration_plan() -> OrchestratorPlan:
    """Sample orchestration plan for testing."""
    return OrchestratorPlan(
        agents_to_call=["contacts_agent"],
        execution_mode="sequential",
        metadata={
            "version": "v1_sequential",
            "intention": "contacts_search",
            "confidence": 0.85,
        },
    )


@pytest.fixture
def sample_agent_result() -> AgentResult:
    """Sample agent result for testing."""
    return {
        "agent_name": "contacts_agent",
        "status": "success",
        "data": {"contacts": [{"name": "John Doe", "email": "john@example.com"}], "total_count": 1},
        "error": None,
        "tokens_in": 150,
        "tokens_out": 300,
        "duration_ms": 1250,
    }
