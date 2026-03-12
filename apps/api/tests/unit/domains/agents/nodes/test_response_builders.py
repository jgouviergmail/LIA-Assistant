"""
Unit tests for response builders.

Tests for the pure functions that construct state update dictionaries
for the planner node.
"""

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from src.domains.agents.constants import (
    STATE_KEY_CLARIFICATION_FIELD,
    STATE_KEY_CLARIFICATION_RESPONSE,
    STATE_KEY_EXECUTION_PLAN,
    STATE_KEY_NEEDS_REPLAN,
    STATE_KEY_PLANNER_ERROR,
    STATE_KEY_PLANNER_METADATA,
    STATE_KEY_VALIDATION_RESULT,
)
from src.domains.agents.nodes.response_builders import (
    build_clarification_response,
    build_parsing_failed_response,
    build_success_response,
    build_validation_failed_response,
)


@dataclass
class MockWarning:
    """Mock validation warning."""

    code: str | Any
    message: str
    step_index: int = 0


@dataclass
class MockError:
    """Mock validation error."""

    code: str | Any
    message: str
    step_index: int = 0
    context: dict | None = None


@dataclass
class MockValidationResult:
    """Mock ValidationResult for testing."""

    is_valid: bool
    total_cost_usd: float
    warnings: list[MockWarning]
    errors: list[MockError]


@dataclass
class MockStep:
    """Mock execution step."""

    step_id: str
    step_type: str
    tool_name: str | None = None
    agent_name: str | None = None
    parameters: dict | None = None
    condition: str | None = None
    on_success: str | None = None
    on_fail: str | None = None


@dataclass
class MockExecutionPlan:
    """Mock ExecutionPlan for testing."""

    plan_id: str
    steps: list[MockStep]
    execution_mode: str = "sequential"
    estimated_cost_usd: float = 0.0
    metadata: dict | None = None


class TestBuildSuccessResponse:
    """Tests for build_success_response function."""

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_returns_execution_plan_in_state(self, mock_metric):
        """Test that execution plan is included in state."""
        plan = MockExecutionPlan(
            plan_id="plan_123",
            steps=[MockStep(step_id="step1", step_type="TOOL", tool_name="search")],
        )
        validation = MockValidationResult(
            is_valid=True, total_cost_usd=0.01, warnings=[], errors=[]
        )

        result = build_success_response(plan, validation, "run_123")

        assert result[STATE_KEY_EXECUTION_PLAN] == plan
        assert result[STATE_KEY_PLANNER_ERROR] is None

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_builds_planner_metadata(self, mock_metric):
        """Test that planner metadata is built correctly."""
        plan = MockExecutionPlan(
            plan_id="plan_456",
            steps=[MockStep(step_id="step1", step_type="TOOL", tool_name="search")],
            execution_mode="parallel",
        )
        validation = MockValidationResult(
            is_valid=True, total_cost_usd=0.02, warnings=[], errors=[]
        )

        result = build_success_response(plan, validation, "run_456")

        metadata = result[STATE_KEY_PLANNER_METADATA]
        assert metadata["plan_id"] == "plan_456"
        assert metadata["step_count"] == 1
        assert metadata["execution_mode"] == "parallel"
        assert metadata["estimated_cost_usd"] == 0.02

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_includes_warnings_in_metadata(self, mock_metric):
        """Test that warnings are included in metadata."""
        plan = MockExecutionPlan(
            plan_id="plan_789",
            steps=[],
        )
        validation = MockValidationResult(
            is_valid=True,
            total_cost_usd=0.0,
            warnings=[
                MockWarning(code="WARN001", message="Low confidence"),
            ],
            errors=[],
        )

        result = build_success_response(plan, validation, "run_789")

        metadata = result[STATE_KEY_PLANNER_METADATA]
        assert metadata["validation"]["warnings_count"] == 1
        assert len(metadata["validation"]["warnings"]) == 1

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_builds_steps_summary_for_tool_steps(self, mock_metric):
        """Test that tool steps are summarized correctly."""
        plan = MockExecutionPlan(
            plan_id="plan_tool",
            steps=[
                MockStep(
                    step_id="step1",
                    step_type="TOOL",
                    tool_name="search_contacts",
                    agent_name="contacts_agent",
                    parameters={"query": "john", "limit": 10},
                )
            ],
        )
        validation = MockValidationResult(is_valid=True, total_cost_usd=0.0, warnings=[], errors=[])

        result = build_success_response(plan, validation, "run_tool")

        metadata = result[STATE_KEY_PLANNER_METADATA]
        step_info = metadata["steps"][0]
        assert step_info["step_id"] == "step1"
        assert step_info["step_type"] == "TOOL"
        assert step_info["tool"] == "search_contacts"
        assert step_info["agent"] == "contacts_agent"

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_builds_steps_summary_for_conditional_steps(self, mock_metric):
        """Test that conditional steps are summarized correctly."""
        plan = MockExecutionPlan(
            plan_id="plan_cond",
            steps=[
                MockStep(
                    step_id="step1",
                    step_type="CONDITIONAL",
                    condition="$result.success",
                    on_success="step2",
                    on_fail="step3",
                )
            ],
        )
        validation = MockValidationResult(is_valid=True, total_cost_usd=0.0, warnings=[], errors=[])

        result = build_success_response(plan, validation, "run_cond")

        metadata = result[STATE_KEY_PLANNER_METADATA]
        step_info = metadata["steps"][0]
        assert step_info["step_type"] == "CONDITIONAL"
        assert step_info["condition"] == "$result.success"
        assert step_info["on_success"] == "step2"
        assert step_info["on_fail"] == "step3"

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_extracts_voice_params_for_search_tools(self, mock_metric):
        """Test that voice parameters are extracted for search tools."""
        plan = MockExecutionPlan(
            plan_id="plan_voice",
            steps=[
                MockStep(
                    step_id="step1",
                    step_type="TOOL",
                    tool_name="search_contacts",
                    parameters={"query": "john doe", "max_results": 5},
                )
            ],
        )
        validation = MockValidationResult(is_valid=True, total_cost_usd=0.0, warnings=[], errors=[])

        result = build_success_response(plan, validation, "run_voice")

        metadata = result[STATE_KEY_PLANNER_METADATA]
        step_info = metadata["steps"][0]
        assert "voice_params" in step_info
        assert step_info["voice_params"]["result_count"] == 5
        assert step_info["voice_params"]["tool_type"] == "search"

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_clears_clarification_flags_on_success(self, mock_metric):
        """Test that clarification flags are cleared."""
        plan = MockExecutionPlan(plan_id="plan_clear", steps=[])
        validation = MockValidationResult(is_valid=True, total_cost_usd=0.0, warnings=[], errors=[])

        result = build_success_response(plan, validation, "run_clear")

        assert result[STATE_KEY_NEEDS_REPLAN] is False
        assert result[STATE_KEY_CLARIFICATION_RESPONSE] is None
        assert result[STATE_KEY_CLARIFICATION_FIELD] is None

    @patch("src.domains.agents.nodes.response_builders.planner_plans_created_total")
    def test_tracks_metrics(self, mock_metric):
        """Test that metrics are tracked."""
        plan = MockExecutionPlan(
            plan_id="plan_metric",
            steps=[],
            execution_mode="parallel",
        )
        validation = MockValidationResult(is_valid=True, total_cost_usd=0.0, warnings=[], errors=[])

        build_success_response(plan, validation, "run_metric")

        mock_metric.labels.assert_called_once_with(execution_mode="parallel")
        mock_metric.labels().inc.assert_called_once()


