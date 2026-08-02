"""
Unit tests for planner_v3 semantic validation feedback integration.

Tests the feedback loop where semantic validator issues are passed back
to the planner during auto-replan cycles.
"""

from dataclasses import asdict

from src.domains.agents.nodes.planner_node_v3 import (
    _format_validation_feedback,
    _has_cardinality_mismatch,
    _issue_type_value,
    _semantic_issues,
)
from src.domains.agents.orchestration.semantic_validator import (
    SemanticIssue,
    SemanticIssueType,
    SemanticValidationResult,
)
from src.domains.agents.utils.shape_agnostic import read_field


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


def _verdict(*issues: SemanticIssue) -> SemanticValidationResult:
    """A verdict in the shape the semantic validator node writes it."""
    return SemanticValidationResult(
        is_valid=not issues,
        issues=list(issues),
        confidence=0.3,
        requires_clarification=False,
        clarification_questions=[],
        validation_duration_seconds=0.1,
    )


def _cardinality_issue() -> SemanticIssue:
    return SemanticIssue(
        issue_type=SemanticIssueType.CARDINALITY_MISMATCH,
        description="Plan processes only one contact instead of all",
        step_index=0,
        severity="high",
    )


class TestSemanticIssuesAccessor:
    """``STATE_KEY_SEMANTIC_VALIDATION`` legitimately holds TWO shapes.

    The validator node writes the ``SemanticValidationResult`` dataclass, but
    ``clarification_node`` rebuilds the verdict through ``dataclasses.asdict``
    and writes back a plain mapping. Reading ``.issues`` directly is therefore
    correct only half the time, and wrong silently: ``hasattr(mapping,
    "issues")`` is False, so the branch is skipped rather than raising.
    """

    def test_reads_issues_from_the_dataclass(self):
        assert _semantic_issues(_verdict(_cardinality_issue())) != []

    def test_reads_issues_from_the_mapping_clarification_writes_back(self):
        """The shape produced by ``asdict`` must yield the same issues."""
        mapping = asdict(_verdict(_cardinality_issue()))

        assert not hasattr(mapping, "issues"), "precondition: attribute access fails here"
        assert len(_semantic_issues(mapping)) == 1

    def test_absent_verdict_yields_no_issues(self):
        assert _semantic_issues(None) == []
        assert _semantic_issues({}) == []

    def test_explicit_null_issues_yields_no_issues(self):
        """`issues: None` is a real shape — a verdict serialised before any run.

        Pinned because the mapping branch reads through ``.get()``, which
        returns None rather than raising: without this, a future rewrite could
        hand `None` straight to the caller's `for` loop.
        """
        assert _semantic_issues({"issues": None}) == []
        assert _semantic_issues(_verdict()) == []

    def test_unknown_shape_yields_no_issues(self):
        """Never raise on an unexpected shape: a planner turn must not die here."""
        assert _semantic_issues("invalid") == []
        assert _semantic_issues(123) == []


class TestIssueTypeValue:
    """Issues themselves arrive as models OR as plain mappings."""

    def test_enum_member_is_reduced_to_its_value(self):
        assert _issue_type_value(_cardinality_issue()) == "cardinality_mismatch"

    def test_plain_mapping_issue(self):
        assert _issue_type_value({"issue_type": "ghost_dependency"}) == "ghost_dependency"

    def test_mapping_without_type_is_unknown(self):
        assert _issue_type_value({}) == "unknown"


class TestIssueField:
    """Issue fields cross the same model/mapping boundary as the type does.

    Reads now go through the shared ``read_field``; these cases stay because
    they pin what THIS module needs from it.
    """

    def test_reads_from_a_model(self):
        issue = _cardinality_issue()
        assert read_field(issue, "description") == issue.description
        assert read_field(issue, "step_index") == 0

    def test_reads_from_a_mapping(self):
        issue = {"description": "boom", "step_index": 3}
        assert read_field(issue, "description") == "boom"
        assert read_field(issue, "step_index") == 3

    def test_missing_field_yields_none(self):
        assert read_field(_cardinality_issue(), "suggested_fix") is None
        assert read_field({}, "description") is None
        assert read_field("not an issue", "description") is None


class TestHasCardinalityMismatch:
    """Regression guard: the FOR_EACH directive must be injected in BOTH shapes.

    The planner injects the FOR_EACH directive when the semantic validator
    reports a ``cardinality_mismatch``. Read through attribute access only, the
    detection returned False on every turn that had passed through a
    clarification — the user answered a question and silently lost the
    directive that the answer was supposed to trigger.
    """

    def test_detected_on_the_dataclass(self):
        assert _has_cardinality_mismatch(_verdict(_cardinality_issue())) is True

    def test_detected_on_the_mapping_clarification_writes_back(self):
        assert _has_cardinality_mismatch(asdict(_verdict(_cardinality_issue()))) is True

    def test_not_detected_when_another_issue_type(self):
        other = SemanticIssue(
            issue_type=SemanticIssueType.GHOST_DEPENDENCY,
            description="Step 2 references a step that produces nothing",
            severity="high",
        )
        assert _has_cardinality_mismatch(_verdict(other)) is False

    def test_not_detected_without_issues(self):
        assert _has_cardinality_mismatch(_verdict()) is False
        assert _has_cardinality_mismatch(None) is False
