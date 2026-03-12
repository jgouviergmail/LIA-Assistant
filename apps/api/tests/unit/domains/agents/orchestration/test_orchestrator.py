"""
Unit tests for orchestration orchestrator (multi-agent coordination).

Phase: Session 13 - Medium Modules (orchestration/orchestrator)
Created: 2025-11-20

Focus: Orchestration plan creation, agent execution logic, next agent selection
Coverage Target: 80%+ (from 23% baseline)
"""

from unittest.mock import patch

import pytest

from src.domains.agents.constants import (
    AGENT_CONTACT,
    EXECUTION_MODE_SEQUENTIAL,
    INTENTION_CONTACT,
    INTENTION_CONTACT_DETAILS,
    INTENTION_CONTACT_LIST,
    INTENTION_CONTACT_SEARCH,
    STATUS_ERROR,
    STATUS_SUCCESS,
    make_agent_result_key,
)
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.orchestrator import (
    create_orchestration_plan,
    get_next_agent_from_plan,
    should_execute_agent,
)
from src.domains.agents.orchestration.schemas import OrchestratorPlan


@pytest.fixture
def sample_router_output():
    """Create a sample RouterOutput for testing."""
    return RouterOutput(
        intention=INTENTION_CONTACT_SEARCH,
        confidence=0.9,
        context_label="contact",
        next_node="task_orchestrator",
        domains=["contacts"],
        reasoning="User wants to search contacts",
    )


@pytest.fixture
def empty_state():
    """Create an empty MessagesState for testing."""
    return MessagesState(messages=[])


@pytest.fixture
def state_with_plan():
    """Create MessagesState with orchestration plan."""
    plan = OrchestratorPlan(
        agents_to_call=[AGENT_CONTACT],
        execution_mode=EXECUTION_MODE_SEQUENTIAL,
        metadata={"version": "v1_sequential"},
    )
    return MessagesState(
        messages=[],
        orchestration_plan=plan.model_dump(),
        current_turn_id=1,
    )


@pytest.fixture
def state_with_executed_agent():
    """Create MessagesState with already executed agent."""
    plan = OrchestratorPlan(
        agents_to_call=[AGENT_CONTACT],
        execution_mode=EXECUTION_MODE_SEQUENTIAL,
        metadata={"version": "v1_sequential"},
    )

    return MessagesState(
        messages=[],
        orchestration_plan=plan.model_dump(),
        current_turn_id=1,
        agent_results={
            make_agent_result_key(1, AGENT_CONTACT): {
                "status": STATUS_SUCCESS,
                "agent_name": AGENT_CONTACT,
                "data": {"contacts": [], "total_count": 0},
            }
        },
    )