class TestBuildValidationFailedResponse:
    """Tests for build_validation_failed_response function."""

    @patch("src.domains.agents.nodes.response_builders.planner_plans_rejected_total")
    def test_returns_none_for_execution_plan(self, mock_metric):
        """Test that execution plan is None in error response."""
        plan = MockExecutionPlan(plan_id="plan_fail", steps=[])
        validation = MockValidationResult(
            is_valid=False,
            total_cost_usd=0.0,
            warnings=[],
            errors=[MockError(code="ERR001", message="Invalid step")],
        )

        result = build_validation_failed_response(plan, validation)

        assert result[STATE_KEY_EXECUTION_PLAN] is None

    @patch("src.domains.agents.nodes.response_builders.planner_plans_rejected_total")
    def test_includes_error_details(self, mock_metric):
        """Test that error details are included."""
        plan = MockExecutionPlan(plan_id="plan_errors", steps=[])
        validation = MockValidationResult(
            is_valid=False,
            total_cost_usd=0.0,
            warnings=[],
            errors=[
                MockError(code="ERR001", message="Missing parameter", step_index=0),
                MockError(code="ERR002", message="Invalid type", step_index=1),
            ],
        )

        result = build_validation_failed_response(plan, validation)

        error_info = result[STATE_KEY_PLANNER_ERROR]
        assert len(error_info["errors"]) == 2
        assert error_info["errors"][0]["code"] == "ERR001"
        assert error_info["errors"][0]["message"] == "Missing parameter"
        assert error_info["message"] == "Missing parameter"

    @patch("src.domains.agents.nodes.response_builders.planner_plans_rejected_total")
    def test_includes_warning_details(self, mock_metric):
        """Test that warning details are included."""
        plan = MockExecutionPlan(plan_id="plan_warnings", steps=[])
        validation = MockValidationResult(
            is_valid=False,
            total_cost_usd=0.0,
            warnings=[MockWarning(code="WARN001", message="Deprecated")],
            errors=[MockError(code="ERR001", message="Error")],
        )

        result = build_validation_failed_response(plan, validation)

        error_info = result[STATE_KEY_PLANNER_ERROR]
        assert len(error_info["warnings"]) == 1
        assert error_info["warnings"][0]["code"] == "WARN001"

    @patch("src.domains.agents.nodes.response_builders.planner_plans_rejected_total")
    def test_tracks_rejection_metric(self, mock_metric):
        """Test that rejection metric is tracked."""
        plan = MockExecutionPlan(plan_id="plan_rej", steps=[])
        validation = MockValidationResult(
            is_valid=False,
            total_cost_usd=0.0,
            warnings=[],
            errors=[MockError(code="ERR", message="Error")],
        )

        build_validation_failed_response(plan, validation)

        mock_metric.labels.assert_called_once_with(reason="validation_failed")
        mock_metric.labels().inc.assert_called_once()

    @patch("src.domains.agents.nodes.response_builders.planner_plans_rejected_total")
    def test_handles_enum_code(self, mock_metric):
        """Test that enum codes are handled correctly."""
        from enum import Enum

        class ErrorCode(Enum):
            INVALID = "INVALID_CODE"

        plan = MockExecutionPlan(plan_id="plan_enum", steps=[])
        validation = MockValidationResult(
            is_valid=False,
            total_cost_usd=0.0,
            warnings=[],
            errors=[MockError(code=ErrorCode.INVALID, message="Invalid")],
        )

        result = build_validation_failed_response(plan, validation)

        error_info = result[STATE_KEY_PLANNER_ERROR]
        assert error_info["errors"][0]["code"] == "INVALID_CODE"


