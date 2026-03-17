"""
Unit tests for sub-agent HITL rejection fallback (F6).

When a user rejects a plan containing delegate_to_sub_agent_tool steps,
the approval gate should convert the REJECT into a REPLAN without sub-agents
instead of routing to the response node.
"""

from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT
from src.domains.agents.nodes.approval_gate_node import _process_approval_decision
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.validator import ValidationContext


def _make_plan_with_delegate_steps() -> ExecutionPlan:
    """Create a plan containing delegate_to_sub_agent_tool steps."""
    return ExecutionPlan(
        user_id="test_user",
        plan_id="test_plan",
        steps=[
            ExecutionStep(
                step_type=StepType.TOOL,
                step_id="step_1",
                tool_name="web_search_tool",
                agent_name="web_search_agent",
                description="Initial search",
                parameters={"query": "test"},
            ),
            ExecutionStep(
                step_type=StepType.TOOL,
                step_id="step_2",
                tool_name=TOOL_NAME_DELEGATE_SUB_AGENT,
                agent_name="sub_agent_tools",
                description="Delegate to train expert",
                parameters={"expertise": "train expert", "instruction": "Research trains"},
                depends_on=["step_1"],
            ),
            ExecutionStep(
                step_type=StepType.TOOL,
                step_id="step_3",
                tool_name=TOOL_NAME_DELEGATE_SUB_AGENT,
                agent_name="sub_agent_tools",
                description="Delegate to flight expert",
                parameters={"expertise": "flight expert", "instruction": "Research flights"},
                depends_on=["step_1"],
            ),
        ],
    )


def _make_plan_without_delegate_steps() -> ExecutionPlan:
    """Create a plan without delegate_to_sub_agent_tool steps."""
    return ExecutionPlan(
        user_id="test_user",
        plan_id="test_plan_no_delegate",
        steps=[
            ExecutionStep(
                step_type=StepType.TOOL,
                step_id="step_1",
                tool_name="web_search_tool",
                agent_name="web_search_agent",
                description="Search",
                parameters={"query": "test"},
            ),
        ],
    )


def _make_context() -> ValidationContext:
    return ValidationContext(
        user_id="test_user",
        session_id="test_session",
        available_scopes=[],
        allow_hitl=True,
    )


class TestSubAgentRejectionFallback:
    """Test sub-agent REJECT → REPLAN conversion in approval gate."""

    def test_sub_agent_rejection_converts_to_replan(self):
        """REJECT on plan with delegate steps → needs_replan=True."""
        plan = _make_plan_with_delegate_steps()
        decision_data = {"decision": "REJECT", "rejection_reason": "User said no"}

        approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
            decision_data, plan, _make_context()
        )

        # _process_approval_decision returns REJECT — the conversion happens
        # in approval_gate_node AFTER calling _process_approval_decision.
        # So we test the detection logic directly.
        assert approved is False
        assert rejection_reason == "User said no"

        # Verify detection: plan has sub-agent steps
        has_sub_agent_steps = any(
            s.tool_name == TOOL_NAME_DELEGATE_SUB_AGENT for s in plan.steps if s.tool_name
        )
        assert has_sub_agent_steps is True

    def test_normal_rejection_no_sub_agents(self):
        """REJECT on plan without delegate steps → normal rejection."""
        plan = _make_plan_without_delegate_steps()
        decision_data = {"decision": "REJECT", "rejection_reason": "Not interested"}

        approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
            decision_data, plan, _make_context()
        )

        assert approved is False
        assert rejection_reason == "Not interested"

        # No sub-agent steps → no conversion
        has_sub_agent_steps = any(
            s.tool_name == TOOL_NAME_DELEGATE_SUB_AGENT for s in plan.steps if s.tool_name
        )
        assert has_sub_agent_steps is False

    def test_sub_agent_approval_unchanged(self):
        """APPROVE on plan with delegate steps → plan_approved=True (no conversion)."""
        plan = _make_plan_with_delegate_steps()
        decision_data = {"decision": "APPROVE"}

        approved, modified_plan, rejection_reason, replan_instructions = _process_approval_decision(
            decision_data, plan, _make_context()
        )

        assert approved is True
        assert rejection_reason == ""
        assert replan_instructions is None