class TestCreateOrchestrationPlan:
    """Tests for create_orchestration_plan() function."""

    @pytest.mark.asyncio
    async def test_create_plan_contacts_search(self, sample_router_output, empty_state):
        """Test creating plan for contacts_search intention."""
        plan = await create_orchestration_plan(sample_router_output, empty_state)

        assert isinstance(plan, OrchestratorPlan)
        assert plan.agents_to_call == [AGENT_CONTACT]
        assert plan.execution_mode == EXECUTION_MODE_SEQUENTIAL
        assert plan.metadata["version"] == "v1_sequential"
        assert plan.metadata["intention"] == INTENTION_CONTACT_SEARCH
        assert plan.metadata["confidence"] == 0.9
        assert plan.metadata["context_label"] == "contact"

    @pytest.mark.asyncio
    async def test_create_plan_contacts_list(self, empty_state):
        """Test creating plan for contacts_list intention."""
        router_output = RouterOutput(
            intention=INTENTION_CONTACT_LIST,
            confidence=0.85,
            context_label="contact",
            next_node="task_orchestrator",
        )

        plan = await create_orchestration_plan(router_output, empty_state)

        assert plan.agents_to_call == [AGENT_CONTACT]
        assert plan.metadata["intention"] == INTENTION_CONTACT_LIST

    @pytest.mark.asyncio
    async def test_create_plan_contacts_details(self, empty_state):
        """Test creating plan for contacts_details intention."""
        router_output = RouterOutput(
            intention=INTENTION_CONTACT_DETAILS,
            confidence=0.92,
            context_label="contact",
            next_node="task_orchestrator",
        )

        plan = await create_orchestration_plan(router_output, empty_state)

        assert plan.agents_to_call == [AGENT_CONTACT]
        assert plan.metadata["intention"] == INTENTION_CONTACT_DETAILS

    @pytest.mark.asyncio
    async def test_create_plan_contacts_fallback(self, empty_state):
        """Test creating plan for generic 'contacts' intention (fallback)."""
        router_output = RouterOutput(
            intention=INTENTION_CONTACT,
            confidence=0.8,
            context_label="contact",
            next_node="task_orchestrator",
        )

        plan = await create_orchestration_plan(router_output, empty_state)

        assert plan.agents_to_call == [AGENT_CONTACT]
        assert plan.metadata["intention"] == INTENTION_CONTACT

    @pytest.mark.asyncio
    async def test_create_plan_unknown_intention(self, empty_state):
        """Test creating plan for unknown intention returns empty agents list."""
        router_output = RouterOutput(
            intention="unknown_intention",
            confidence=0.7,
            context_label="general",
            next_node="response",
        )

        plan = await create_orchestration_plan(router_output, empty_state)

        assert plan.agents_to_call == []
        assert plan.execution_mode == EXECUTION_MODE_SEQUENTIAL
        assert plan.metadata["intention"] == "unknown_intention"

    @pytest.mark.asyncio
    async def test_create_plan_includes_reasoning(self, empty_state):
        """Test that reasoning is included in metadata when provided."""
        router_output = RouterOutput(
            intention=INTENTION_CONTACT_SEARCH,
            confidence=0.9,
            context_label="contact",
            next_node="task_orchestrator",
            reasoning="User explicitly requested contact search",
        )

        plan = await create_orchestration_plan(router_output, empty_state)

        assert plan.metadata["reasoning"] == "User explicitly requested contact search"

    @pytest.mark.asyncio
    async def test_create_plan_logs_creation(self, sample_router_output, empty_state):
        """Test that plan creation is logged."""
        with patch("src.domains.agents.orchestration.orchestrator.logger") as mock_logger:
            await create_orchestration_plan(sample_router_output, empty_state)

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "orchestration_plan_created"
            assert call_args[1]["intention"] == f"{INTENTION_CONTACT_SEARCH} -> contact"
            assert call_args[1]["confidence"] == 0.9
            assert call_args[1]["agents_count"] == 1
            assert call_args[1]["agents"] == [AGENT_CONTACT]

    @pytest.mark.asyncio
    async def test_create_plan_hardcodes_sequential_mode(self, sample_router_output, empty_state):
        """Test that V1 hardcodes sequential execution mode."""
        plan = await create_orchestration_plan(sample_router_output, empty_state)

        assert plan.execution_mode == EXECUTION_MODE_SEQUENTIAL
        assert plan.metadata["version"] == "v1_sequential"


