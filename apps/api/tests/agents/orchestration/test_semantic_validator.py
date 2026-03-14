"""
Unit tests for PlanSemanticValidator (Phase 2.6 OPTIMPLAN).

Tests cover:
- SemanticIssueType enum
- SemanticIssue Pydantic model
- SemanticValidationOutput structured output
- SemanticValidationResult dataclass
- PlanSemanticValidator with:
  - Feature flag control
  - Short-circuit for trivial plans (≤1 step)
  - Timeout protection (optimistic fallback)
  - LLM validation with structured output
  - Error handling and fallback

Created: 2025-11-26
"""

import asyncio
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import SEMANTIC_VALIDATOR_PROMPT_VERSION_DEFAULT
from src.domains.agents.orchestration.semantic_validator import (
    PlanSemanticValidator,
    SemanticIssue,
    SemanticIssueType,
    SemanticValidationOutput,
    SemanticValidationResult,
)

# ============================================================================
# SemanticIssueType Tests
# ============================================================================


class TestSemanticIssueType:
    """Test suite for SemanticIssueType enum."""

    def test_all_types_defined(self):
        """Test that all expected issue types are defined."""
        assert SemanticIssueType.CARDINALITY_MISMATCH.value == "cardinality_mismatch"
        assert (
            SemanticIssueType.MISSING_DEPENDENCY.value == "ghost_dependency"
        )  # Alias for GHOST_DEPENDENCY
        assert SemanticIssueType.IMPLICIT_ASSUMPTION.value == "implicit_assumption"
        assert SemanticIssueType.SCOPE_OVERFLOW.value == "scope_overflow"
        assert SemanticIssueType.SCOPE_UNDERFLOW.value == "scope_underflow"
        assert (
            SemanticIssueType.AMBIGUOUS_INTENT.value == "dangerous_ambiguity"
        )  # Alias for DANGEROUS_AMBIGUITY

    def test_enum_membership(self):
        """Test enum membership operations."""
        assert "cardinality_mismatch" in [t.value for t in SemanticIssueType]
        # 15 unique types: 11 main + 4 for_each (aliases not counted in len)
        assert len(SemanticIssueType) == 15

    def test_for_each_missing_item_ref_defined(self):
        """Test that FOR_EACH_MISSING_ITEM_REF is defined."""
        assert SemanticIssueType.FOR_EACH_MISSING_ITEM_REF.value == "for_each_missing_item_ref"


# ============================================================================
# SemanticIssue Pydantic Model Tests
# ============================================================================


class TestSemanticIssue:
    """Test suite for SemanticIssue Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creation with only required fields."""
        issue = SemanticIssue(
            issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
            description="Plan does single op but user said 'pour chaque'",
        )

        assert issue.issue_type == SemanticIssueType.CARDINALITY_MISMATCH
        assert "pour chaque" in issue.description
        assert issue.affected_step_ids == []  # Default
        assert issue.severity == "medium"  # Default

    def test_create_with_all_fields(self):
        """Test creation with all fields."""
        issue = SemanticIssue(
            issue_type=SemanticIssueType.MISSING_DEPENDENCY,
            description="Step 2 needs data from step 1 but no depends_on",
            affected_step_ids=["step_1", "step_2"],
            severity="high",
        )

        assert issue.issue_type == SemanticIssueType.MISSING_DEPENDENCY
        assert issue.affected_step_ids == ["step_1", "step_2"]
        assert issue.severity == "high"

    def test_model_dump(self):
        """Test Pydantic model serialization."""
        issue = SemanticIssue(
            issue_type=SemanticIssueType.SCOPE_OVERFLOW,
            description="Plan does more than requested",
        )

        dumped = issue.model_dump()
        assert dumped["issue_type"] == "scope_overflow"
        assert "description" in dumped


# ============================================================================
# SemanticValidationOutput Tests
# ============================================================================


