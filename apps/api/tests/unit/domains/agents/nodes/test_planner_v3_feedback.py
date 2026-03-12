"""
Unit tests for planner_v3 semantic validation feedback integration.

Tests the feedback loop where semantic validator issues are passed back
to the planner during auto-replan cycles.
"""

from src.domains.agents.nodes.planner_node_v3 import _format_validation_feedback
from src.domains.agents.orchestration.semantic_validator import (
    SemanticIssue,
    SemanticIssueType,
    SemanticValidationResult,
)


class TestFormatValidationFeedback:
    """Tests for _format_validation_feedback helper."""

    def test_empty_validation_returns_empty_string(self):
        """No validation result returns empty feedback."""
        assert _format_validation_feedback(None) == ""

    def test_no_issues_returns_empty_string(self):
        """Validation with no issues returns empty feedback."""
        validation = SemanticValidationResult(
            is_valid=True,
            issues=[],
            confidence=1.0,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.1,
        )
        assert _format_validation_feedback(validation) == ""

    def test_single_issue_formatted_correctly(self):
        """Single issue is formatted with type and description."""
        issue = SemanticIssue(
            issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
            description="Plan processes only one contact instead of all",
            step_index=0,
            severity="high",
            suggested_fix="Use batch parameter or iterate over all contacts",
        )
        validation = SemanticValidationResult(
            is_valid=False,
            issues=[issue],
            confidence=0.3,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.5,
        )

        feedback = _format_validation_feedback(validation)

        assert "PREVIOUS PLAN VALIDATION FAILED" in feedback
        assert "cardinality_mismatch" in feedback
        assert "(step 0)" in feedback
        assert "Plan processes only one contact" in feedback
        assert "FIX:" in feedback
        assert "batch parameter" in feedback
        assert "CRITICAL: You MUST address ALL issues" in feedback

    def test_multiple_issues_all_included(self):
        """Multiple issues are all formatted in feedback."""
        issues = [
            SemanticIssue(
                issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
                description="Wrong count",
                step_index=0,
                severity="high",
            ),
            SemanticIssue(
                issue_type=SemanticIssueType.SCOPE_OVERFLOW,
                description="Too many actions",
                step_index=1,
                severity="medium",
                suggested_fix="Reduce scope",
            ),
        ]
        validation = SemanticValidationResult(
            is_valid=False,
            issues=issues,
            confidence=0.4,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.3,
        )

        feedback = _format_validation_feedback(validation)

        assert "1. [cardinality_mismatch]" in feedback
        assert "2. [scope_overflow]" in feedback
        assert "Wrong count" in feedback
        assert "Too many actions" in feedback
        assert "FIX: Reduce scope" in feedback

    def test_handles_dict_format(self):
        """Also handles dict-based validation (for flexibility)."""
        validation = {
            "is_valid": False,
            "issues": [
                {
                    "issue_type": "ghost_dependency",
                    "description": "Step 2 references non-existent step",
                    "step_index": 2,
                    "severity": "high",
                }
            ],
        }

        feedback = _format_validation_feedback(validation)

        assert "ghost_dependency" in feedback
        assert "(step 2)" in feedback
        assert "Step 2 references non-existent step" in feedback

    def test_issue_without_step_index(self):
        """Issue without step_index (plan-level issue) is formatted correctly."""
        issue = SemanticIssue(
            issue_type=SemanticIssueType.MISSING_STEP,
            description="Plan is missing verification step",
            step_index=None,
            severity="medium",
            suggested_fix="Add verification step before mutation",
        )
        validation = SemanticValidationResult(
            is_valid=False,
            issues=[issue],
            confidence=0.5,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.2,
        )

        feedback = _format_validation_feedback(validation)

        assert "1. [missing_step]" in feedback
        assert "(step" not in feedback  # No step info since step_index is None
        assert "Plan is missing verification step" in feedback

    def test_issue_without_suggested_fix(self):
        """Issue without suggested_fix is formatted without FIX line."""
        issue = SemanticIssue(
            issue_type=SemanticIssueType.WRONG_PARAMETERS,
            description="Parameter value does not match user intent",
            step_index=1,
            severity="medium",
        )
        validation = SemanticValidationResult(
            is_valid=False,
            issues=[issue],
            confidence=0.6,
            requires_clarification=False,
            clarification_questions=[],
            validation_duration_seconds=0.3,
        )

        feedback = _format_validation_feedback(validation)

        assert "wrong_parameters" in feedback
        assert "Parameter value does not match" in feedback
        assert "FIX:" not in feedback  # No FIX line since suggested_fix is None

    def test_non_validation_object_returns_empty(self):
        """Non-validation object returns empty string."""
        assert _format_validation_feedback("invalid") == ""
        assert _format_validation_feedback(123) == ""
        assert _format_validation_feedback([]) == ""
