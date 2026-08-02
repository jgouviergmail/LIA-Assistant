"""
Unit tests for plan_schemas.py - ExecutionPlan DSL and Structured Output schemas.

Phase 2 - Structured Output Migration:
Tests for ExecutionPlanLLMOutput schema used with get_structured_output().

Created: 2025-11-24
"""

import pytest
from pydantic import ValidationError

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionPlanLLMOutput,
    ExecutionStep,
    ExecutionStepLLM,
    ParameterItem,
    ParameterValue,
    PlanValidationError,
    StepType,
)

# ============================================================================
# ExecutionStep Tests
# ============================================================================


class TestExecutionStep:
    """Tests for ExecutionStep model."""

    def test_tool_step_creation(self):
        """Test creating a TOOL step with all required fields."""
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name="contacts_agent",
            tool_name="search_contacts_tool",
            parameters={"query": "John"},
            description="Search for contacts named John",
        )

        assert step.step_id == "step_1"
        assert step.step_type == StepType.TOOL
        assert step.agent_name == "contacts_agent"
        assert step.tool_name == "search_contacts_tool"
        assert step.parameters == {"query": "John"}
        assert step.description == "Search for contacts named John"

    def test_tool_step_requires_agent_name(self):
        """A TOOL step without an agent is refused AT CONSTRUCTION.

        It used to be accepted: Pydantic does not validate default values, so an
        omitted ``agent_name`` never reached its field validator. The previous
        version of this test enshrined that as "by design — plan-level validation
        catches issues"; measured, the plan accepted it too, so nothing caught it.

        It was not harmless. On the way back from a checkpoint the field IS
        passed explicitly as None, the validator fires, the constructor raises,
        and the step degrades to a plain dict with no error surfaced — after
        which `parallel_executor` reads `step.step_id` and dies. Refusing the
        object up front turns a silent corruption into an immediate, located
        failure (ADR-195).
        """
        with pytest.raises(ValidationError, match="agent_name"):
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                tool_name="search_contacts_tool",
            )

    def test_tool_step_refuses_an_explicitly_null_agent_name(self):
        """Omitted and explicitly-None must behave identically.

        The old field validator only caught the second one — the asymmetry is
        exactly what let the defect through.
        """
        with pytest.raises(ValidationError, match="agent_name"):
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name=None,
                tool_name="search_contacts_tool",
            )

    def test_a_non_tool_step_needs_neither_agent_nor_tool(self):
        """The rule is scoped to TOOL steps and must not leak to the others."""
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.CONDITIONAL,
            condition="$steps.step_0.success",
        )

        assert step.agent_name is None
        assert step.tool_name is None

    def test_a_valid_tool_step_survives_a_checkpoint_round_trip(self):
        """The property the rule protects, end to end.

        Pinned here and not only in the checkpoint guard: this is the reason the
        rule exists, and a reader of this model should see it.
        """
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        from src.domains.conversations.checkpointer import _CHECKPOINT_ALLOWED_MODULES

        serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
        plan = ExecutionPlan(
            plan_id="p1",
            user_id="u1",
            session_id="s1",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="contacts_agent",
                    tool_name="search_contacts_tool",
                )
            ],
        )

        restored = serde.loads_typed(serde.dumps_typed(plan))

        assert isinstance(restored.steps[0], ExecutionStep)

    def test_tool_step_requires_tool_name(self):
        """Same rule, other field: a TOOL step with no tool is refused."""
        with pytest.raises(ValidationError, match="tool_name"):
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
            )

    def test_a_tool_step_missing_both_reports_both(self):
        """One message naming every missing field beats fixing them one by one."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionStep(step_id="step_1", step_type=StepType.TOOL)

        message = str(exc_info.value)
        assert "agent_name" in message
        assert "tool_name" in message
        assert "step_1" in message, "the message must locate the offending step"

    def test_conditional_step_creation(self):
        """Test creating a CONDITIONAL step."""
        step = ExecutionStep(
            step_id="step_2",
            step_type=StepType.CONDITIONAL,
            condition="len($steps.step_1.contacts) > 0",
            on_success="step_3",
            on_fail="step_4",
            depends_on=["step_1"],
        )

        assert step.step_type == StepType.CONDITIONAL
        assert step.condition == "len($steps.step_1.contacts) > 0"
        assert step.on_success == "step_3"
        assert step.on_fail == "step_4"

    def test_conditional_step_requires_condition(self):
        """A CONDITIONAL step with nothing to evaluate is refused too.

        Its field validator had the same blind spot as the TOOL ones: an omitted
        `condition` never reached it.
        """
        with pytest.raises(ValidationError, match="condition"):
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.CONDITIONAL,
            )

    def test_step_id_validation_not_empty(self):
        """Test that step_id cannot be empty."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionStep(
                step_id="",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts_tool",
            )

        assert "step_id" in str(exc_info.value)

    def test_step_id_validation_no_spaces(self):
        """Test that step_id cannot contain spaces."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionStep(
                step_id="step 1",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts_tool",
            )

        assert "step_id" in str(exc_info.value)

    def test_step_with_dependencies(self):
        """Test step with depends_on list."""
        step = ExecutionStep(
            step_id="step_3",
            step_type=StepType.TOOL,
            agent_name="contacts_agent",
            tool_name="get_contact_details_tool",
            parameters={"resource_name": "$steps.step_1.contacts[0].resource_name"},
            depends_on=["step_1", "step_2"],
        )

        assert step.depends_on == ["step_1", "step_2"]

    def test_step_with_timeout(self):
        """Test step with timeout configuration."""
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name="emails_agent",
            tool_name="search_emails_tool",
            timeout_seconds=30,
        )

        assert step.timeout_seconds == 30

    def test_step_with_approval_required(self):
        """Test step with HITL approval required."""
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name="emails_agent",
            tool_name="send_email_tool",
            approvals_required=True,
        )

        assert step.approvals_required is True

    def test_human_step_creation(self):
        """Test creating a HUMAN step for HITL approval workflows."""
        step = ExecutionStep(
            step_id="confirm_send",
            step_type=StepType.HUMAN,
            description="User confirmation required before sending email",
            depends_on=["step_1"],
        )

        assert step.step_id == "confirm_send"
        assert step.step_type == StepType.HUMAN
        assert step.description == "User confirmation required before sending email"
        assert step.depends_on == ["step_1"]
        # HUMAN steps don't need agent_name or tool_name
        assert step.agent_name is None
        assert step.tool_name is None

    def test_human_step_minimal(self):
        """Test creating a minimal HUMAN step."""
        step = ExecutionStep(
            step_id="approval",
            step_type=StepType.HUMAN,
        )

        assert step.step_type == StepType.HUMAN
        assert step.agent_name is None
        assert step.tool_name is None
        assert step.condition is None

    def test_human_step_with_timeout(self):
        """Test HUMAN step with timeout for user response."""
        step = ExecutionStep(
            step_id="user_approval",
            step_type=StepType.HUMAN,
            description="Awaiting user approval",
            timeout_seconds=300,  # 5 minute timeout for user to respond
        )

        assert step.step_type == StepType.HUMAN
        assert step.timeout_seconds == 300

    def test_replan_step_creation(self):
        """Test creating a REPLAN step (Phase 2 - currently not fully supported)."""
        step = ExecutionStep(
            step_id="replan_step",
            step_type=StepType.REPLAN,
            description="Regenerate plan based on new context",
        )

        assert step.step_type == StepType.REPLAN
        assert step.description == "Regenerate plan based on new context"


# ============================================================================
# ExecutionPlan Tests
# ============================================================================


class TestExecutionPlan:
    """Tests for ExecutionPlan model."""

    def test_execution_plan_minimal(self):
        """Test ExecutionPlan with minimal required fields."""
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name="contacts_agent",
            tool_name="search_contacts_tool",
        )

        plan = ExecutionPlan(
            user_id="user_123",
            steps=[step],
        )

        assert plan.user_id == "user_123"
        assert len(plan.steps) == 1
        assert plan.execution_mode == "sequential"  # Default
        assert plan.version == "1.0.0"  # Default
        assert plan.plan_id  # Auto-generated UUID

    def test_execution_plan_requires_at_least_one_step(self):
        """Test that plan must have at least one step."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlan(user_id="user_123", steps=[])

        assert "Plan must contain at least one step" in str(exc_info.value)

    def test_execution_plan_unique_step_ids(self):
        """Test that step_ids must be unique."""
        step1 = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name="contacts_agent",
            tool_name="search_contacts_tool",
        )
        step2 = ExecutionStep(
            step_id="step_1",  # Duplicate!
            step_type=StepType.TOOL,
            agent_name="emails_agent",
            tool_name="search_emails_tool",
        )

        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlan(user_id="user_123", steps=[step1, step2])

        assert "Duplicate step_ids" in str(exc_info.value)

    def test_execution_plan_max_cost_validation(self):
        """Test that max_cost_usd must be positive."""
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name="contacts_agent",
            tool_name="search_contacts_tool",
        )

        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlan(user_id="user_123", steps=[step], max_cost_usd=-1.0)

        assert "max_cost_usd" in str(exc_info.value)

    def test_execution_plan_estimated_cost_validation(self):
        """Test that estimated_cost_usd must be positive."""
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name="contacts_agent",
            tool_name="search_contacts_tool",
        )

        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlan(user_id="user_123", steps=[step], estimated_cost_usd=-0.5)

        assert "estimated_cost_usd" in str(exc_info.value)


