"""
Tests for PlanValidator (Phase 3).

This module tests the plan validator that relies on catalogue manifests
to validate plans before execution.

Coverage target: 95% on validator.py
"""

import pytest

from src.domains.agents.orchestration.validator import (
    PlanValidator,
    ValidationContext,
    ValidationResult,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.tools.common import ToolErrorCode

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def registry():
    """Empty registry for tests"""
    return AgentRegistry(checkpointer=None, store=None)


@pytest.fixture
def sample_agent_manifest():
    """Agent manifest for tests"""
    return AgentManifest(
        name="test_agent",
        description="Test agent",
        tools=["tool_simple", "tool_with_constraints", "tool_hitl", "tool_expensive"],
        version="1.0.0",
    )


@pytest.fixture
def tool_simple():
    """Simple tool without constraints"""
    return ToolManifest(
        name="tool_simple",
        agent="test_agent",
        description="Simple tool for testing",
        parameters=[
            ParameterSchema(
                name="query",
                type="string",
                required=True,
                description="Search query",
            ),
            ParameterSchema(
                name="limit",
                type="integer",
                required=False,
                description="Max results",
            ),
        ],
        outputs=[],
        cost=CostProfile(
            est_tokens_in=100, est_tokens_out=200, est_cost_usd=0.01, est_latency_ms=300
        ),
        permissions=PermissionProfile(required_scopes=["test.read"]),
        version="1.0.0",
    )


@pytest.fixture
def tool_with_constraints():
    """Tool with Pydantic constraints"""
    return ToolManifest(
        name="tool_with_constraints",
        agent="test_agent",
        description="Tool with parameter constraints",
        parameters=[
            ParameterSchema(
                name="query",
                type="string",
                required=True,
                description="Search query",
                constraints=[ParameterConstraint(kind="min_length", value=1)],
            ),
            ParameterSchema(
                name="max_results",
                type="integer",
                required=True,
                description="Max results",
                constraints=[
                    ParameterConstraint(kind="minimum", value=1),
                    ParameterConstraint(kind="maximum", value=50),
                ],
            ),
            ParameterSchema(
                name="sort_order",
                type="string",
                required=False,
                description="Sort order",
                constraints=[ParameterConstraint(kind="enum", value=["ASC", "DESC"])],
            ),
        ],
        outputs=[],
        cost=CostProfile(est_cost_usd=0.02),
        permissions=PermissionProfile(required_scopes=["test.read"]),
        version="1.0.0",
    )


@pytest.fixture
def tool_hitl():
    """Tool requiring HITL"""
    return ToolManifest(
        name="tool_hitl",
        agent="test_agent",
        description="Tool requiring HITL approval",
        parameters=[
            ParameterSchema(
                name="action", type="string", required=True, description="Action to perform"
            ),
        ],
        outputs=[],
        cost=CostProfile(est_cost_usd=0.05),
        permissions=PermissionProfile(required_scopes=["test.write"], hitl_required=True),
        version="1.0.0",
    )


@pytest.fixture
def tool_expensive():
    """Expensive tool"""
    return ToolManifest(
        name="tool_expensive",
        agent="test_agent",
        description="Expensive tool",
        parameters=[
            ParameterSchema(
                name="data", type="string", required=True, description="Data to process"
            ),
        ],
        outputs=[],
        cost=CostProfile(est_cost_usd=0.50),
        permissions=PermissionProfile(required_scopes=["test.read"]),
        version="1.0.0",
    )


@pytest.fixture
def validator(
    registry, sample_agent_manifest, tool_simple, tool_with_constraints, tool_hitl, tool_expensive
):
    """Validator configured with test tools"""
    registry.register_agent_manifest(sample_agent_manifest)
    registry.register_tool_manifest(tool_simple)
    registry.register_tool_manifest(tool_with_constraints)
    registry.register_tool_manifest(tool_hitl)
    registry.register_tool_manifest(tool_expensive)
    return PlanValidator(registry)


@pytest.fixture
def basic_context():
    """Basic validation context"""
    return ValidationContext(
        user_id="user123",
        session_id="sess456",
        available_scopes=["test.read", "test.write"],
        user_roles=["user"],
        budget_usd=1.0,
        allow_hitl=True,
        max_steps=10,
    )


# ============================================================================
# Tests ValidationResult
# ============================================================================


class TestValidationResult:
    """Tests for ValidationResult"""

    def test_create_valid_result(self):
        """Test creating a valid result"""
        result = ValidationResult(is_valid=True, total_cost_usd=0.05, total_steps=2)
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert result.total_cost_usd == 0.05
        assert result.total_steps == 2

    def test_add_error_invalidates_result(self):
        """Test that adding an error invalidates the result"""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True

        result.add_error(
            code=ToolErrorCode.MISSING_REQUIRED_PARAM,
            message="Missing param",
            step_index=0,
            tool_name="tool_test",
        )

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].severity == "error"
        assert result.errors[0].code == ToolErrorCode.MISSING_REQUIRED_PARAM

    def test_add_warning_does_not_invalidate(self):
        """Test that adding a warning does not invalidate the result"""
        result = ValidationResult(is_valid=True)
        result.add_warning(
            code=ToolErrorCode.EMPTY_RESULT,
            message="Empty result",
            step_index=0,
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
        assert result.warnings[0].severity == "warning"


# ============================================================================
# Tests PlanValidator - Structure
# ============================================================================


class TestPlanValidatorStructure:
    """Tests for plan structure validation"""

    def test_validate_empty_plan_invalid(self, validator, basic_context):
        """Test that empty plan is invalid"""
        result = validator.validate_plan({}, basic_context)
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].code == ToolErrorCode.INVALID_INPUT

    def test_validate_plan_missing_steps(self, validator, basic_context):
        """Test that plan without 'steps' is invalid"""
        plan = {"other_field": "value"}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert "steps" in result.errors[0].message.lower()

    def test_validate_plan_steps_not_list(self, validator, basic_context):
        """Test that plan with non-list 'steps' is invalid"""
        plan = {"steps": "not a list"}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert "list" in result.errors[0].message.lower()

    def test_validate_plan_exceeds_max_steps(self, validator, basic_context):
        """Test that plan exceeding max_steps is invalid"""
        basic_context.max_steps = 2
        plan = {
            "steps": [
                {"tool": "tool_simple", "args": {"query": "test"}},
                {"tool": "tool_simple", "args": {"query": "test"}},
                {"tool": "tool_simple", "args": {"query": "test"}},  # 3 > 2
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert result.total_steps == 3
        assert any("max steps" in err.message.lower() for err in result.errors)

    def test_validate_step_not_dict(self, validator, basic_context):
        """Test that non-dict step is invalid"""
        plan = {"steps": ["not a dict"]}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert "dict" in result.errors[0].message.lower()

    def test_validate_step_missing_tool(self, validator, basic_context):
        """Test that step without 'tool' is invalid"""
        plan = {"steps": [{"args": {"query": "test"}}]}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert "tool" in result.errors[0].message.lower()

    def test_validate_tool_not_found(self, validator, basic_context):
        """Test that non-existent tool is invalid"""
        plan = {"steps": [{"tool": "nonexistent_tool", "args": {}}]}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert result.errors[0].code == ToolErrorCode.NOT_FOUND
        assert "nonexistent_tool" in result.errors[0].message


# ============================================================================
# Tests PlanValidator - Parameters
# ============================================================================


class TestPlanValidatorParameters:
    """Tests for parameter validation"""

    def test_validate_missing_required_param(self, validator, basic_context):
        """Test missing required parameter"""
        plan = {"steps": [{"tool": "tool_simple", "args": {}}]}  # Missing required 'query'
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert any(err.code == ToolErrorCode.MISSING_REQUIRED_PARAM for err in result.errors)
        assert any("query" in err.message for err in result.errors)

    def test_validate_unknown_param_warning(self, validator, basic_context):
        """Test that unknown parameter generates a warning"""
        plan = {
            "steps": [{"tool": "tool_simple", "args": {"query": "test", "unknown_param": "value"}}]
        }
        result = validator.validate_plan(plan, basic_context)
        # Should still be valid (warning only)
        assert result.is_valid is True
        assert len(result.warnings) == 1
        assert "unknown_param" in result.warnings[0].message

    def test_validate_param_type_mismatch(self, validator, basic_context):
        """Test incorrect parameter type"""
        plan = {
            "steps": [{"tool": "tool_simple", "args": {"query": "test", "limit": "not an int"}}]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert any("type" in err.message.lower() for err in result.errors)

    def test_validate_min_length_constraint(self, validator, basic_context):
        """Test min_length constraint"""
        plan = {
            "steps": [{"tool": "tool_with_constraints", "args": {"query": "", "max_results": 10}}]
        }  # empty query
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert any(err.code == ToolErrorCode.CONSTRAINT_VIOLATION for err in result.errors)

    def test_validate_minimum_constraint(self, validator, basic_context):
        """Test minimum constraint"""
        plan = {
            "steps": [
                {"tool": "tool_with_constraints", "args": {"query": "test", "max_results": 0}}
            ]  # < 1 minimum
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert any("min" in err.message.lower() for err in result.errors)

    def test_validate_maximum_constraint(self, validator, basic_context):
        """Test maximum constraint"""
        plan = {
            "steps": [
                {"tool": "tool_with_constraints", "args": {"query": "test", "max_results": 100}}
            ]  # > 50 max
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert any("max" in err.message.lower() for err in result.errors)

    def test_validate_enum_constraint_valid(self, validator, basic_context):
        """Test valid enum constraint"""
        plan = {
            "steps": [
                {
                    "tool": "tool_with_constraints",
                    "args": {"query": "test", "max_results": 10, "sort_order": "ASC"},
                }
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is True

    def test_validate_enum_constraint_invalid(self, validator, basic_context):
        """Test invalid enum constraint"""
        plan = {
            "steps": [
                {
                    "tool": "tool_with_constraints",
                    "args": {"query": "test", "max_results": 10, "sort_order": "INVALID"},
                }
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert any("allowed values" in err.message.lower() for err in result.errors)

    def test_validate_reference_param_skipped(self, validator, basic_context):
        """Test that parameters with references ($steps.X) are skipped"""
        plan = {
            "steps": [
                {"tool": "tool_simple", "args": {"query": "test"}},
                {"tool": "tool_simple", "args": {"query": "$steps.0.result"}},  # Référence
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        # Should be valid - reference validation is orchestrator's job
        assert result.is_valid is True


# ============================================================================
# Tests PlanValidator - Permissions
# ============================================================================


class TestPlanValidatorPermissions:
    """Tests for permission validation"""

    def test_validate_missing_scope(self, validator, basic_context):
        """Test that missing scope is invalid"""
        basic_context.available_scopes = []  # No scopes
        plan = {"steps": [{"tool": "tool_simple", "args": {"query": "test"}}]}  # Requires test.read
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert any(err.code == ToolErrorCode.UNAUTHORIZED for err in result.errors)
        assert any("scope" in err.message.lower() for err in result.errors)

    def test_validate_sufficient_scopes(self, validator, basic_context):
        """Test that sufficient scopes are valid"""
        basic_context.available_scopes = ["test.read", "test.write", "other.scope"]
        plan = {"steps": [{"tool": "tool_simple", "args": {"query": "test"}}]}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is True


# ============================================================================
# Tests PlanValidator - Cost & Budget
# ============================================================================


class TestPlanValidatorCost:
    """Tests for cost validation"""

    def test_validate_plan_within_budget(self, validator, basic_context):
        """Test that plan within budget is valid"""
        basic_context.budget_usd = 1.0
        plan = {
            "steps": [
                {"tool": "tool_simple", "args": {"query": "test"}},  # 0.01 USD
                {
                    "tool": "tool_with_constraints",
                    "args": {"query": "test", "max_results": 10},
                },  # 0.02 USD
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is True
        assert result.total_cost_usd == 0.03

    def test_validate_plan_exceeds_budget(self, validator, basic_context):
        """Test that plan exceeding budget is invalid"""
        basic_context.budget_usd = 0.1
        plan = {
            "steps": [
                {"tool": "tool_expensive", "args": {"data": "test"}},  # 0.50 USD > 0.1 budget
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert result.total_cost_usd == 0.50
        assert any("budget" in err.message.lower() for err in result.errors)

    def test_validate_no_budget_limit(self, validator, basic_context):
        """Test that no budget limit accepts everything"""
        basic_context.budget_usd = None  # No limit
        plan = {
            "steps": [
                {"tool": "tool_expensive", "args": {"data": "test"}},  # 0.50 USD
                {"tool": "tool_expensive", "args": {"data": "test"}},  # 0.50 USD
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is True
        assert result.total_cost_usd == 1.0


# ============================================================================
# Tests PlanValidator - HITL
# ============================================================================


class TestPlanValidatorHITL:
    """Tests for HITL validation"""

    def test_validate_hitl_required_allowed(self, validator, basic_context):
        """Test that required and allowed HITL is valid"""
        basic_context.allow_hitl = True
        plan = {"steps": [{"tool": "tool_hitl", "args": {"action": "test"}}]}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is True
        assert result.requires_hitl is True

    def test_validate_hitl_required_not_allowed(self, validator, basic_context):
        """Test that required but disallowed HITL is invalid"""
        basic_context.allow_hitl = False
        plan = {"steps": [{"tool": "tool_hitl", "args": {"action": "test"}}]}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        assert result.requires_hitl is True
        assert any(err.code == ToolErrorCode.FORBIDDEN for err in result.errors)
        assert any("hitl" in err.message.lower() for err in result.errors)

    def test_validate_no_hitl_required(self, validator, basic_context):
        """Test plan without HITL"""
        plan = {"steps": [{"tool": "tool_simple", "args": {"query": "test"}}]}
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is True
        assert result.requires_hitl is False


# ============================================================================
# Tests PlanValidator - Integration
# ============================================================================


class TestPlanValidatorIntegration:
    """Full integration tests"""

    def test_validate_complex_valid_plan(self, validator, basic_context):
        """Test valid complex plan"""
        plan = {
            "steps": [
                {"tool": "tool_simple", "args": {"query": "search term", "limit": 10}},
                {
                    "tool": "tool_with_constraints",
                    "args": {"query": "another search", "max_results": 20, "sort_order": "DESC"},
                },
                {"tool": "tool_simple", "args": {"query": "$steps.0.result"}},  # Référence
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is True
        assert result.total_steps == 3
        assert result.total_cost_usd == 0.04  # 0.01 + 0.02 + 0.01
        assert result.requires_hitl is False

    def test_validate_complex_invalid_plan_multiple_errors(self, validator, basic_context):
        """Test complex plan with multiple errors"""
        basic_context.available_scopes = []  # No scopes
        basic_context.budget_usd = 0.01  # Budget too small

        plan = {
            "steps": [
                {"tool": "tool_simple", "args": {}},  # Missing required query
                {
                    "tool": "tool_with_constraints",
                    "args": {"query": "", "max_results": 100},
                },  # Constraints violated
                {"tool": "tool_expensive", "args": {"data": "test"}},  # Exceeds budget
            ]
        }
        result = validator.validate_plan(plan, basic_context)
        assert result.is_valid is False
        # Should have multiple errors:
        # - Missing required param 'query' in step 0
        # - Missing scopes for all steps
        # - min_length violation in step 1
        # - maximum violation in step 1
        # - Budget exceeded
        assert len(result.errors) >= 5

    def test_validate_plan_logging(self, validator, basic_context, caplog):
        """Test validation logging"""
        import logging

        plan = {"steps": [{"tool": "tool_simple", "args": {"query": "test"}}]}

        with caplog.at_level(logging.INFO):
            result = validator.validate_plan(plan, basic_context)

        assert result.is_valid is True
        # Verify log was created
        assert any("plan_validated" in record.message for record in caplog.records)


# ============================================================================
# Tests PlanValidator - HUMAN Step Type (StepType.HUMAN)
# ============================================================================


class TestPlanValidatorHUMANStepType:
    """Tests for StepType.HUMAN validation in ExecutionPlan.

    StepType.HUMAN is used for HITL (Human-In-The-Loop) approval workflows,
    such as confirming before sending an email.
    """

    @pytest.fixture
    def execution_plan_validator(self, registry, sample_agent_manifest, tool_simple, tool_hitl):
        """Validator setup with ExecutionPlan-compatible registry."""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(tool_simple)
        registry.register_tool_manifest(tool_hitl)
        return PlanValidator(registry)

    def test_human_step_sets_requires_hitl(self, execution_plan_validator, basic_context):
        """Test that HUMAN step marks plan as requiring HITL."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        step = ExecutionStep(
            step_id="confirm",
            step_type=StepType.HUMAN,
            description="User confirmation required",
        )
        plan = ExecutionPlan(user_id="user_123", steps=[step])

        basic_context.allow_hitl = True
        result = execution_plan_validator.validate_execution_plan(plan, basic_context)

        assert result.is_valid is True
        assert result.requires_hitl is True

    def test_human_step_allowed_when_hitl_enabled(self, execution_plan_validator, basic_context):
        """Test HUMAN step validates successfully when HITL is allowed."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        step = ExecutionStep(
            step_id="approval",
            step_type=StepType.HUMAN,
            description="Awaiting user approval",
        )
        plan = ExecutionPlan(user_id="user_123", steps=[step])

        basic_context.allow_hitl = True
        result = execution_plan_validator.validate_execution_plan(plan, basic_context)

        assert result.is_valid is True

    def test_human_step_rejected_when_hitl_disabled(self, execution_plan_validator, basic_context):
        """Test HUMAN step fails validation when HITL is not allowed."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        step = ExecutionStep(
            step_id="approval",
            step_type=StepType.HUMAN,
            description="Awaiting user approval",
        )
        plan = ExecutionPlan(user_id="user_123", steps=[step])

        basic_context.allow_hitl = False
        result = execution_plan_validator.validate_execution_plan(plan, basic_context)

        assert result.is_valid is False
        assert result.requires_hitl is True
        assert any(err.code == ToolErrorCode.FORBIDDEN for err in result.errors)

    def test_human_step_with_dependencies(self, execution_plan_validator, basic_context):
        """Test HUMAN step with dependencies on earlier steps."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        step1 = ExecutionStep(
            step_id="search",
            step_type=StepType.TOOL,
            agent_name="test_agent",
            tool_name="tool_simple",
            parameters={"query": "test"},
        )
        step2 = ExecutionStep(
            step_id="confirm",
            step_type=StepType.HUMAN,
            description="Confirm before proceeding",
            depends_on=["search"],
        )
        plan = ExecutionPlan(user_id="user_123", steps=[step1, step2])

        basic_context.allow_hitl = True
        result = execution_plan_validator.validate_execution_plan(plan, basic_context)

        assert result.is_valid is True
        assert result.requires_hitl is True

    def test_multiple_human_steps(self, execution_plan_validator, basic_context):
        """Test plan with multiple HUMAN steps."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        step1 = ExecutionStep(
            step_id="confirm_1",
            step_type=StepType.HUMAN,
            description="First confirmation",
        )
        step2 = ExecutionStep(
            step_id="confirm_2",
            step_type=StepType.HUMAN,
            description="Second confirmation",
            depends_on=["confirm_1"],
        )
        plan = ExecutionPlan(user_id="user_123", steps=[step1, step2])

        basic_context.allow_hitl = True
        result = execution_plan_validator.validate_execution_plan(plan, basic_context)

        assert result.is_valid is True
        assert result.requires_hitl is True

    def test_mixed_tool_and_human_steps(self, execution_plan_validator, basic_context):
        """Test plan with mix of TOOL and HUMAN steps (typical email send flow)."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        step1 = ExecutionStep(
            step_id="search",
            step_type=StepType.TOOL,
            agent_name="test_agent",
            tool_name="tool_simple",
            parameters={"query": "recipient"},
        )
        step2 = ExecutionStep(
            step_id="confirm",
            step_type=StepType.HUMAN,
            description="Confirm email send",
            depends_on=["search"],
        )
        step3 = ExecutionStep(
            step_id="send",
            step_type=StepType.TOOL,
            agent_name="test_agent",
            tool_name="tool_hitl",
            parameters={"action": "send"},
            depends_on=["confirm"],
        )
        plan = ExecutionPlan(user_id="user_123", steps=[step1, step2, step3])

        basic_context.allow_hitl = True
        result = execution_plan_validator.validate_execution_plan(plan, basic_context)

        assert result.is_valid is True
        assert result.requires_hitl is True

    def test_replan_step_rejected(self, execution_plan_validator, basic_context):
        """Test that REPLAN step type is rejected (not implemented in MVP)."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        step = ExecutionStep(
            step_id="replan",
            step_type=StepType.REPLAN,
            description="Regenerate plan",
        )
        plan = ExecutionPlan(user_id="user_123", steps=[step])

        result = execution_plan_validator.validate_execution_plan(plan, basic_context)

        assert result.is_valid is False
        assert any(err.code == ToolErrorCode.NOT_IMPLEMENTED for err in result.errors)


# ============================================================================
# Tests Jinja Template Type Validation Skip (Issue #dupond)
# ============================================================================


class TestJinjaTemplateValidation:
    """Tests for Jinja template type validation skip.

    When a parameter contains Jinja template syntax ({% %} or {{ }}),
    the validator should skip type validation because the actual type
    will only be determined at runtime after template evaluation.
    """

    @pytest.fixture
    def tool_with_array_param(self):
        """Tool with array parameter for testing Jinja template skip."""
        return ToolManifest(
            name="tool_array_param",
            agent="test_agent",
            description="Tool with array parameter",
            parameters=[
                ParameterSchema(
                    name="resource_names",
                    type="array",
                    required=True,
                    description="List of resource names",
                ),
            ],
            outputs=[],
            cost=CostProfile(est_cost_usd=0.01),
            permissions=PermissionProfile(required_scopes=["test.read"]),
            version="1.0.0",
        )

    @pytest.fixture
    def validator_with_array_tool(
        self,
        registry,
        sample_agent_manifest,
        tool_simple,
        tool_with_constraints,
        tool_hitl,
        tool_expensive,
        tool_with_array_param,
    ):
        """Validator with array parameter tool."""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(tool_simple)
        registry.register_tool_manifest(tool_with_constraints)
        registry.register_tool_manifest(tool_hitl)
        registry.register_tool_manifest(tool_expensive)
        registry.register_tool_manifest(tool_with_array_param)
        return PlanValidator(registry)

    def test_jinja_block_template_skips_type_validation(
        self, validator_with_array_tool, basic_context
    ):
        """Test that {% %} Jinja block syntax skips type validation.

        Even though resource_names expects an array, a Jinja template string
        should pass validation because the type will be determined at runtime.
        """
        plan = {
            "steps": [
                {
                    "tool": "tool_array_param",
                    "agent": "test_agent",
                    "parameters": {
                        "resource_names": "{% for g in steps.group.groups %}{{ g.resource_name }}{% endfor %}"
                    },
                }
            ],
        }

        result = validator_with_array_tool.validate_plan(plan, basic_context)

        # Should not fail due to type mismatch (string vs array)
        type_errors = [
            e
            for e in result.errors
            if "wrong type" in e.message.lower() and "resource_names" in e.message
        ]
        assert len(type_errors) == 0, f"Unexpected type error: {type_errors}"

    def test_jinja_expression_template_skips_type_validation(
        self, validator_with_array_tool, basic_context
    ):
        """Test that {{ }} Jinja expression syntax skips type validation."""
        plan = {
            "steps": [
                {
                    "tool": "tool_array_param",
                    "agent": "test_agent",
                    "parameters": {
                        "resource_names": "{{ steps.search.contacts | map(attribute='resource_name') | join(',') }}"
                    },
                }
            ],
        }

        result = validator_with_array_tool.validate_plan(plan, basic_context)

        type_errors = [
            e
            for e in result.errors
            if "wrong type" in e.message.lower() and "resource_names" in e.message
        ]
        assert len(type_errors) == 0, f"Unexpected type error: {type_errors}"

    def test_mixed_jinja_template_skips_type_validation(
        self, validator_with_array_tool, basic_context
    ):
        """Test complex Jinja template with both block and expression syntax."""
        plan = {
            "steps": [
                {
                    "tool": "tool_array_param",
                    "agent": "test_agent",
                    "parameters": {
                        "resource_names": (
                            "{% for g in steps.group.groups %}"
                            "{% if g.count > 0 %}"
                            "{% for item in g.members %}"
                            "{{ item.resource_name }}"
                            "{% if not loop.last %},{% endif %}"
                            "{% endfor %}"
                            "{% endif %}"
                            "{% endfor %}"
                        )
                    },
                }
            ],
        }

        result = validator_with_array_tool.validate_plan(plan, basic_context)

        type_errors = [
            e
            for e in result.errors
            if "wrong type" in e.message.lower() and "resource_names" in e.message
        ]
        assert len(type_errors) == 0, f"Unexpected type error: {type_errors}"

    def test_dollar_steps_reference_still_skips_validation(
        self, validator_with_array_tool, basic_context
    ):
        """Test that $steps.X references still skip validation (existing behavior)."""
        plan = {
            "steps": [
                {
                    "tool": "tool_array_param",
                    "agent": "test_agent",
                    "parameters": {"resource_names": "$steps.search.contacts"},
                }
            ],
        }

        result = validator_with_array_tool.validate_plan(plan, basic_context)

        type_errors = [
            e
            for e in result.errors
            if "wrong type" in e.message.lower() and "resource_names" in e.message
        ]
        assert len(type_errors) == 0, f"Unexpected type error: {type_errors}"

    def test_plain_string_still_fails_type_validation(
        self, validator_with_array_tool, basic_context
    ):
        """Test that plain strings without Jinja/$ still fail type validation.

        This ensures we only skip validation for dynamic references, not
        for all string values.
        """
        plan = {
            "steps": [
                {
                    "tool": "tool_array_param",
                    "agent": "test_agent",
                    "parameters": {"resource_names": "people/c123"},  # Plain string, no Jinja
                }
            ],
        }

        result = validator_with_array_tool.validate_plan(plan, basic_context)

        # Should fail because array expected, got plain string
        # The error message is "Parameter 'X' has wrong type: expected Y, got Z"
        type_errors = [
            e
            for e in result.errors
            if "wrong type" in e.message.lower() or "resource_names" in e.message
        ]
        assert len(type_errors) >= 1, (
            f"Should fail type validation for plain string. "
            f"Got errors: {[e.message for e in result.errors]}"
        )

    def test_array_value_still_passes_validation(self, validator_with_array_tool, basic_context):
        """Test that proper array values still pass validation."""
        plan = {
            "steps": [
                {
                    "tool": "tool_array_param",
                    "agent": "test_agent",
                    "parameters": {"resource_names": ["people/c123", "people/c456"]},
                }
            ],
        }

        result = validator_with_array_tool.validate_plan(plan, basic_context)

        type_errors = [
            e
            for e in result.errors
            if "wrong type" in e.message.lower() and "resource_names" in e.message
        ]
        assert len(type_errors) == 0, f"Unexpected type error for valid array: {type_errors}"
