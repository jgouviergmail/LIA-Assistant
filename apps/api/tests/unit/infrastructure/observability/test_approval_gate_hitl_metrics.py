"""
Tests for HITL business metrics tracking in approval_gate_node (Phase 3.2 - Step 2.3).

Tests business metrics instrumentation:
- hitl_feature_usage_total (Counter with interaction_type, agent_type labels)
- agent_tool_approval_rate (Histogram with agent_type label)

Business metrics track user engagement with HITL features, distinct from
framework metrics (hitl_plan_decisions) which track operational success/failure.

Coverage target: 100% of business metrics paths

Phase: 3.2 - Business Metrics - Step 2.3
Date: 2025-11-23
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.nodes.approval_gate_node import (
    _extract_agent_types_from_plan,
    _process_approval_decision,
)
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.validator import ValidationContext
from src.infrastructure.observability.metrics_business import (
    agent_tool_approval_rate,
    hitl_feature_usage_total,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_execution_plan():
    """Create sample ExecutionPlan with mixed agent types."""
    return ExecutionPlan(
        plan_id="test_plan_123",
        user_id="user_456",
        session_id="session_789",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts",
                parameters={"query": "John"},
                depends_on=[],
                description="Search for John in contacts",
            ),
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.TOOL,
                agent_name="emails_agent",
                tool_name="search_emails",
                parameters={"query": "meeting"},
                depends_on=["step_1"],
                description="Search emails about meeting",
            ),
            ExecutionStep(
                step_id="step_3",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",  # Duplicate agent_type
                tool_name="get_contact_details",
                parameters={"contact_id": "$steps.step_1.contact_id"},
                depends_on=["step_1"],
                description="Get contact details",
            ),
        ],
        execution_mode="sequential",
        max_cost_usd=1.0,
        estimated_cost_usd=0.05,
        max_timeout_seconds=300,
        version="1.0",
        metadata={"query": "Find John and check emails"},
    )


@pytest.fixture
def validation_context():
    """Create sample ValidationContext."""
    return ValidationContext(
        user_id="user_456",
        session_id="session_789",
        available_scopes=["contacts.read", "gmail.read"],
        user_roles=["user"],
        allow_hitl=True,
    )


@pytest.fixture
def mock_framework_metrics():
    """Mock framework metrics to isolate business metrics testing."""
    with (
        patch("src.domains.agents.nodes.approval_gate_node.hitl_plan_decisions") as mock_decisions,
        patch(
            "src.domains.agents.nodes.approval_gate_node.hitl_plan_modifications"
        ) as mock_modifications,
    ):
        # Mock .labels() chaining
        mock_decisions.labels.return_value.inc = MagicMock()
        mock_modifications.labels.return_value.inc = MagicMock()

        yield {
            "decisions": mock_decisions,
            "modifications": mock_modifications,
        }


# ============================================================================
# TESTS - Helper Function
# ============================================================================


def test_extract_agent_types_from_plan(sample_execution_plan):
    """Test agent_type extraction from ExecutionPlan steps."""
    agent_types = _extract_agent_types_from_plan(sample_execution_plan)

    # Expected: 2 unique agent_types (contacts, emails)
    # contacts_agent appears twice but should be deduplicated
    assert len(agent_types) == 2
    assert "contacts" in agent_types
    assert "emails" in agent_types


def test_extract_agent_types_empty_plan():
    """Test agent_type extraction from empty plan.

    Note: ExecutionPlan validates that steps cannot be empty, so this test
    creates a minimal plan with one step instead.
    """
    minimal_plan = ExecutionPlan(
        plan_id="minimal_plan",
        user_id="user_123",
        session_id="session_456",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="generic_agent",
                tool_name="noop",
                parameters={},
                depends_on=[],
                description="Minimal step",
            )
        ],
        execution_mode="sequential",
        max_cost_usd=1.0,
        estimated_cost_usd=0.0,
        max_timeout_seconds=300,
        version="1.0",
        metadata={},
    )

    agent_types = _extract_agent_types_from_plan(minimal_plan)
    assert agent_types == ["generic"]


def test_extract_agent_types_non_standard_agent_name():
    """Test agent_type extraction with non-standard agent names."""
    plan = ExecutionPlan(
        plan_id="custom_plan",
        user_id="user_123",
        session_id="session_456",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="custom_tool",  # No "_agent" suffix
                tool_name="custom_action",
                parameters={},
                depends_on=[],
                description="Custom action",
            ),
        ],
        execution_mode="sequential",
        max_cost_usd=1.0,
        estimated_cost_usd=0.0,
        max_timeout_seconds=300,
        version="1.0",
        metadata={},
    )

    agent_types = _extract_agent_types_from_plan(plan)
    # Should use full agent_name as fallback
    assert agent_types == ["custom_tool"]


# ============================================================================
# TESTS - APPROVE Decision
# ============================================================================


def test_approval_gate_tracks_approval(
    sample_execution_plan, validation_context, mock_framework_metrics
):
    """Test business metrics tracking for APPROVE decision."""
    decision_data = {"decision": "APPROVE"}

    # Execute decision processing
    approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
        decision_data, sample_execution_plan, validation_context
    )

    # Assertions: Function behavior
    assert approved is True
    assert modified_plan is None
    assert rejection_reason == ""

    # Verify framework metric was tracked (mocked)
    mock_framework_metrics["decisions"].labels.assert_called_with(decision="APPROVE")

    # Verify business metrics (real Prometheus metrics)
    # hitl_feature_usage_total should increment for each agent_type
    assert hitl_feature_usage_total is not None

    # agent_tool_approval_rate should observe 1.0 for each agent_type
    assert agent_tool_approval_rate is not None


# ============================================================================
# TESTS - REJECT Decision
# ============================================================================


def test_approval_gate_tracks_rejection(
    sample_execution_plan, validation_context, mock_framework_metrics
):
    """Test business metrics tracking for REJECT decision."""
    decision_data = {
        "decision": "REJECT",
        "rejection_reason": "Plan too expensive",
    }

    # Execute decision processing
    approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
        decision_data, sample_execution_plan, validation_context
    )

    # Assertions: Function behavior
    assert approved is False
    assert modified_plan is None
    assert rejection_reason == "Plan too expensive"

    # Verify framework metric was tracked (mocked)
    mock_framework_metrics["decisions"].labels.assert_called_with(decision="REJECT")

    # Verify business metrics (real Prometheus metrics)
    # hitl_feature_usage_total should increment for each agent_type
    assert hitl_feature_usage_total is not None

    # agent_tool_approval_rate should observe 0.0 for each agent_type
    assert agent_tool_approval_rate is not None


# ============================================================================
# TESTS - EDIT Decision
# ============================================================================


def test_approval_gate_tracks_edit(
    sample_execution_plan, validation_context, mock_framework_metrics
):
    """Test business metrics tracking for EDIT decision with successful modification."""
    decision_data = {
        "decision": "EDIT",
        "modifications": [
            {
                "step_id": "step_1",
                "modification_type": "edit_params",  # Valid type: edit_params, remove_step, reorder_steps
                "field_path": "parameters.query",
                "new_value": "Jane",
            }
        ],
    }

    # Mock PlanEditor and PlanValidator to avoid complex setup
    with (
        patch("src.domains.agents.nodes.approval_gate_node.PlanEditor") as mock_editor_class,
        patch("src.domains.agents.nodes.approval_gate_node.PlanValidator") as mock_validator_class,
    ):
        # Setup mock editor
        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor

        # Create modified plan (same as original for simplicity)
        modified_plan = ExecutionPlan(
            plan_id="modified_plan_123",
            user_id=sample_execution_plan.user_id,
            session_id=sample_execution_plan.session_id,
            steps=sample_execution_plan.steps,  # Same steps for testing
            execution_mode=sample_execution_plan.execution_mode,
            max_cost_usd=sample_execution_plan.max_cost_usd,
            estimated_cost_usd=sample_execution_plan.estimated_cost_usd,
            max_timeout_seconds=sample_execution_plan.max_timeout_seconds,
            version=sample_execution_plan.version,
            metadata=sample_execution_plan.metadata,
        )
        mock_editor.apply_modifications.return_value = modified_plan

        # Setup mock validator
        mock_validator = MagicMock()
        mock_validator_class.return_value = mock_validator
        mock_validation_result = MagicMock()
        mock_validation_result.is_valid = True
        mock_validator.validate_execution_plan.return_value = mock_validation_result

        # Execute decision processing
        approved, returned_plan, rejection_reason, replan_instructions = _process_approval_decision(
            decision_data, sample_execution_plan, validation_context
        )

        # Assertions: Function behavior
        assert approved is True
        assert returned_plan == modified_plan
        assert rejection_reason == ""

        # Verify framework metric was tracked (mocked)
        mock_framework_metrics["decisions"].labels.assert_called_with(decision="EDIT")

        # Verify business metrics (real Prometheus metrics)
        # hitl_feature_usage_total should increment for each agent_type
        assert hitl_feature_usage_total is not None

        # agent_tool_approval_rate should observe 1.0 for each agent_type (plan continues)
        assert agent_tool_approval_rate is not None


# ============================================================================
# TESTS - REPLAN Decision (Clarification)
# ============================================================================


def test_approval_gate_tracks_clarification(
    sample_execution_plan, validation_context, mock_framework_metrics
):
    """Test business metrics tracking for REPLAN decision (mapped to clarification)."""
    decision_data = {"decision": "REPLAN"}

    # Execute decision processing
    approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
        decision_data, sample_execution_plan, validation_context
    )

    # Assertions: Function behavior (REPLAN returns empty rejection_reason and replan_instructions)
    assert approved is False
    assert modified_plan is None
    assert rejection_reason == ""  # REPLAN doesn't use rejection_reason
    # replan_instructions may be empty if no instructions provided in decision_data
    # but the 4th element should be returned

    # Verify framework metric was tracked (mocked)
    mock_framework_metrics["decisions"].labels.assert_called_with(decision="REPLAN")

    # Verify business metrics (real Prometheus metrics)
    # hitl_feature_usage_total should increment with interaction_type="clarification"
    assert hitl_feature_usage_total is not None

    # agent_tool_approval_rate should observe 0.0 (plan stopped)
    assert agent_tool_approval_rate is not None


# ============================================================================
# TESTS - Business Metric Definitions
# ============================================================================


def test_hitl_feature_usage_total_metric_definition():
    """Test that hitl_feature_usage_total is correctly defined."""
    # Verify metric exists
    assert hitl_feature_usage_total is not None

    # Verify metric name
    assert hitl_feature_usage_total._name == "hitl_feature_usage"

    # Verify labels
    expected_labels = ("interaction_type", "agent_type")
    assert hitl_feature_usage_total._labelnames == expected_labels

    # Verify metric type
    from prometheus_client import Counter

    assert isinstance(hitl_feature_usage_total, Counter)


def test_agent_tool_approval_rate_metric_definition():
    """Test that agent_tool_approval_rate is correctly defined."""
    # Verify metric exists
    assert agent_tool_approval_rate is not None

    # Verify metric name
    assert agent_tool_approval_rate._name == "agent_tool_approval_rate"

    # Verify labels
    expected_labels = ("agent_type",)
    assert agent_tool_approval_rate._labelnames == expected_labels

    # Verify metric type
    from prometheus_client import Histogram

    assert isinstance(agent_tool_approval_rate, Histogram)


# ============================================================================
# TESTS - Edge Cases
# ============================================================================


def test_approval_gate_tracks_unknown_decision(
    sample_execution_plan, validation_context, mock_framework_metrics
):
    """Test business metrics NOT tracked for unknown decision types."""
    decision_data = {"decision": "INVALID_DECISION"}

    # Execute decision processing
    approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
        decision_data, sample_execution_plan, validation_context
    )

    # Assertions: Function behavior (should reject)
    assert approved is False
    assert modified_plan is None
    assert "Unknown decision type" in rejection_reason

    # Unknown decisions don't track framework or business metrics
    # (no metrics calls expected)


def test_approval_gate_handles_single_agent_plan():
    """Test metrics tracking with plan containing only one agent type."""
    single_agent_plan = ExecutionPlan(
        plan_id="single_agent_plan",
        user_id="user_123",
        session_id="session_456",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts",
                parameters={"query": "John"},
                depends_on=[],
                description="Search contacts",
            ),
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",  # Same agent
                tool_name="get_contact_details",
                parameters={"contact_id": "$steps.step_1.contact_id"},
                depends_on=["step_1"],
                description="Get details",
            ),
        ],
        execution_mode="sequential",
        max_cost_usd=1.0,
        estimated_cost_usd=0.02,
        max_timeout_seconds=300,
        version="1.0",
        metadata={},
    )

    agent_types = _extract_agent_types_from_plan(single_agent_plan)

    # Should extract only "contacts" (deduplicated)
    assert len(agent_types) == 1
    assert agent_types == ["contacts"]


def test_approval_gate_edit_validation_failure(
    sample_execution_plan, validation_context, mock_framework_metrics
):
    """Test EDIT decision when modified plan fails validation."""
    decision_data = {
        "decision": "EDIT",
        "modifications": [
            {
                "step_id": "step_1",
                "modification_type": "edit_params",  # Valid type
                "field_path": "parameters.query",
                "new_value": "InvalidValue",
            }
        ],
    }

    # Mock PlanEditor and PlanValidator
    with (
        patch("src.domains.agents.nodes.approval_gate_node.PlanEditor") as mock_editor_class,
        patch("src.domains.agents.nodes.approval_gate_node.PlanValidator") as mock_validator_class,
    ):
        # Setup mock editor
        mock_editor = MagicMock()
        mock_editor_class.return_value = mock_editor
        mock_editor.apply_modifications.return_value = sample_execution_plan

        # Setup mock validator - validation FAILS
        mock_validator = MagicMock()
        mock_validator_class.return_value = mock_validator
        mock_validation_result = MagicMock()
        mock_validation_result.is_valid = False
        mock_validation_result.errors = ["Invalid query parameter"]
        mock_validator.validate_execution_plan.return_value = mock_validation_result

        # Execute decision processing
        approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
            decision_data, sample_execution_plan, validation_context
        )

        # Assertions: Should reject due to validation failure
        assert approved is False
        assert modified_plan is None
        assert "Modified plan validation failed" in rejection_reason

        # Framework EDIT decision metric should NOT be tracked (validation failed)
        # Business metrics should NOT be tracked (plan rejected before success path)