# ============================================================================
# ExecutionPlanLLMOutput Tests (Phase 2 - Structured Output)
# ============================================================================


def _create_llm_step(
    step_id: str,
    agent_name: str = "contacts_agent",
    tool_name: str = "search_contacts_tool",
    parameters: dict | None = None,
    step_type: StepType = StepType.TOOL,
) -> ExecutionStepLLM:
    """Helper to create ExecutionStepLLM with correct parameter format."""
    param_items = []
    if parameters:
        for k, v in parameters.items():
            param_items.append(
                ParameterItem(
                    name=k,
                    value=ParameterValue(string_value=str(v), value_type="string"),
                )
            )
    return ExecutionStepLLM(
        step_id=step_id,
        step_type=step_type,
        agent_name=agent_name,
        tool_name=tool_name,
        parameters=param_items,
    )


class TestExecutionPlanLLMOutput:
    """Tests for ExecutionPlanLLMOutput schema used with get_structured_output().

    Note: ExecutionPlanLLMOutput uses ExecutionStepLLM (with list[ParameterItem])
    for OpenAI strict mode compatibility, NOT ExecutionStep (with dict[str, Any]).
    """

    def test_llm_output_minimal(self):
        """Test ExecutionPlanLLMOutput with minimal fields."""
        step = _create_llm_step("step_1")

        output = ExecutionPlanLLMOutput(steps=[step])

        assert len(output.steps) == 1
        assert output.execution_mode == "sequential"  # Default
        assert output.estimated_cost_usd == 0.0  # Default

    def test_llm_output_requires_steps(self):
        """Test that ExecutionPlanLLMOutput requires at least one step."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlanLLMOutput(steps=[])

        assert "Plan must contain at least one step" in str(exc_info.value)

    def test_llm_output_unique_step_ids(self):
        """Test that step_ids must be unique in LLM output."""
        step1 = _create_llm_step("step_1", agent_name="contacts_agent")
        step2 = _create_llm_step(
            "step_1", agent_name="emails_agent", tool_name="search_emails_tool"
        )

        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlanLLMOutput(steps=[step1, step2])

        assert "Duplicate step_ids" in str(exc_info.value)

    def test_llm_output_estimated_cost_validation(self):
        """Test that estimated_cost_usd must be non-negative."""
        step = _create_llm_step("step_1")

        with pytest.raises(ValidationError) as exc_info:
            ExecutionPlanLLMOutput(steps=[step], estimated_cost_usd=-0.1)

        assert "estimated_cost_usd" in str(exc_info.value)

    def test_llm_output_to_execution_plan_basic(self):
        """Test conversion from LLM output to ExecutionPlan."""
        step = _create_llm_step("step_1", parameters={"query": "John"})

        llm_output = ExecutionPlanLLMOutput(
            steps=[step],
            execution_mode="sequential",
            estimated_cost_usd=0.05,
        )

        plan = llm_output.to_execution_plan(
            user_id="user_123",
            session_id="session_456",
        )

        # Verify injected fields
        assert plan.user_id == "user_123"
        assert plan.session_id == "session_456"
        assert plan.plan_id  # Should be generated UUID
        assert plan.version == "1.0.0"
        assert plan.created_at  # Should be set

        # Verify preserved fields
        assert len(plan.steps) == 1
        assert plan.steps[0].step_id == "step_1"
        assert plan.execution_mode == "sequential"
        assert plan.estimated_cost_usd == 0.05

    def test_llm_output_to_execution_plan_with_all_params(self):
        """Test conversion with all optional parameters."""
        step = _create_llm_step("step_1")

        llm_output = ExecutionPlanLLMOutput(steps=[step])

        plan = llm_output.to_execution_plan(
            user_id="user_123",
            session_id="session_456",
            max_cost_usd=1.0,
            max_timeout_seconds=120,
            metadata={"run_id": "run_789", "intention": "contacts_search"},
        )

        assert plan.max_cost_usd == 1.0
        assert plan.max_timeout_seconds == 120
        assert plan.metadata == {"run_id": "run_789", "intention": "contacts_search"}

    def test_llm_output_to_execution_plan_multiple_steps(self):
        """Test conversion with multiple steps."""
        step1 = _create_llm_step("step_1", parameters={"query": "John"})
        step2 = ExecutionStepLLM(
            step_id="step_2",
            step_type=StepType.TOOL,
            agent_name="contacts_agent",
            tool_name="get_contact_details_tool",
            parameters=[
                ParameterItem(
                    name="resource_name",
                    value=ParameterValue(
                        string_value="$steps.step_1.contacts[0].resource_name",
                        value_type="string",
                    ),
                )
            ],
            depends_on=["step_1"],
        )

        llm_output = ExecutionPlanLLMOutput(steps=[step1, step2])
        plan = llm_output.to_execution_plan(user_id="user_123")

        assert len(plan.steps) == 2
        assert plan.steps[0].step_id == "step_1"
        assert plan.steps[1].step_id == "step_2"
        assert plan.steps[1].depends_on == ["step_1"]
        # Verify parameters were converted to dict
        assert plan.steps[0].parameters == {"query": "John"}
        assert plan.steps[1].parameters == {
            "resource_name": "$steps.step_1.contacts[0].resource_name"
        }

    def test_llm_output_is_frozen(self):
        """Test that ExecutionPlanLLMOutput is immutable after creation."""
        step = _create_llm_step("step_1")

        llm_output = ExecutionPlanLLMOutput(steps=[step])

        # Should raise error when trying to modify frozen model
        with pytest.raises(ValidationError):
            llm_output.execution_mode = "parallel"

    def test_llm_output_generates_unique_plan_ids(self):
        """Test that each conversion generates a unique plan_id."""
        step = _create_llm_step("step_1")

        llm_output = ExecutionPlanLLMOutput(steps=[step])

        plan1 = llm_output.to_execution_plan(user_id="user_123")
        plan2 = llm_output.to_execution_plan(user_id="user_123")

        assert plan1.plan_id != plan2.plan_id

    def test_llm_output_json_schema_has_correct_fields(self):
        """Test that JSON schema only contains LLM-relevant fields."""
        schema = ExecutionPlanLLMOutput.model_json_schema()
        properties = schema.get("properties", {})

        # Should have these fields (LLM generates)
        assert "steps" in properties
        assert "execution_mode" in properties
        assert "estimated_cost_usd" in properties
        assert "metadata" in properties  # LLM can set needs_clarification/missing_parameters

        # Should NOT have these fields (injected at runtime)
        assert "user_id" not in properties
        assert "session_id" not in properties
        assert "plan_id" not in properties
        assert "created_at" not in properties
        assert "version" not in properties
        assert "max_cost_usd" not in properties
        assert "max_timeout_seconds" not in properties


# ============================================================================
# PlanValidationError Tests
# ============================================================================


class TestPlanValidationError:
    """Tests for PlanValidationError exception."""

    def test_plan_validation_error_basic(self):
        """Test PlanValidationError with message only."""
        error = PlanValidationError("Invalid step reference")

        assert str(error) == "Invalid step reference"
        assert error.message == "Invalid step reference"
        assert error.code == "VALIDATION_ERROR"  # Default
        assert error.details == {}  # Default

    def test_plan_validation_error_with_code(self):
        """Test PlanValidationError with custom code."""
        error = PlanValidationError("Tool not found", code="UNKNOWN_TOOL")

        assert error.code == "UNKNOWN_TOOL"

    def test_plan_validation_error_with_details(self):
        """Test PlanValidationError with details dict."""
        error = PlanValidationError(
            "Cyclic dependency detected",
            code="CYCLIC_DEPENDENCY",
            details={
                "cycle_path": ["step_1", "step_2", "step_1"],
                "affected_steps": ["step_1", "step_2"],
            },
        )

        assert error.code == "CYCLIC_DEPENDENCY"
        assert error.details["cycle_path"] == ["step_1", "step_2", "step_1"]
        assert error.details["affected_steps"] == ["step_1", "step_2"]

    def test_plan_validation_error_is_exception(self):
        """Test that PlanValidationError is a proper Exception."""
        error = PlanValidationError("Test error")

        assert isinstance(error, Exception)

        # Should be raisable
        with pytest.raises(PlanValidationError) as exc_info:
            raise error

        assert exc_info.value.message == "Test error"


class TestRequiredFieldsRegistry:
    """The table driving the rule must stay in sync with the model itself."""

    def test_every_step_type_has_an_entry(self):
        """ADR-085: an empty entry is a decision, an absent one is an oversight."""
        from src.domains.agents.orchestration.plan_schemas import _REQUIRED_FIELDS_BY_STEP_TYPE

        assert set(_REQUIRED_FIELDS_BY_STEP_TYPE) == set(StepType)

    def test_every_listed_field_exists_on_the_model(self):
        """A typo would make the field permanently 'missing'.

        The rule reads through ``getattr(..., None)``, so a misspelt name would
        never resolve and every step of that type would be rejected forever —
        with a message naming a field the model does not have.
        """
        from src.domains.agents.orchestration.plan_schemas import _REQUIRED_FIELDS_BY_STEP_TYPE

        listed = {field for fields in _REQUIRED_FIELDS_BY_STEP_TYPE.values() for field in fields}
        unknown = sorted(listed - set(ExecutionStep.model_fields))

        assert not unknown, f"required fields absent from ExecutionStep: {unknown}"