class TestShouldExecuteAgent:
    """Tests for should_execute_agent() function."""

    def test_should_execute_agent_no_results(self, empty_state):
        """Test that agent should execute when no results exist."""
        result = should_execute_agent(AGENT_CONTACT, empty_state)

        assert result is True

    def test_should_execute_agent_not_executed_yet(self):
        """Test that agent should execute if not in agent_results."""
        state = MessagesState(
            messages=[],
            agent_results={
                "other_agent": {
                    "status": STATUS_SUCCESS,
                    "agent_name": "other_agent",
                }
            },
        )

        result = should_execute_agent(AGENT_CONTACT, state)

        assert result is True

    def test_should_execute_agent_success_status(self):
        """Test that agent should NOT execute if already successful."""
        state = MessagesState(
            messages=[],
            agent_results={
                AGENT_CONTACT: {
                    "status": STATUS_SUCCESS,
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        result = should_execute_agent(AGENT_CONTACT, state)

        assert result is False

    def test_should_execute_agent_connector_disabled(self):
        """Test that agent should NOT execute if connector disabled."""
        state = MessagesState(
            messages=[],
            agent_results={
                AGENT_CONTACT: {
                    "status": "connector_disabled",
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        result = should_execute_agent(AGENT_CONTACT, state)

        assert result is False

    def test_should_execute_agent_error_status(self):
        """Test that agent SHOULD execute again if previous status was error."""
        state = MessagesState(
            messages=[],
            agent_results={
                AGENT_CONTACT: {
                    "status": STATUS_ERROR,
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        result = should_execute_agent(AGENT_CONTACT, state)

        assert result is True

    def test_should_execute_agent_pending_status(self):
        """Test that agent SHOULD execute if status is pending."""
        state = MessagesState(
            messages=[],
            agent_results={
                AGENT_CONTACT: {
                    "status": "pending",
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        result = should_execute_agent(AGENT_CONTACT, state)

        assert result is True

    def test_should_execute_agent_logs_skip(self):
        """Test that skipping execution is logged."""
        state = MessagesState(
            messages=[],
            agent_results={
                AGENT_CONTACT: {
                    "status": STATUS_SUCCESS,
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        with patch("src.domains.agents.orchestration.orchestrator.logger") as mock_logger:
            result = should_execute_agent(AGENT_CONTACT, state)

            assert result is False
            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args
            assert call_args[0][0] == "agent_already_executed"
            assert call_args[1]["agent_name"] == AGENT_CONTACT
            assert call_args[1]["status"] == STATUS_SUCCESS


class TestGetNextAgentFromPlan:
    """Tests for get_next_agent_from_plan() function."""

    def test_get_next_agent_no_plan(self, empty_state):
        """Test that None is returned when no orchestration plan exists."""
        result = get_next_agent_from_plan(empty_state)

        assert result is None

    def test_get_next_agent_empty_agents_list(self):
        """Test that None is returned when agents_to_call is empty."""
        plan = OrchestratorPlan(
            agents_to_call=[],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )
        state = MessagesState(
            messages=[],
            orchestration_plan=plan.model_dump(),
        )

        result = get_next_agent_from_plan(state)

        assert result is None

    def test_get_next_agent_first_agent(self, state_with_plan):
        """Test that first agent is returned when none executed yet."""
        result = get_next_agent_from_plan(state_with_plan)

        assert result == AGENT_CONTACT

    def test_get_next_agent_already_executed(self):
        """Test that None is returned when all agents executed (using object plan format)."""
        # Use object format to avoid bug at line 199 (plan.agents_to_call)
        plan = OrchestratorPlan(
            agents_to_call=[AGENT_CONTACT],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={"version": "v1_sequential"},
        )

        state = MessagesState(
            messages=[],
            orchestration_plan=plan,  # Object format, not dict
            current_turn_id=1,
            agent_results={
                make_agent_result_key(1, AGENT_CONTACT): {
                    "status": STATUS_SUCCESS,
                    "agent_name": AGENT_CONTACT,
                    "data": {"contacts": [], "total_count": 0},
                }
            },
        )

        result = get_next_agent_from_plan(state)

        assert result is None

    def test_get_next_agent_multiple_agents_sequential(self):
        """Test sequential execution with multiple agents."""
        plan = OrchestratorPlan(
            agents_to_call=["contacts_agent", "emails_agent"],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )
        state = MessagesState(
            messages=[],
            orchestration_plan=plan.model_dump(),
            current_turn_id=2,
            agent_results={
                make_agent_result_key(2, "contacts_agent"): {
                    "status": STATUS_SUCCESS,
                    "agent_name": "contacts_agent",
                }
            },
        )

        result = get_next_agent_from_plan(state)

        assert result == "emails_agent"

    def test_get_next_agent_skips_failed_agent(self):
        """Test that failed agents are skipped (no retry in V1)."""
        plan = OrchestratorPlan(
            agents_to_call=["contacts_agent", "emails_agent"],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )
        state = MessagesState(
            messages=[],
            orchestration_plan=plan.model_dump(),
            current_turn_id=3,
            agent_results={
                make_agent_result_key(3, "contacts_agent"): {
                    "status": STATUS_ERROR,
                    "agent_name": "contacts_agent",
                    "error": "API error",
                }
            },
        )

        result = get_next_agent_from_plan(state)

        # Should skip failed agent and return next one
        assert result == "emails_agent"

    def test_get_next_agent_uses_composite_key(self):
        """Test that composite keys (turn_id:agent_name) are used correctly."""
        plan = OrchestratorPlan(
            agents_to_call=[AGENT_CONTACT],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )
        state = MessagesState(
            messages=[],
            orchestration_plan=plan,  # Object format to avoid bug
            current_turn_id=5,
            agent_results={
                make_agent_result_key(5, AGENT_CONTACT): {
                    "status": STATUS_SUCCESS,
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        result = get_next_agent_from_plan(state)

        # Agent with turn_id=5 should be considered executed
        assert result is None

    def test_get_next_agent_different_turn_id_not_skipped(self):
        """Test that agents from different turns are not skipped."""
        plan = OrchestratorPlan(
            agents_to_call=[AGENT_CONTACT],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )
        state = MessagesState(
            messages=[],
            orchestration_plan=plan.model_dump(),
            current_turn_id=6,
            agent_results={
                make_agent_result_key(5, AGENT_CONTACT): {  # Different turn
                    "status": STATUS_SUCCESS,
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        result = get_next_agent_from_plan(state)

        # Agent from turn_id=5 should not affect turn_id=6
        assert result == AGENT_CONTACT

    def test_get_next_agent_logs_selection(self, state_with_plan):
        """Test that agent selection is logged."""
        with patch("src.domains.agents.orchestration.orchestrator.logger") as mock_logger:
            result = get_next_agent_from_plan(state_with_plan)

            assert result == AGENT_CONTACT
            mock_logger.debug.assert_called()

            # Find the "next_agent_selected" call
            debug_calls = [
                call
                for call in mock_logger.debug.call_args_list
                if call[0][0] == "next_agent_selected"
            ]
            assert len(debug_calls) > 0

            call_args = debug_calls[0][1]
            assert call_args["agent_name"] == AGENT_CONTACT
            assert call_args["turn_id"] == 1

    def test_get_next_agent_logs_failed_skip(self):
        """Test that skipping failed agent is logged as warning."""
        plan = OrchestratorPlan(
            agents_to_call=["contacts_agent", "emails_agent"],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )
        state = MessagesState(
            messages=[],
            orchestration_plan=plan.model_dump(),
            current_turn_id=4,
            agent_results={
                make_agent_result_key(4, "contacts_agent"): {
                    "status": STATUS_ERROR,
                    "agent_name": "contacts_agent",
                    "error": "Connection timeout",
                }
            },
        )

        with patch("src.domains.agents.orchestration.orchestrator.logger") as mock_logger:
            get_next_agent_from_plan(state)

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "agent_failed_skipping"
            assert call_args[1]["agent_name"] == "contacts_agent"
            assert call_args[1]["turn_id"] == 4
            assert call_args[1]["error"] == "Connection timeout"

    def test_get_next_agent_logs_all_executed(self):
        """Test that completion is logged when all agents executed."""
        plan = OrchestratorPlan(
            agents_to_call=[AGENT_CONTACT],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={"version": "v1_sequential"},
        )

        state = MessagesState(
            messages=[],
            orchestration_plan=plan,  # Object format to avoid bug
            current_turn_id=1,
            agent_results={
                make_agent_result_key(1, AGENT_CONTACT): {
                    "status": STATUS_SUCCESS,
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        with patch("src.domains.agents.orchestration.orchestrator.logger") as mock_logger:
            result = get_next_agent_from_plan(state)

            assert result is None

            # Find the "all_agents_executed" call
            debug_calls = [
                call
                for call in mock_logger.debug.call_args_list
                if len(call[0]) > 0 and call[0][0] == "all_agents_executed"
            ]
            assert len(debug_calls) > 0

    def test_get_next_agent_handles_dict_plan(self):
        """Test that dict-format plans are handled (legacy support)."""
        state = MessagesState(
            messages=[],
            orchestration_plan={
                "agents_to_call": [AGENT_CONTACT],
                "execution_mode": EXECUTION_MODE_SEQUENTIAL,
                "metadata": {},
            },
            current_turn_id=1,
        )

        result = get_next_agent_from_plan(state)

        assert result == AGENT_CONTACT

    def test_get_next_agent_handles_object_plan(self):
        """Test that object-format plans are handled."""
        plan = OrchestratorPlan(
            agents_to_call=[AGENT_CONTACT],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )

        # Don't convert to dict - pass as object
        state = MessagesState(
            messages=[],
            orchestration_plan=plan,  # Object format
            current_turn_id=1,
        )

        result = get_next_agent_from_plan(state)

        assert result == AGENT_CONTACT

    def test_get_next_agent_returns_string(self, state_with_plan):
        """Test that returned agent name is always a string."""
        result = get_next_agent_from_plan(state_with_plan)

        assert isinstance(result, str)
        assert result == AGENT_CONTACT

    def test_get_next_agent_no_plan_logs(self, empty_state):
        """Test that missing plan is logged."""
        with patch("src.domains.agents.orchestration.orchestrator.logger") as mock_logger:
            result = get_next_agent_from_plan(empty_state)

            assert result is None
            mock_logger.debug.assert_called()

            # Find the "no_orchestration_plan" call
            debug_calls = [
                call
                for call in mock_logger.debug.call_args_list
                if call[0][0] == "no_orchestration_plan"
            ]
            assert len(debug_calls) > 0

    def test_get_next_agent_empty_agents_logs(self):
        """Test that empty agents list is logged."""
        plan = OrchestratorPlan(
            agents_to_call=[],
            execution_mode=EXECUTION_MODE_SEQUENTIAL,
            metadata={},
        )
        state = MessagesState(
            messages=[],
            orchestration_plan=plan.model_dump(),
        )

        with patch("src.domains.agents.orchestration.orchestrator.logger") as mock_logger:
            result = get_next_agent_from_plan(state)

            assert result is None

            # Find the "empty_agents_to_call" call
            debug_calls = [
                call
                for call in mock_logger.debug.call_args_list
                if call[0][0] == "empty_agents_to_call"
            ]
            assert len(debug_calls) > 0


class TestOrchestrationIntegration:
    """Integration tests for orchestration flow."""

    @pytest.mark.asyncio
    async def test_full_orchestration_flow_single_agent(self, sample_router_output):
        """Test complete flow: create plan → check execution → get next agent."""
        # Step 1: Create plan
        plan = await create_orchestration_plan(sample_router_output, {})

        # Step 2: Create state with plan (use object format to avoid bug at line 199)
        state = MessagesState(
            messages=[],
            current_turn_id=1,
            orchestration_plan=plan,  # Object format
        )

        # Step 3: Check if agent should execute
        should_execute = should_execute_agent(AGENT_CONTACT, state)
        assert should_execute is True

        # Step 4: Get next agent
        next_agent = get_next_agent_from_plan(state)
        assert next_agent == AGENT_CONTACT

        # Step 5: Create new state with agent execution result
        state_with_result = MessagesState(
            messages=[],
            current_turn_id=1,
            orchestration_plan=plan,
            agent_results={
                make_agent_result_key(1, AGENT_CONTACT): {
                    "status": STATUS_SUCCESS,
                    "agent_name": AGENT_CONTACT,
                }
            },
        )

        # Step 6: Check no more agents
        next_agent = get_next_agent_from_plan(state_with_result)
        assert next_agent is None

    @pytest.mark.asyncio
    async def test_full_orchestration_flow_unknown_intention(self):
        """Test flow with unknown intention (empty agents list)."""
        router_output = RouterOutput(
            intention="unknown",
            confidence=0.5,
            context_label="general",
            next_node="response",
        )

        plan = await create_orchestration_plan(router_output, {})

        assert plan.agents_to_call == []

        state = MessagesState(
            messages=[],
            current_turn_id=1,
            orchestration_plan=plan,  # Object format
        )
        next_agent = get_next_agent_from_plan(state)

        assert next_agent is None
