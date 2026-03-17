"""
Unit tests for semantic validator sub-agent exceptions (F6).

Tests that:
1. Explicit delegate_to_sub_agent_tool steps satisfy for_each cardinality
2. Check 5 (repeated tools consolidation) excludes delegate_to_sub_agent_tool
"""

from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.semantic_validator import (
    SemanticIssueType,
    validate_for_each_patterns,
)


def _make_plan(steps: list[ExecutionStep]) -> ExecutionPlan:
    return ExecutionPlan(plan_id="test", user_id="test_user", steps=steps)


def _make_step(step_id: str, tool_name: str, depends_on: list[str] | None = None) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        tool_name=tool_name,
        agent_name="test_agent",
        description=f"Step {step_id}",
        parameters={"query": "test"},
        depends_on=depends_on or [],
    )


class TestForEachSubAgentException:
    """Check 1 exception: explicit sub-agent delegation satisfies cardinality."""

    def test_for_each_satisfied_by_explicit_sub_agent_delegation(self):
        """3 delegate steps + for_each_detected=True → valid (no FOR_EACH_MISSING_CARDINALITY)."""
        plan = _make_plan(
            [
                _make_step("step_1", "web_search_tool"),
                _make_step("step_2", TOOL_NAME_DELEGATE_SUB_AGENT, ["step_1"]),
                _make_step("step_3", TOOL_NAME_DELEGATE_SUB_AGENT, ["step_1"]),
                _make_step("step_4", TOOL_NAME_DELEGATE_SUB_AGENT, ["step_1"]),
            ]
        )

        qi = {
            "for_each_detected": True,
            "for_each_collection_key": "experts",
            "cardinality_magnitude": 3,
        }
        is_valid, feedback, issue_type = validate_for_each_patterns(plan, qi)

        assert is_valid is True
        assert feedback is None
        assert issue_type is None

    def test_two_delegate_steps_satisfy_cardinality(self):
        """2 delegate steps (minimum threshold) → valid."""
        plan = _make_plan(
            [
                _make_step("step_1", TOOL_NAME_DELEGATE_SUB_AGENT),
                _make_step("step_2", TOOL_NAME_DELEGATE_SUB_AGENT),
            ]
        )

        qi = {"for_each_detected": True, "for_each_collection_key": "items"}
        is_valid, feedback, issue_type = validate_for_each_patterns(plan, qi)

        assert is_valid is True

    def test_single_delegate_step_still_flags(self):
        """1 delegate step + for_each_detected=True → FOR_EACH_MISSING_CARDINALITY."""
        plan = _make_plan(
            [
                _make_step("step_1", "web_search_tool"),
                _make_step("step_2", TOOL_NAME_DELEGATE_SUB_AGENT, ["step_1"]),
            ]
        )

        qi = {"for_each_detected": True, "for_each_collection_key": "items"}
        is_valid, feedback, issue_type = validate_for_each_patterns(plan, qi)

        assert is_valid is False
        assert issue_type == SemanticIssueType.FOR_EACH_MISSING_CARDINALITY

    def test_no_for_each_detected_passes(self):
        """for_each_detected=False → always valid (no check triggered)."""
        plan = _make_plan(
            [
                _make_step("step_1", TOOL_NAME_DELEGATE_SUB_AGENT),
            ]
        )

        qi = {"for_each_detected": False}
        is_valid, feedback, issue_type = validate_for_each_patterns(plan, qi)

        assert is_valid is True


class TestCheck5SubAgentExemption:
    """Check 5: delegate_to_sub_agent_tool excluded from repeated-tool consolidation."""

    def test_check5_excludes_delegate_tool(self):
        """Repeated delegate_to_sub_agent_tool → NOT flagged as CARDINALITY_MISMATCH."""
        plan = _make_plan(
            [
                _make_step("step_1", "web_search_tool"),
                _make_step("step_2", TOOL_NAME_DELEGATE_SUB_AGENT, ["step_1"]),
                _make_step("step_3", TOOL_NAME_DELEGATE_SUB_AGENT, ["step_1"]),
                _make_step("step_4", TOOL_NAME_DELEGATE_SUB_AGENT, ["step_1"]),
            ]
        )

        # No for_each_detected to avoid Check 1 triggering
        qi = {"for_each_detected": False}
        is_valid, feedback, issue_type = validate_for_each_patterns(plan, qi)

        assert is_valid is True
        assert issue_type is None

    def test_check5_still_flags_other_repeated_tools(self):
        """Repeated get_route_tool → CARDINALITY_MISMATCH (not exempt)."""
        plan = _make_plan(
            [
                _make_step("step_1", "get_events_tool"),
                _make_step("step_2", "get_route_tool", ["step_1"]),
                _make_step("step_3", "get_route_tool", ["step_1"]),
                _make_step("step_4", "get_route_tool", ["step_1"]),
            ]
        )

        qi = {"for_each_detected": False}
        is_valid, feedback, issue_type = validate_for_each_patterns(plan, qi)

        assert is_valid is False
        assert issue_type == SemanticIssueType.CARDINALITY_MISMATCH
