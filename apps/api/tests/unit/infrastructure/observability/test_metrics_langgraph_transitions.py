"""
Unit tests for LangGraph node transition metrics (P2).

Tests that routing functions correctly track:
- Conditional edge decisions (langgraph_conditional_edges_total)
- Node transitions (langgraph_node_transitions_total)

Phase: PHASE 2.5 - LangGraph Observability (P2)
Created: 2025-11-22
"""

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.constants import (
    NODE_APPROVAL_GATE,
    NODE_PLANNER,
    NODE_RESPONSE,
    NODE_ROUTER,
    NODE_TASK_ORCHESTRATOR,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_MESSAGES,
    STATE_KEY_PLAN_APPROVED,
    STATE_KEY_ROUTING_HISTORY,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.graph import route_from_orchestrator, route_from_router
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.routing import route_from_approval_gate, route_from_planner
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.validator import ValidationResult
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_conditional_edges_total,
    langgraph_node_transitions_total,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test to ensure clean state."""
    # Clear all metric families to reset counters
    for collector in list(REGISTRY._collector_to_names.keys()):
        if hasattr(collector, "_metrics"):
            collector._metrics.clear()
    yield


class TestRouteFromRouterMetrics:
    """Test metrics tracking for route_from_router function."""

    def test_tracks_transition_to_planner(self):
        """Verify metrics are tracked when routing to planner."""
        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_ROUTING_HISTORY: [
                RouterOutput(
                    intention="search_contacts",
                    confidence=0.95,
                    context_label="contact",
                    next_node=NODE_PLANNER,
                )
            ],
        }

        result = route_from_router(state)

        assert result == NODE_PLANNER

        # Check conditional edge metric
        conditional_edge_samples = langgraph_conditional_edges_total.collect()[0].samples
        planner_samples = [
            s
            for s in conditional_edge_samples
            if s.labels.get("edge_name") == "route_from_router"
            and s.labels.get("decision") == NODE_PLANNER
        ]
        assert len(planner_samples) > 0
        assert planner_samples[0].value >= 1.0

        # Check node transition metric
        transition_samples = langgraph_node_transitions_total.collect()[0].samples
        router_to_planner_samples = [
            s
            for s in transition_samples
            if s.labels.get("from_node") == NODE_ROUTER and s.labels.get("to_node") == NODE_PLANNER
        ]
        assert len(router_to_planner_samples) > 0
        assert router_to_planner_samples[0].value >= 1.0

    def test_tracks_transition_to_response(self):
        """Verify metrics are tracked when routing to response."""
        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_ROUTING_HISTORY: [
                RouterOutput(
                    intention="conversational",
                    confidence=0.85,
                    context_label="general",
                    next_node=NODE_RESPONSE,
                )
            ],
        }

        result = route_from_router(state)

        assert result == NODE_RESPONSE

        # Check conditional edge metric
        conditional_edge_samples = langgraph_conditional_edges_total.collect()[0].samples
        response_samples = [
            s
            for s in conditional_edge_samples
            if s.labels.get("edge_name") == "route_from_router"
            and s.labels.get("decision") == NODE_RESPONSE
        ]
        assert len(response_samples) > 0
        assert response_samples[0].value >= 1.0

        # Check node transition metric
        transition_samples = langgraph_node_transitions_total.collect()[0].samples
        router_to_response_samples = [
            s
            for s in transition_samples
            if s.labels.get("from_node") == NODE_ROUTER and s.labels.get("to_node") == NODE_RESPONSE
        ]
        assert len(router_to_response_samples) > 0
        assert router_to_response_samples[0].value >= 1.0


class TestRouteFromPlannerMetrics:
    """Test metrics tracking for route_from_planner function."""

    def test_tracks_transition_to_approval_gate(self):
        """Verify metrics are tracked when routing to approval_gate (HITL required)."""
        # Create a valid execution plan with at least one step
        execution_plan = ExecutionPlan(
            plan_id="test-plan-1",
            user_id="test-user-1",
            steps=[
                ExecutionStep(
                    step_id="step-1",
                    tool_name="get_contacts_tool",
                    step_type=StepType.TOOL,
                    args={"query": "test"},
                )
            ],
            domains=["contacts"],
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_VALIDATION_RESULT: ValidationResult(
                is_valid=True,
                requires_hitl=True,
            ),
            STATE_KEY_EXECUTION_PLAN: execution_plan,
        }

        result = route_from_planner(state)

        assert result == "approval_gate"

        # Check conditional edge metric
        conditional_edge_samples = langgraph_conditional_edges_total.collect()[0].samples
        approval_gate_samples = [
            s
            for s in conditional_edge_samples
            if s.labels.get("edge_name") == "route_from_planner"
            and s.labels.get("decision") == "approval_gate"
        ]
        assert len(approval_gate_samples) > 0
        assert approval_gate_samples[0].value >= 1.0

        # Check node transition metric
        transition_samples = langgraph_node_transitions_total.collect()[0].samples
        planner_to_approval_samples = [
            s
            for s in transition_samples
            if s.labels.get("from_node") == NODE_PLANNER
            and s.labels.get("to_node") == NODE_APPROVAL_GATE
        ]
        assert len(planner_to_approval_samples) > 0
        assert planner_to_approval_samples[0].value >= 1.0

    def test_tracks_transition_to_task_orchestrator(self):
        """Verify metrics are tracked when routing to task_orchestrator (no HITL)."""
        # Create a valid execution plan with at least one step
        execution_plan = ExecutionPlan(
            plan_id="test-plan-2",
            user_id="test-user-2",
            steps=[
                ExecutionStep(
                    step_id="step-1",
                    tool_name="get_events_tool",
                    step_type=StepType.TOOL,
                    args={"query": "test"},
                )
            ],
            domains=["calendar"],
        )

        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_VALIDATION_RESULT: ValidationResult(
                is_valid=True,
                requires_hitl=False,
            ),
            STATE_KEY_EXECUTION_PLAN: execution_plan,
        }

        result = route_from_planner(state)

        assert result == "task_orchestrator"

        # Check conditional edge metric
        conditional_edge_samples = langgraph_conditional_edges_total.collect()[0].samples
        orchestrator_samples = [
            s
            for s in conditional_edge_samples
            if s.labels.get("edge_name") == "route_from_planner"
            and s.labels.get("decision") == "task_orchestrator"
        ]
        assert len(orchestrator_samples) > 0
        assert orchestrator_samples[0].value >= 1.0

        # Check node transition metric
        transition_samples = langgraph_node_transitions_total.collect()[0].samples
        planner_to_orchestrator_samples = [
            s
            for s in transition_samples
            if s.labels.get("from_node") == NODE_PLANNER
            and s.labels.get("to_node") == NODE_TASK_ORCHESTRATOR
        ]
        assert len(planner_to_orchestrator_samples) > 0
        assert planner_to_orchestrator_samples[0].value >= 1.0


class TestRouteFromApprovalGateMetrics:
    """Test metrics tracking for route_from_approval_gate function."""

    def test_tracks_transition_to_task_orchestrator_approved(self):
        """Verify metrics are tracked when plan is approved."""
        # LOT 6 FIX: Must include execution_plan with at least one step
        # Empty plans are blocked from execution (route to response instead)
        execution_plan = ExecutionPlan(
            plan_id="test_plan_001",
            user_id="test_user_123",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    tool="search_contacts",
                    description="Search contacts",
                    params={"query": "test"},
                    step_type=StepType.TOOL,
                )
            ],
        )
        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_PLAN_APPROVED: True,
            "execution_plan": execution_plan,
        }

        result = route_from_approval_gate(state)

        assert result == "task_orchestrator"

        # Check conditional edge metric
        conditional_edge_samples = langgraph_conditional_edges_total.collect()[0].samples
        orchestrator_samples = [
            s
            for s in conditional_edge_samples
            if s.labels.get("edge_name") == "route_from_approval_gate"
            and s.labels.get("decision") == "task_orchestrator"
        ]
        assert len(orchestrator_samples) > 0
        assert orchestrator_samples[0].value >= 1.0

        # Check node transition metric
        transition_samples = langgraph_node_transitions_total.collect()[0].samples
        approval_to_orchestrator_samples = [
            s
            for s in transition_samples
            if s.labels.get("from_node") == NODE_APPROVAL_GATE
            and s.labels.get("to_node") == NODE_TASK_ORCHESTRATOR
        ]
        assert len(approval_to_orchestrator_samples) > 0
        assert approval_to_orchestrator_samples[0].value >= 1.0

    def test_tracks_transition_to_response_rejected(self):
        """Verify metrics are tracked when plan is rejected."""
        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            STATE_KEY_PLAN_APPROVED: False,
        }

        result = route_from_approval_gate(state)

        assert result == "response"

        # Check conditional edge metric
        conditional_edge_samples = langgraph_conditional_edges_total.collect()[0].samples
        response_samples = [
            s
            for s in conditional_edge_samples
            if s.labels.get("edge_name") == "route_from_approval_gate"
            and s.labels.get("decision") == "response"
        ]
        assert len(response_samples) > 0
        assert response_samples[0].value >= 1.0

        # Check node transition metric
        transition_samples = langgraph_node_transitions_total.collect()[0].samples
        approval_to_response_samples = [
            s
            for s in transition_samples
            if s.labels.get("from_node") == NODE_APPROVAL_GATE
            and s.labels.get("to_node") == NODE_RESPONSE
        ]
        assert len(approval_to_response_samples) > 0
        assert approval_to_response_samples[0].value >= 1.0


class TestRouteFromOrchestratorMetrics:
    """Test metrics tracking for route_from_orchestrator function."""

    def test_tracks_transition_to_response_no_next_agent(self):
        """Verify metrics are tracked when all agents are done.

        ADR-062: route_from_orchestrator now routes to NODE_INITIATIVE
        instead of NODE_RESPONSE when no next agent exists.
        """
        from src.core.constants import NODE_INITIATIVE

        state: MessagesState = {
            STATE_KEY_MESSAGES: [],
            # Empty orchestration_plan means all agents done
        }

        result = route_from_orchestrator(state)

        assert result == NODE_INITIATIVE

        # Check conditional edge metric
        conditional_edge_samples = langgraph_conditional_edges_total.collect()[0].samples
        response_samples = [
            s
            for s in conditional_edge_samples
            if s.labels.get("edge_name") == "route_from_orchestrator"
            and s.labels.get("decision") == NODE_INITIATIVE
        ]
        assert len(response_samples) > 0
        assert response_samples[0].value >= 1.0

        # Check node transition metric
        transition_samples = langgraph_node_transitions_total.collect()[0].samples
        orchestrator_to_response_samples = [
            s
            for s in transition_samples
            if s.labels.get("from_node") == NODE_TASK_ORCHESTRATOR
            and s.labels.get("to_node") == NODE_INITIATIVE
        ]
        assert len(orchestrator_to_response_samples) > 0
        assert orchestrator_to_response_samples[0].value >= 1.0


class TestMetricsCardinality:
    """Test that metrics have acceptable cardinality."""

    def test_conditional_edges_cardinality(self):
        """Verify langgraph_conditional_edges_total has acceptable label combinations."""
        # Expected edge_name values: 4 routing functions

        # Expected decision values per edge:
        # - route_from_router: planner, response (2)
        # - route_from_planner: approval_gate, task_orchestrator (2)
        # - route_from_approval_gate: task_orchestrator, response (2)
        # - route_from_orchestrator: response, contacts_agent, emails_agent (3)
        # Total: 2 + 2 + 2 + 3 = 9 time series
        max_expected_series = 9

        # Simulate all possible routing decisions
        test_states = [
            # route_from_router → planner
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_ROUTING_HISTORY: [
                    RouterOutput(
                        intention="action",
                        confidence=0.9,
                        context_label="contact",
                        next_node=NODE_PLANNER,
                    )
                ],
            },
            # route_from_router → response
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_ROUTING_HISTORY: [
                    RouterOutput(
                        intention="conv",
                        confidence=0.9,
                        context_label="general",
                        next_node=NODE_RESPONSE,
                    )
                ],
            },
            # route_from_planner → approval_gate
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_VALIDATION_RESULT: ValidationResult(is_valid=True, requires_hitl=True),
            },
            # route_from_planner → task_orchestrator
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_VALIDATION_RESULT: ValidationResult(is_valid=True, requires_hitl=False),
            },
            # route_from_approval_gate → task_orchestrator
            {STATE_KEY_MESSAGES: [], STATE_KEY_PLAN_APPROVED: True},
            # route_from_approval_gate → response
            {STATE_KEY_MESSAGES: [], STATE_KEY_PLAN_APPROVED: False},
            # route_from_orchestrator → response
            {STATE_KEY_MESSAGES: []},
        ]

        # Execute all routing functions
        route_from_router(test_states[0])
        route_from_router(test_states[1])
        route_from_planner(test_states[2])
        route_from_planner(test_states[3])
        route_from_approval_gate(test_states[4])
        route_from_approval_gate(test_states[5])
        route_from_orchestrator(test_states[6])

        # Check cardinality
        samples = langgraph_conditional_edges_total.collect()[0].samples
        unique_label_combos = {(s.labels["edge_name"], s.labels["decision"]) for s in samples}

        assert (
            len(unique_label_combos) <= max_expected_series
        ), f"Cardinality exceeded: {len(unique_label_combos)} > {max_expected_series}"

    def test_node_transitions_cardinality(self):
        """Verify langgraph_node_transitions_total has acceptable label combinations."""
        # Expected node pairs:
        # - router → planner, response (2)
        # - planner → approval_gate, task_orchestrator (2)
        # - approval_gate → task_orchestrator, response (2)
        # - task_orchestrator → response, contacts_agent, emails_agent (3)
        # - contacts_agent → response (1)
        # - emails_agent → response (1)
        # Total: 11 time series
        max_expected_series = 11

        # Simulate routing (same as above)
        test_states = [
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_ROUTING_HISTORY: [
                    RouterOutput(
                        intention="action",
                        confidence=0.9,
                        context_label="contact",
                        next_node=NODE_PLANNER,
                    )
                ],
            },
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_ROUTING_HISTORY: [
                    RouterOutput(
                        intention="conv",
                        confidence=0.9,
                        context_label="general",
                        next_node=NODE_RESPONSE,
                    )
                ],
            },
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_VALIDATION_RESULT: ValidationResult(is_valid=True, requires_hitl=True),
            },
            {
                STATE_KEY_MESSAGES: [],
                STATE_KEY_VALIDATION_RESULT: ValidationResult(is_valid=True, requires_hitl=False),
            },
            {STATE_KEY_MESSAGES: [], STATE_KEY_PLAN_APPROVED: True},
            {STATE_KEY_MESSAGES: [], STATE_KEY_PLAN_APPROVED: False},
            {STATE_KEY_MESSAGES: []},
        ]

        route_from_router(test_states[0])
        route_from_router(test_states[1])
        route_from_planner(test_states[2])
        route_from_planner(test_states[3])
        route_from_approval_gate(test_states[4])
        route_from_approval_gate(test_states[5])
        route_from_orchestrator(test_states[6])

        # Check cardinality
        samples = langgraph_node_transitions_total.collect()[0].samples
        unique_label_combos = {(s.labels["from_node"], s.labels["to_node"]) for s in samples}

        assert (
            len(unique_label_combos) <= max_expected_series
        ), f"Cardinality exceeded: {len(unique_label_combos)} > {max_expected_series}"