class TestSemanticValidationOutput:
    """Test suite for SemanticValidationOutput Pydantic model."""

    def test_create_valid_output(self):
        """Test creation for valid plan."""
        output = SemanticValidationOutput(
            is_valid=True,
            confidence=0.95,
            issues=[],
            reasoning="Plan correctly matches user request",
            clarification_questions=[],
        )

        assert output.is_valid is True
        assert output.confidence == 0.95
        assert output.issues == []
        assert output.clarification_questions == []

    def test_create_invalid_output_with_issues(self):
        """Test creation for invalid plan with issues."""
        issue = SemanticIssue(
            issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
            description="Mismatch detected",
        )

        output = SemanticValidationOutput(
            is_valid=False,
            confidence=0.85,
            issues=[issue],
            reasoning="Plan has cardinality issues",
            clarification_questions=["Voulez-vous UN ou TOUS les contacts ?"],
        )

        assert output.is_valid is False
        assert len(output.issues) == 1
        assert len(output.clarification_questions) == 1

    def test_confidence_bounds_validation(self):
        """Test that confidence must be between 0.0 and 1.0."""
        # Valid confidence
        output = SemanticValidationOutput(
            is_valid=True,
            confidence=0.5,
            issues=[],
            reasoning="OK",
            clarification_questions=[],
        )
        assert output.confidence == 0.5

        # Invalid confidence should raise ValidationError
        with pytest.raises(Exception):
            SemanticValidationOutput(
                is_valid=True,
                confidence=1.5,  # > 1.0
                issues=[],
                reasoning="OK",
                clarification_questions=[],
            )


# ============================================================================
# SemanticValidationResult Tests
# ============================================================================


class TestSemanticValidationResult:
    """Test suite for SemanticValidationResult dataclass."""

    def test_create_valid_result(self):
        """Test creation of valid result."""
        result = SemanticValidationResult(
            is_valid=True,
            issues=[],
            confidence=1.0,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.5,
            used_fallback=False,
        )

        assert result.is_valid is True
        assert result.used_fallback is False
        assert result.validation_duration_seconds == 0.5

    def test_create_fallback_result(self):
        """Test creation of fallback result."""
        result = SemanticValidationResult(
            is_valid=True,
            issues=[],
            confidence=0.5,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=1.0,
            used_fallback=True,
        )

        assert result.used_fallback is True
        assert result.confidence == 0.5

    def test_dataclass_conversion(self):
        """Test dataclass dict conversion."""
        result = SemanticValidationResult(
            is_valid=False,
            issues=[],
            confidence=0.7,
            requires_clarification=True,
            clarification_questions=["Question 1"],
            validation_duration_seconds=0.8,
            used_fallback=False,
        )

        result_dict = asdict(result)
        assert result_dict["is_valid"] is False
        assert result_dict["requires_clarification"] is True


# ============================================================================
# PlanSemanticValidator Tests
# ============================================================================


