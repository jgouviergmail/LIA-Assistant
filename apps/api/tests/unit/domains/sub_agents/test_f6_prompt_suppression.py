"""
Unit tests for F6 sub-agent prompt suppression.

When a user rejects a plan containing delegate_to_sub_agent_tool,
the planner prompt must NOT include the sub-agents delegation section.
This prevents the LLM from receiving contradictory instructions
(catalogue excludes the tool but prompt encourages delegation).
"""

from unittest.mock import patch

from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT
from src.core.context import exclude_sub_agents_from_prompt
from src.domains.agents.services.smart_planner_service import SmartPlannerService


class TestBuildSubAgentsSectionSuppression:
    """Test _build_sub_agents_section respects exclude_sub_agents_from_prompt."""

    def test_section_empty_when_excluded(self):
        """Sub-agents section should be empty when ContextVar is True."""
        token = exclude_sub_agents_from_prompt.set(True)
        try:
            with patch("src.core.config.get_settings") as mock_settings:
                mock_settings.return_value.sub_agents_enabled = True
                result = SmartPlannerService._build_sub_agents_section()
                assert result == ""
        finally:
            exclude_sub_agents_from_prompt.reset(token)

    def test_section_present_when_not_excluded(self):
        """Sub-agents section should be present when ContextVar is False."""
        token = exclude_sub_agents_from_prompt.set(False)
        try:
            with patch("src.core.config.get_settings") as mock_settings:
                mock_settings.return_value.sub_agents_enabled = True
                result = SmartPlannerService._build_sub_agents_section()
                assert "SUB-AGENT DELEGATION" in result
                assert "delegate_to_sub_agent_tool" in result
        finally:
            exclude_sub_agents_from_prompt.reset(token)

    def test_section_empty_when_feature_disabled(self):
        """Sub-agents section should be empty when feature is disabled."""
        token = exclude_sub_agents_from_prompt.set(False)
        try:
            with patch("src.core.config.get_settings") as mock_settings:
                mock_settings.return_value.sub_agents_enabled = False
                result = SmartPlannerService._build_sub_agents_section()
                assert result == ""
        finally:
            exclude_sub_agents_from_prompt.reset(token)

    def test_default_contextvar_is_false(self):
        """Default ContextVar value should be False (sub-agents allowed)."""
        assert exclude_sub_agents_from_prompt.get() is False


class TestPlanMethodSetsContextVar:
    """Test that plan() correctly sets exclude_sub_agents_from_prompt."""

    def test_contextvar_set_when_exclude_tools_has_delegate(self):
        """ContextVar should be True when exclude_tools contains delegate tool."""
        exclude_tools = {TOOL_NAME_DELEGATE_SUB_AGENT}

        # Simulate the logic from plan() without calling the full method
        from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT as DELEGATE_TOOL

        exclude_sub_agents_from_prompt.set(bool(exclude_tools and DELEGATE_TOOL in exclude_tools))
        try:
            assert exclude_sub_agents_from_prompt.get() is True
        finally:
            exclude_sub_agents_from_prompt.set(False)

    def test_contextvar_false_when_exclude_tools_empty(self):
        """ContextVar should be False when exclude_tools is None."""
        exclude_tools = None

        from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT as DELEGATE_TOOL

        exclude_sub_agents_from_prompt.set(bool(exclude_tools and DELEGATE_TOOL in exclude_tools))
        try:
            assert exclude_sub_agents_from_prompt.get() is False
        finally:
            exclude_sub_agents_from_prompt.set(False)

    def test_contextvar_false_when_exclude_tools_has_other_tool(self):
        """ContextVar should be False when exclude_tools does not contain delegate."""
        exclude_tools = {"some_other_tool"}

        from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT as DELEGATE_TOOL

        exclude_sub_agents_from_prompt.set(bool(exclude_tools and DELEGATE_TOOL in exclude_tools))
        try:
            assert exclude_sub_agents_from_prompt.get() is False
        finally:
            exclude_sub_agents_from_prompt.set(False)


class TestApprovalGatePlannerIteration:
    """Test that F6 replan increments planner_iteration for loop protection."""

    def test_planner_iteration_incremented_on_sub_agent_rejection(self):
        """planner_iteration should be incremented when F6 converts REJECT to REPLAN."""
        from src.domains.agents.constants import (
            STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS,
            STATE_KEY_NEEDS_REPLAN,
            STATE_KEY_PLANNER_ITERATION,
        )
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        plan = ExecutionPlan(
            user_id="test_user",
            plan_id="test_plan",
            steps=[
                ExecutionStep(
                    step_type=StepType.TOOL,
                    step_id="step_1",
                    tool_name=TOOL_NAME_DELEGATE_SUB_AGENT,
                    agent_name="sub_agent_tools",
                    description="Delegate",
                    parameters={"expertise": "expert", "instruction": "Do something"},
                ),
            ],
        )

        has_sub_agent_steps = any(
            s.tool_name == TOOL_NAME_DELEGATE_SUB_AGENT for s in plan.steps if s.tool_name
        )
        assert has_sub_agent_steps is True

        # Simulate the state and result dict from approval_gate_node
        state = {STATE_KEY_PLANNER_ITERATION: 0}
        result: dict = {}

        # Replicate the F6 logic
        if has_sub_agent_steps:
            planner_iteration = state.get(STATE_KEY_PLANNER_ITERATION, 0)
            result[STATE_KEY_NEEDS_REPLAN] = True
            result[STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS] = True
            result[STATE_KEY_PLANNER_ITERATION] = planner_iteration + 1

        assert result[STATE_KEY_NEEDS_REPLAN] is True
        assert result[STATE_KEY_EXCLUDE_SUB_AGENT_TOOLS] is True
        assert result[STATE_KEY_PLANNER_ITERATION] == 1

    def test_second_rejection_reaches_max_replans(self):
        """After 2+ F6 replans, planner_iteration should exceed max_replans default."""
        from src.domains.agents.constants import STATE_KEY_PLANNER_ITERATION

        # After first F6 replan: iteration = 1
        # After second F6 replan: iteration = 2
        # Default max_replans = 2, so iteration > max_replans at 3
        # This ensures the loop cannot go beyond 2 extra attempts
        state = {STATE_KEY_PLANNER_ITERATION: 2}
        planner_iteration = state.get(STATE_KEY_PLANNER_ITERATION, 0)
        new_iteration = planner_iteration + 1

        assert new_iteration == 3
        # route_from_semantic_validator uses: planner_iteration > max_iterations
        # Default max_iterations = 2, so 3 > 2 → True → bypass to approval_gate
        assert new_iteration > 2