class TestBuildClarificationResponse:
    """Tests for build_clarification_response function."""

    def test_returns_empty_plan_with_clarification_metadata(self):
        """Test that empty plan with clarification metadata is returned."""
        plan = MockExecutionPlan(
            plan_id="plan_clarify",
            steps=[],
            metadata={
                "missing_parameters": [{"parameter": "recipient", "question": "Who to send to?"}],
                "reasoning": "Recipient not specified",
            },
        )

        result = build_clarification_response(plan, "run_clarify")

        assert result[STATE_KEY_EXECUTION_PLAN] == plan
        assert result[STATE_KEY_PLANNER_ERROR] is None

    def test_includes_clarification_in_semantic_validation(self):
        """Test that semantic_validation includes clarification info."""
        plan = MockExecutionPlan(
            plan_id="plan_sem",
            steps=[],
            metadata={
                "missing_parameters": ["recipient"],
                "reasoning": "Need recipient",
            },
        )

        result = build_clarification_response(plan, "run_sem")

        sem_val = result["semantic_validation"]
        assert sem_val["requires_clarification"] is True
        assert sem_val["is_valid"] is False
        assert len(sem_val["clarification_questions"]) == 1
        assert "recipient" in sem_val["clarification_questions"][0]

    def test_builds_clarification_questions_from_dict_params(self):
        """Test clarification questions from dict parameters."""
        plan = MockExecutionPlan(
            plan_id="plan_q",
            steps=[],
            metadata={
                "missing_parameters": [
                    {"parameter": "email", "question": "What email address?"},
                    {"parameter": "subject", "question": "What subject?"},
                ],
                "reasoning": "Missing info",
            },
        )

        result = build_clarification_response(plan, "run_q")

        sem_val = result["semantic_validation"]
        assert len(sem_val["clarification_questions"]) == 2
        assert "What email address?" in sem_val["clarification_questions"]

    def test_clears_needs_replan_flag(self):
        """Test that needs_replan flag is cleared."""
        plan = MockExecutionPlan(
            plan_id="plan_replan",
            steps=[],
            metadata={"missing_parameters": [], "reasoning": ""},
        )

        result = build_clarification_response(plan, "run_replan")

        assert result[STATE_KEY_NEEDS_REPLAN] is False
        assert result[STATE_KEY_CLARIFICATION_RESPONSE] is None
        assert result[STATE_KEY_CLARIFICATION_FIELD] is None

    def test_includes_validation_result_for_routing(self):
        """Test that validation result is included for routing."""
        plan = MockExecutionPlan(
            plan_id="plan_route",
            steps=[],
            metadata={"missing_parameters": [], "reasoning": ""},
        )

        result = build_clarification_response(plan, "run_route")

        assert STATE_KEY_VALIDATION_RESULT in result
        assert result[STATE_KEY_VALIDATION_RESULT].requires_hitl is True


class TestBuildParsingFailedResponse:
    """Tests for build_parsing_failed_response function."""

    def test_returns_none_for_execution_plan(self):
        """Test that execution plan is None in error response."""
        result = build_parsing_failed_response("run_parse", None, None)

        assert result[STATE_KEY_EXECUTION_PLAN] is None

    def test_returns_generic_error_message(self):
        """Test that generic error message is returned."""
        result = build_parsing_failed_response("run_err", None, None)

        error_info = result[STATE_KEY_PLANNER_ERROR]
        assert "Failed to parse" in error_info["message"]

    def test_handles_partial_plan(self):
        """Test handling when plan exists but validation failed."""
        plan = MockExecutionPlan(plan_id="plan_partial", steps=[])

        result = build_parsing_failed_response("run_partial", plan, None)

        assert result[STATE_KEY_EXECUTION_PLAN] is None
        assert result[STATE_KEY_PLANNER_ERROR] is not None

    def test_handles_partial_validation(self):
        """Test handling when validation exists but plan failed."""
        validation = MockValidationResult(
            is_valid=False, total_cost_usd=0.0, warnings=[], errors=[]
        )

        result = build_parsing_failed_response("run_val", None, validation)

        assert result[STATE_KEY_EXECUTION_PLAN] is None