class TestPlanSemanticValidator:
    """Test suite for PlanSemanticValidator."""

    @pytest.fixture(autouse=True)
    def _bypass_pre_llm_checks(self):
        """Bypass pre-LLM validation checks for all tests in this class.

        These tests focus on LLM validation logic (timeout, fallback, prompt building).
        Insufficient content and for_each pattern detection are tested separately.
        """
        with (
            patch(
                "src.domains.agents.orchestration.semantic_validator.detect_insufficient_content",
                return_value=None,
            ),
            patch(
                "src.domains.agents.orchestration.semantic_validator.validate_for_each_patterns",
                return_value=(True, None, None),
            ),
        ):
            yield

    @pytest.fixture
    def mock_execution_plan(self):
        """Create mock execution plan with 3 steps."""
        from enum import Enum

        class MockStepType(str, Enum):
            TOOL = "TOOL"

        plan = MagicMock()
        plan.plan_id = "test-plan-123"
        plan.estimated_cost_usd = 0.002
        plan.execution_mode = "sequential"
        plan.metadata = {}
        plan.steps = [
            MagicMock(
                step_id="step_1",
                tool_name="search_contacts_tool",
                agent_name="contacts_agent",
                step_type=MockStepType.TOOL,
                description="Search contacts",
                parameters={"query": "test"},
                depends_on=[],
                condition=None,
                on_success=None,
                on_fail=None,
                approvals_required=False,
            ),
            MagicMock(
                step_id="step_2",
                tool_name="get_contact_details_tool",
                agent_name="contacts_agent",
                step_type=MockStepType.TOOL,
                description="Get contact details",
                parameters={"contact_id": "$step_1.id"},
                depends_on=["step_1"],
                condition=None,
                on_success=None,
                on_fail=None,
                approvals_required=False,
            ),
            MagicMock(
                step_id="step_3",
                tool_name="send_email_tool",
                agent_name="emails_agent",
                step_type=MockStepType.TOOL,
                description="Send email",
                parameters={"to": "$step_2.email", "subject": "Hello", "body": "Hi there"},
                depends_on=["step_2"],
                condition=None,
                on_success=None,
                on_fail=None,
                approvals_required=False,
            ),
        ]
        return plan

    @pytest.fixture
    def mock_trivial_plan(self):
        """Create mock execution plan with 1 step (trivial)."""
        plan = MagicMock()
        plan.plan_id = "trivial-plan"
        plan.steps = [
            MagicMock(
                step_id="step_1",
                tool_name="search_contacts_tool",
                parameters={"query": "test"},
            )
        ]
        return plan

    @pytest.mark.asyncio
    async def test_short_circuit_trivial_plan(self, mock_trivial_plan):
        """Test that plans with ≤1 step are instantly validated (short-circuit)."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 1.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                result = await validator.validate(
                    plan=mock_trivial_plan,
                    user_request="Simple request",
                    user_language="fr",
                )

                assert result.is_valid is True
                assert result.used_fallback is False
                # Short-circuit should be fast (allow 1s for first-run import overhead)
                assert result.validation_duration_seconds < 1.0

    @pytest.mark.asyncio
    async def test_timeout_fallback(self, mock_execution_plan):
        """Test that timeout triggers optimistic fallback."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 0.1  # Very short timeout
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                # Mock _validate_with_llm to take too long
                async def slow_validation(*args, **kwargs):
                    await asyncio.sleep(1.0)  # Longer than timeout
                    return SemanticValidationResult(
                        is_valid=True,
                        issues=[],
                        confidence=1.0,
                        requires_clarification=False,
                        clarification_questions=[],
                        validation_duration_seconds=1.0,
                        used_fallback=False,
                    )

                with patch.object(validator, "_validate_with_llm", slow_validation):
                    # Patch metrics at the import location inside the module
                    with patch(
                        "src.infrastructure.observability.metrics_agents.semantic_validation_timeout_total"
                    ):
                        result = await validator.validate(
                            plan=mock_execution_plan,
                            user_request="Test request",
                            user_language="fr",
                        )

                        # Should fallback to valid due to timeout
                        assert result.is_valid is True
                        assert result.used_fallback is True
                        assert result.confidence == 0.3  # Fallback confidence (timeout)

    @pytest.mark.asyncio
    async def test_error_fallback(self, mock_execution_plan):
        """Test that errors trigger optimistic fallback."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                # Mock _validate_with_llm to raise exception
                async def failing_validation(*args, **kwargs):
                    raise ValueError("LLM call failed")

                with patch.object(validator, "_validate_with_llm", failing_validation):
                    result = await validator.validate(
                        plan=mock_execution_plan,
                        user_request="Test request",
                        user_language="fr",
                    )

                    # Should fallback to valid due to error
                    assert result.is_valid is True
                    assert result.used_fallback is True

    @pytest.mark.asyncio
    async def test_successful_validation(self, mock_execution_plan):
        """Test successful LLM validation."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                # Mock successful validation
                mock_result = SemanticValidationResult(
                    is_valid=True,
                    issues=[],
                    confidence=0.95,
                    requires_clarification=False,
                    clarification_questions=[],
                    validation_duration_seconds=0.5,
                    used_fallback=False,
                )

                async def mock_validation(*args, **kwargs):
                    return mock_result

                with patch.object(validator, "_validate_with_llm", mock_validation):
                    # Patch metrics at their actual location
                    with patch(
                        "src.infrastructure.observability.metrics_agents.semantic_validation_duration_seconds"
                    ):
                        with patch(
                            "src.infrastructure.observability.metrics_agents.semantic_validation_total"
                        ) as mock_metric:
                            mock_metric.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

                            result = await validator.validate(
                                plan=mock_execution_plan,
                                user_request="Test request",
                                user_language="fr",
                            )

                            assert result.is_valid is True
                            assert result.used_fallback is False
                            assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_validation_with_clarification_required(self, mock_execution_plan):
        """Test validation that requires clarification."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                # Mock validation requiring clarification
                mock_result = SemanticValidationResult(
                    is_valid=False,
                    issues=[
                        SemanticIssue(
                            issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
                            description="User said 'pour chaque' but plan does single op",
                        )
                    ],
                    confidence=0.8,
                    requires_clarification=True,
                    clarification_questions=[
                        "Voulez-vous envoyer à UN contact ou TOUS les contacts ?"
                    ],
                    validation_duration_seconds=0.6,
                    used_fallback=False,
                )

                async def mock_validation(*args, **kwargs):
                    return mock_result

                with patch.object(validator, "_validate_with_llm", mock_validation):
                    # Patch metrics at their actual location
                    with patch(
                        "src.infrastructure.observability.metrics_agents.semantic_validation_duration_seconds"
                    ):
                        with patch(
                            "src.infrastructure.observability.metrics_agents.semantic_validation_total"
                        ) as mock_metric:
                            mock_metric.labels = MagicMock(return_value=MagicMock(inc=MagicMock()))

                            result = await validator.validate(
                                plan=mock_execution_plan,
                                user_request="Envoie un email pour chaque contact",
                                user_language="fr",
                            )

                            assert result.is_valid is False
                            assert result.requires_clarification is True
                            assert len(result.clarification_questions) == 1
                            assert len(result.issues) == 1

    def test_build_validation_prompt(self, mock_execution_plan):
        """Test prompt building for validation."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30
            mock_settings.semantic_validator_prompt_version = (
                SEMANTIC_VALIDATOR_PROMPT_VERSION_DEFAULT
            )

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                with patch(
                    "src.domains.agents.orchestration.semantic_validator.load_prompt"
                ) as mock_load:
                    mock_load.return_value = "CARDINALITY_MISMATCH MISSING_DEPENDENCY validation fr"
                    validator = PlanSemanticValidator()

                    messages = validator._build_validation_prompt(
                        plan=mock_execution_plan,
                        user_request="Envoie un email à tous mes contacts",
                        user_language="fr",
                    )

                    assert len(messages) == 2  # System + Human
                    # Check system message contains issue types
                    system_content = messages[0].content
                    assert "CARDINALITY_MISMATCH" in system_content
                    assert "MISSING_DEPENDENCY" in system_content
                    assert "fr" in system_content  # Language

                    # Check human message contains request and plan
                    human_content = messages[1].content
                    assert "Envoie un email" in human_content
                    assert "3" in human_content  # 3 steps
                    assert "search_contacts_tool" in human_content

    def test_create_valid_result_helper(self):
        """Test _create_valid_result helper method."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                # Normal valid result
                result = validator._create_valid_result(
                    reason="Test reason",
                    duration=0.5,
                    used_fallback=False,
                )

                assert result.is_valid is True
                assert result.confidence == 1.0
                assert result.used_fallback is False

                # Fallback valid result
                fallback_result = validator._create_valid_result(
                    reason="Timeout fallback",
                    duration=1.0,
                    used_fallback=True,
                )

                assert fallback_result.is_valid is True
                assert fallback_result.confidence == 0.5  # Reduced for fallback
                assert fallback_result.used_fallback is True


# ============================================================================
# Integration Tests
# ============================================================================


class TestSemanticValidatorIntegration:
    """Integration tests for semantic validator flow."""

    @pytest.mark.asyncio
    async def test_empty_plan(self):
        """Test validation of empty plan."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                empty_plan = MagicMock()
                empty_plan.plan_id = "empty-plan"
                empty_plan.steps = []

                result = await validator.validate(
                    plan=empty_plan,
                    user_request="Some request",
                    user_language="en",
                )

                # Empty plan (0 steps) should short-circuit as valid
                assert result.is_valid is True
                assert result.used_fallback is False

    @pytest.mark.asyncio
    async def test_validator_initialization_with_custom_llm(self):
        """Test validator initialization with custom LLM."""
        mock_llm = MagicMock()

        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 2.0
            mock_settings.semantic_validator_llm_provider = "anthropic"

            validator = PlanSemanticValidator(
                llm=mock_llm,
                provider="custom_provider",
                timeout_seconds=3.0,
            )

            assert validator._llm is mock_llm
            assert validator._provider == "custom_provider"
            assert validator._timeout_seconds == 3.0


