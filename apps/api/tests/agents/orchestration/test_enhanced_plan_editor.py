"""
Unit tests for EnhancedPlanEditor and SecurePlanEditor (Phase 3 OPTIMPLAN).

Tests cover:
- EnhancedPlanEditor schema validation
- EnhancedPlanEditor undo functionality
- EnhancedPlanEditor audit logging
- SecurePlanEditor injection detection
- Broken reference detection
- Metrics instrumentation

Created: 2025-11-26
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.orchestration.approval_schemas import PlanModification
from src.domains.agents.orchestration.plan_editor import (
    EditAuditEntry,
    EnhancedEditResult,
    EnhancedPlanEditor,
    InjectionDetectedError,
    PlanModificationError,
    SchemaValidationError,
    SecurePlanEditor,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_plan() -> ExecutionPlan:
    """Create a sample execution plan for testing."""
    return ExecutionPlan(
        plan_id="test_plan_001",
        user_id="test_user_123",  # Required field
        session_id="test_session_456",  # Required field
        user_request="Search for contacts named John",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type="TOOL",  # Required field
                tool_name="search_contacts_tool",
                agent_name="contacts_agent",
                parameters={"query": "John", "max_results": 10},
                depends_on=[],
                estimated_cost_usd=0.01,
                description="Search for contacts",
            ),
            ExecutionStep(
                step_id="step_2",
                step_type="TOOL",  # Required field
                tool_name="get_contact_details_tool",
                agent_name="contacts_agent",
                parameters={"resource_name": "$steps.step_1.results[0].resource_name"},
                depends_on=["step_1"],
                estimated_cost_usd=0.005,
                description="Get contact details",
            ),
        ],
        execution_mode="sequential",
    )


@pytest.fixture
def mock_schema_validator():
    """Create a mock HitlSchemaValidator."""
    validator = MagicMock()
    # Default: validation passes
    validator.validate_tool_args.return_value = MagicMock(
        is_valid=True,
        validated_args={"query": "test"},
        errors=[],
    )
    return validator


@pytest.fixture
def mock_schema_validator_failing():
    """Create a mock HitlSchemaValidator that fails validation."""
    validator = MagicMock()
    validator.validate_tool_args.return_value = MagicMock(
        is_valid=False,
        validated_args=None,
        errors=["max_results: Invalid parameter type (expected int, got str)"],
    )
    return validator


# ============================================================================
# EnhancedPlanEditor Basic Tests
# ============================================================================


class TestEnhancedPlanEditorBasic:
    """Test basic EnhancedPlanEditor functionality."""

    def test_init_without_validator(self):
        """Test initialization without schema validator."""
        editor = EnhancedPlanEditor()
        assert editor._schema_validator is None
        assert editor.history_size == 0

    def test_init_with_validator(self, mock_schema_validator):
        """Test initialization with schema validator."""
        editor = EnhancedPlanEditor(schema_validator=mock_schema_validator)
        assert editor._schema_validator is not None

    def test_apply_edit_params_no_validator(self, sample_plan):
        """Test applying edit_params modification without validator."""
        editor = EnhancedPlanEditor()

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Jane"},
            )
        ]

        # Patch metrics at their actual location (imported inside method)
        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = editor.apply_with_validation(sample_plan, modifications)

        assert isinstance(result, EnhancedEditResult)
        assert result.schema_validated is False  # No validator
        assert len(result.audit_entries) == 1

        # Verify modification was applied
        modified_step = result.modified_plan.steps[0]
        assert modified_step.parameters["query"] == "Jane"

    def test_apply_edit_params_with_validator(self, sample_plan, mock_schema_validator):
        """Test applying edit_params modification with validator."""
        editor = EnhancedPlanEditor(schema_validator=mock_schema_validator)

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Jane"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = editor.apply_with_validation(sample_plan, modifications)

        assert result.schema_validated is True
        mock_schema_validator.validate_tool_args.assert_called_once()


# ============================================================================
# EnhancedPlanEditor Schema Validation Tests
# ============================================================================


class TestEnhancedPlanEditorSchemaValidation:
    """Test schema validation in EnhancedPlanEditor."""

    def test_schema_validation_failure(self, sample_plan, mock_schema_validator_failing):
        """Test that schema validation failure raises SchemaValidationError."""
        editor = EnhancedPlanEditor(schema_validator=mock_schema_validator_failing)

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"max_results": "invalid_string"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_ops:
            mock_ops.labels.return_value.inc = MagicMock()
            with patch(
                "src.infrastructure.observability.metrics_agents.plan_edit_schema_validation_failures_total"
            ) as mock_metric:
                mock_metric.labels.return_value.inc = MagicMock()

                with pytest.raises(SchemaValidationError) as exc_info:
                    editor.apply_with_validation(sample_plan, modifications)

                assert "search_contacts_tool" in str(exc_info.value)
                assert "max_results" in str(exc_info.value)

    def test_schema_validation_merges_params(self, sample_plan, mock_schema_validator):
        """Test that validation merges original + new params."""
        editor = EnhancedPlanEditor(schema_validator=mock_schema_validator)

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Jane"},  # Only modify query
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            editor.apply_with_validation(sample_plan, modifications)

        # Verify validator was called with merged params
        call_args = mock_schema_validator.validate_tool_args.call_args
        merged_args = call_args.kwargs["merged_args"]
        assert merged_args["query"] == "Jane"
        assert merged_args["max_results"] == 10  # Original value preserved


# ============================================================================
# EnhancedPlanEditor History/Undo Tests
# ============================================================================


class TestEnhancedPlanEditorUndo:
    """Test undo functionality in EnhancedPlanEditor."""

    def test_undo_restores_previous_plan(self, sample_plan):
        """Test that undo restores the previous plan state."""
        editor = EnhancedPlanEditor()

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Jane"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = editor.apply_with_validation(sample_plan, modifications)

        # Verify modification was applied
        assert result.modified_plan.steps[0].parameters["query"] == "Jane"
        assert editor.history_size == 1

        # Undo
        previous = editor.undo()
        assert previous is not None
        assert previous.steps[0].parameters["query"] == "John"
        assert editor.history_size == 0

    def test_undo_empty_history_returns_none(self):
        """Test that undo on empty history returns None."""
        editor = EnhancedPlanEditor()
        assert editor.undo() is None

    def test_history_limit(self):
        """Test that history respects max size limit."""
        editor = EnhancedPlanEditor()
        editor._max_history_size = 3

        # Apply multiple modifications (push directly to history)
        for i in range(5):
            # Create new plan for each iteration
            modified = ExecutionPlan(
                plan_id=f"test_plan_{i}",
                user_id="test_user_123",
                session_id="test_session_456",
                user_request="Test request",
                steps=[
                    ExecutionStep(
                        step_id="step_1",
                        step_type="TOOL",
                        tool_name="test_tool",
                        agent_name="test_agent",
                        parameters={"query": f"Query{i}"},
                        depends_on=[],
                        estimated_cost_usd=0.01,
                        description="Test step",
                    ),
                ],
                execution_mode="sequential",
            )
            editor._push_history(modified)

        # History should be limited to 3
        assert editor.history_size == 3


# ============================================================================
# EnhancedPlanEditor Audit Tests
# ============================================================================


class TestEnhancedPlanEditorAudit:
    """Test audit logging in EnhancedPlanEditor."""

    def test_audit_entry_created(self, sample_plan):
        """Test that audit entries are created for modifications."""
        editor = EnhancedPlanEditor()

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Jane"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = editor.apply_with_validation(sample_plan, modifications)

        assert len(result.audit_entries) == 1
        entry = result.audit_entries[0]
        assert isinstance(entry, EditAuditEntry)
        assert entry.original_params == {"query": "John", "max_results": 10}
        assert entry.new_params["query"] == "Jane"
        assert entry.timestamp is not None

    def test_audit_multiple_modifications(self, sample_plan):
        """Test audit entries for multiple modifications."""
        editor = EnhancedPlanEditor()

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Jane"},
            ),
            PlanModification(
                modification_type="edit_params",
                step_id="step_2",
                new_parameters={"resource_name": "people/c123"},
            ),
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = editor.apply_with_validation(sample_plan, modifications)

        assert len(result.audit_entries) == 2


# ============================================================================
# EnhancedPlanEditor Broken Reference Detection
# ============================================================================


class TestEnhancedPlanEditorReferences:
    """Test broken reference detection in EnhancedPlanEditor."""

    def test_detect_broken_reference_after_removal(self, sample_plan):
        """Test that removing a step with dependents raises error."""
        editor = EnhancedPlanEditor()

        # Remove step_1 which step_2 depends on
        modifications = [
            PlanModification(
                modification_type="remove_step",
                step_id="step_1",
            )
        ]

        # This should raise an error because step_2 depends on step_1
        # The error is raised by base PlanEditor.apply_modifications() before
        # EnhancedPlanEditor gets to check broken references
        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            with pytest.raises(PlanModificationError) as exc_info:
                editor.apply_with_validation(sample_plan, modifications)

            # Error message should contain dependency information
            error_msg = str(exc_info.value).lower()
            assert "step_1" in error_msg or "depend" in error_msg


# ============================================================================
# SecurePlanEditor Injection Detection Tests
# ============================================================================


class TestSecurePlanEditorInjection:
    """Test injection detection in SecurePlanEditor."""

    @pytest.fixture
    def secure_editor(self):
        """Create SecurePlanEditor with strict mode."""
        return SecurePlanEditor(strict_mode=True)

    @pytest.mark.parametrize(
        "pattern_name,malicious_value",
        [
            ("dunder_attribute", "__class__.__bases__"),
            ("eval_call", "eval(input())"),
            ("exec_call", "exec('import os')"),
            ("import_statement", "import subprocess"),
            ("template_dollar", "${cmd}"),
            ("template_jinja", "{{config.items()}}"),
            ("os_system", "os.system('ls')"),
            ("subprocess", "subprocess.call(['ls'])"),
        ],
    )
    def test_injection_pattern_detected(
        self, secure_editor, sample_plan, pattern_name, malicious_value
    ):
        """Test that various injection patterns are detected."""
        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": malicious_value},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_ops:
            mock_ops.labels.return_value.inc = MagicMock()
            with patch(
                "src.infrastructure.observability.metrics_agents.plan_edit_injection_blocked_total"
            ) as mock_metric:
                mock_metric.labels.return_value.inc = MagicMock()

                with pytest.raises(InjectionDetectedError) as exc_info:
                    secure_editor.apply_with_validation(sample_plan, modifications)

                # Verify the pattern was detected
                assert exc_info.value.pattern in [
                    "dunder_attribute",
                    "eval_call",
                    "exec_call",
                    "import_statement",
                    "template_dollar",
                    "template_jinja",
                    "os_system",
                    "subprocess",
                ]

    def test_safe_value_passes(self, secure_editor, sample_plan):
        """Test that safe values pass injection check."""
        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "John Doe from Marketing"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = secure_editor.apply_with_validation(sample_plan, modifications)

        assert result.injection_checked is True
        assert result.modified_plan.steps[0].parameters["query"] == "John Doe from Marketing"

    def test_non_strict_mode_logs_warning(self, sample_plan):
        """Test that non-strict mode logs warning but continues."""
        editor = SecurePlanEditor(strict_mode=False)

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "eval(x)"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_ops:
            mock_ops.labels.return_value.inc = MagicMock()
            with patch(
                "src.infrastructure.observability.metrics_agents.plan_edit_injection_blocked_total"
            ) as mock_metric:
                mock_metric.labels.return_value.inc = MagicMock()

                # Should NOT raise (non-strict mode)
                result = editor.apply_with_validation(sample_plan, modifications)

                # Should still mark as injection-checked
                assert result.injection_checked is True

    def test_injection_checked_flag_set(self, secure_editor, sample_plan):
        """Test that injection_checked flag is set to True."""
        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Safe query"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = secure_editor.apply_with_validation(sample_plan, modifications)

        assert result.injection_checked is True


# ============================================================================
# Integration Tests
# ============================================================================


class TestPlanEditorIntegration:
    """Integration tests combining multiple features."""

    def test_full_edit_flow_with_validation_and_security(self, sample_plan, mock_schema_validator):
        """Test complete edit flow with schema validation and security."""
        editor = SecurePlanEditor(
            schema_validator=mock_schema_validator,
            strict_mode=True,
        )

        modifications = [
            PlanModification(
                modification_type="edit_params",
                step_id="step_1",
                new_parameters={"query": "Jane Smith"},
            )
        ]

        with patch(
            "src.infrastructure.observability.metrics_agents.plan_edit_operations_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()
            result = editor.apply_with_validation(sample_plan, modifications)

        # All checks passed
        assert result.schema_validated is True
        assert result.injection_checked is True
        assert len(result.warnings) == 0
        assert len(result.audit_entries) == 1

        # Modification applied
        assert result.modified_plan.steps[0].parameters["query"] == "Jane Smith"

        # Can undo
        previous = editor.undo()
        assert previous.steps[0].parameters["query"] == "John"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