# ============================================================================
# _format_plan_for_validation Tests (Issue #60 Fix)
# ============================================================================


class TestFormatPlanForValidation:
    """
    Test suite for _format_plan_for_validation().

    Issue #60 Fix: This method creates a detailed plan representation
    for the LLM to enable cardinality mismatch detection.
    """

    @pytest.fixture
    def mock_step(self):
        """Create a mock step for testing."""
        from enum import Enum

        class MockStepType(str, Enum):
            TOOL_CALL = "tool_call"

        step = MagicMock()
        step.step_id = "step_1"
        step.step_type = MockStepType.TOOL_CALL
        step.agent_name = "gmail_agent"
        step.tool_name = "gmail_send_email"
        step.description = "Envoyer un email"
        step.parameters = {"max_results": 20, "query": "contacts"}
        step.depends_on = []
        step.approvals_required = False
        step.condition = None
        step.on_success = None
        step.on_fail = None
        return step

    def test_format_includes_numeric_parameters(self, mock_step):
        """Test that numeric parameters are clearly marked for cardinality detection."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                plan = MagicMock()
                plan.steps = [mock_step]

                result = validator._format_plan_for_validation(plan)

                # Numeric values should be clearly marked
                assert "max_results: 20" in result
                assert "(number)" in result
                assert "query:" in result

    def test_format_includes_list_parameters_with_count(self, mock_step):
        """Test that list parameters show count for cardinality validation."""
        mock_step.parameters = {"recipients": ["a@test.com", "b@test.com"], "max_results": 5}

        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                plan = MagicMock()
                plan.steps = [mock_step]

                result = validator._format_plan_for_validation(plan)

                # Lists should show count
                assert "recipients:" in result
                assert "count=2" in result or "list" in result

    def test_format_includes_step_references(self, mock_step):
        """Test that step references are marked for dependency validation."""
        mock_step.parameters = {"contact_id": "$steps[0].result.id", "email": "test@test.com"}

        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                plan = MagicMock()
                plan.steps = [mock_step]

                result = validator._format_plan_for_validation(plan)

                # References should be marked
                assert "$steps[0].result.id" in result
                assert "(reference)" in result

    def test_format_includes_dependencies(self, mock_step):
        """Test that step dependencies are included for ghost dependency detection."""
        mock_step.depends_on = ["step_0"]

        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                plan = MagicMock()
                plan.steps = [mock_step]

                result = validator._format_plan_for_validation(plan)

                # Dependencies should be visible
                assert "Depends on" in result
                assert "step_0" in result

    def test_format_includes_hitl_requirements(self, mock_step):
        """Test that HITL requirements are shown."""
        mock_step.approvals_required = True

        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                plan = MagicMock()
                plan.steps = [mock_step]

                result = validator._format_plan_for_validation(plan)

                # HITL requirement should be visible
                assert "Requires Approval" in result
                assert "HITL" in result

    def test_format_includes_step_id_and_index(self, mock_step):
        """Test that step ID and index are included for issue reporting."""
        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                plan = MagicMock()
                plan.steps = [mock_step]

                result = validator._format_plan_for_validation(plan)

                # Step ID and index should be visible
                assert "Step 0" in result
                assert "step_1" in result

    def test_issue60_scenario_cardinality_visibility(self):
        """
        Test Issue #60 scenario: max_results=20 vs user request "2 per contact".

        The format must make the numeric value clearly visible so the LLM
        can detect the cardinality mismatch.
        """
        from enum import Enum

        class MockStepType(str, Enum):
            TOOL_CALL = "tool_call"

        step = MagicMock()
        step.step_id = "gmail_emails_step"
        step.step_type = MockStepType.TOOL_CALL
        step.agent_name = "gmail_agent"
        step.tool_name = "gmail_list_emails"
        step.description = "Récupérer les emails"
        step.parameters = {"max_results": 20}  # Issue #60: User said "2 per contact"
        step.depends_on = []
        step.approvals_required = False
        step.condition = None
        step.on_success = None
        step.on_fail = None

        with patch("src.domains.agents.orchestration.semantic_validator.settings") as mock_settings:
            mock_settings.semantic_validation_enabled = True
            mock_settings.semantic_validation_timeout_seconds = 5.0
            mock_settings.semantic_validator_llm_provider = "openai"
            mock_settings.insufficient_content_min_chars_threshold = 30

            with patch("src.domains.agents.orchestration.semantic_validator.get_llm"):
                validator = PlanSemanticValidator()

                plan = MagicMock()
                plan.steps = [step]

                result = validator._format_plan_for_validation(plan)

                # The key assertion: max_results=20 must be clearly visible
                # so the LLM can compare against user's "2 per contact"
                assert "max_results: 20" in result
                assert "(number)" in result
                # Tool name also visible for context
                assert "gmail_list_emails" in result


# ============================================================================
# validate_for_each_patterns Tests
# ============================================================================


class TestValidateForEachPatterns:
    """Test suite for validate_for_each_patterns function."""

    def test_for_each_missing_item_ref_detected(self):
        """Test that FOR_EACH_MISSING_ITEM_REF is detected when params use hardcoded index."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.orchestration.semantic_validator import (
            validate_for_each_patterns,
        )

        # Create a plan with for_each but using $steps.step_1.events[0] instead of $item
        plan = ExecutionPlan(
            user_id="test_user",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="calendar_agent",
                    tool_name="get_events_tool",
                    parameters={"max_results": 3},
                ),
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    agent_name="reminder_agent",
                    tool_name="create_reminder_tool",
                    parameters={
                        # BUG: Using hardcoded [0] instead of $item
                        "content": "$steps.step_1.events[0].summary",
                        "trigger_datetime": "$steps.step_1.events[0].start.dateTime",
                    },
                    depends_on=["step_1"],
                    for_each="$steps.step_1.events",
                ),
            ],
        )

        is_valid, feedback, issue_type = validate_for_each_patterns(plan)

        assert is_valid is False
        assert issue_type == SemanticIssueType.FOR_EACH_MISSING_ITEM_REF
        assert "FOR_EACH_MISSING_ITEM_REF" in feedback
        assert "$item" in feedback
        assert "CORRECT" in feedback

    def test_for_each_valid_with_item_ref(self):
        """Test that valid for_each with $item references passes validation."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.orchestration.semantic_validator import (
            validate_for_each_patterns,
        )

        # Create a plan with for_each using correct $item syntax
        plan = ExecutionPlan(
            user_id="test_user",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="calendar_agent",
                    tool_name="get_events_tool",
                    parameters={"max_results": 3},
                ),
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    agent_name="reminder_agent",
                    tool_name="create_reminder_tool",
                    parameters={
                        # CORRECT: Using $item
                        "content": "$item.summary",
                        "trigger_datetime": "$item.start.dateTime",
                    },
                    depends_on=["step_1"],
                    for_each="$steps.step_1.events",
                ),
            ],
        )

        is_valid, feedback, issue_type = validate_for_each_patterns(plan)

        assert is_valid is True
        assert feedback is None
        assert issue_type is None

    def test_for_each_mixed_refs_allowed(self):
        """Test that mixing $item with other refs is allowed if $item is present."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.orchestration.semantic_validator import (
            validate_for_each_patterns,
        )

        # Create a plan with for_each using $item AND $steps refs (for other purposes)
        plan = ExecutionPlan(
            user_id="test_user",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="calendar_agent",
                    tool_name="get_events_tool",
                    parameters={"max_results": 3},
                ),
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    agent_name="reminder_agent",
                    tool_name="create_reminder_tool",
                    parameters={
                        # CORRECT: Using $item for iteration + $steps for other data
                        "content": "$item.summary",
                        "trigger_datetime": "$item.start.dateTime",
                        # This is allowed - referencing another step's data (not the iteration source)
                        "extra_info": "$steps.step_0.some_value",
                    },
                    depends_on=["step_1"],
                    for_each="$steps.step_1.events",
                ),
            ],
        )

        is_valid, feedback, issue_type = validate_for_each_patterns(plan)

        assert is_valid is True
        assert feedback is None
        assert issue_type is None

    def test_for_each_index_placeholder_detected(self):
        """Test that FOR_EACH_MISSING_ITEM_REF is detected when params use [INDEX] placeholder."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticIssueType,
            validate_for_each_patterns,
        )

        # Create a plan with for_each where LLM used [INDEX] instead of $item
        plan = ExecutionPlan(
            user_id="test_user",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="calendar_agent",
                    tool_name="get_events_tool",
                    parameters={"max_results": 3},
                ),
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    agent_name="reminder_agent",
                    tool_name="create_reminder_tool",
                    parameters={
                        # WRONG: LLM used [INDEX] as a literal placeholder
                        "content": "$steps.step_1.events[INDEX].summary",
                        "trigger_datetime": "$steps.step_1.events[INDEX].start.dateTime",
                    },
                    depends_on=["step_1"],
                    for_each="$steps.step_1.events",
                ),
            ],
        )

        is_valid, feedback, issue_type = validate_for_each_patterns(plan)

        assert is_valid is False
        assert issue_type == SemanticIssueType.FOR_EACH_MISSING_ITEM_REF
        assert "FOR_EACH_MISSING_ITEM_REF" in feedback
        assert "$item" in feedback
        assert "RESERVED KEYWORD" in feedback

    def test_for_each_i_placeholder_detected(self):
        """Test that FOR_EACH_MISSING_ITEM_REF is detected when params use [i] placeholder."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticIssueType,
            validate_for_each_patterns,
        )

        # Create a plan with for_each where LLM used [i] instead of $item
        plan = ExecutionPlan(
            user_id="test_user",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="contacts_agent",
                    tool_name="get_contacts_tool",
                    parameters={"query": "family"},
                ),
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    agent_name="email_agent",
                    tool_name="send_email_tool",
                    parameters={
                        # WRONG: LLM used [i] as a loop variable placeholder
                        "to": "$steps.step_1.contacts[i].email",
                        "subject": "Hello",
                    },
                    depends_on=["step_1"],
                    for_each="$steps.step_1.contacts",
                ),
            ],
        )

        is_valid, feedback, issue_type = validate_for_each_patterns(plan)

        assert is_valid is False
        assert issue_type == SemanticIssueType.FOR_EACH_MISSING_ITEM_REF
        assert "$item" in feedback

    def test_for_each_wildcard_placeholder_detected(self):
        """Test that FOR_EACH_MISSING_ITEM_REF is detected when params use [*] wildcard."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.orchestration.semantic_validator import (
            SemanticIssueType,
            validate_for_each_patterns,
        )

        # Create a plan with for_each where LLM used [*] wildcard instead of $item
        plan = ExecutionPlan(
            user_id="test_user",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="calendar_agent",
                    tool_name="get_events_tool",
                    parameters={"max_results": 3},
                ),
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    agent_name="reminder_agent",
                    tool_name="create_reminder_tool",
                    parameters={
                        # WRONG: LLM used [*] wildcard thinking it expands to all items
                        "content": "$steps.step_1.events[*].summary",
                        "trigger_datetime": "$steps.step_1.events[*].start.dateTime",
                    },
                    depends_on=["step_1"],
                    for_each="$steps.step_1.events",
                ),
            ],
        )

        is_valid, feedback, issue_type = validate_for_each_patterns(plan)

        assert is_valid is False
        assert issue_type == SemanticIssueType.FOR_EACH_MISSING_ITEM_REF
        assert "$item" in feedback
        assert "RESERVED KEYWORD" in feedback


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
