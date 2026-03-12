"""
Tests pour ScopeDetector - Detection de scopes dangereux et for_each.

Ce module teste:
1. detect_dangerous_scope() - Detection des operations destructives bulk
2. detect_for_each_scope() - Detection des iterations for_each (plan_planner.md Section 12)
"""

from src.core.config import get_settings
from src.core.constants import (
    FOR_EACH_APPROVAL_THRESHOLD,
    FOR_EACH_WARNING_THRESHOLD,
    SCOPE_BULK_THRESHOLD,
)
from src.domains.agents.services.hitl.scope_detector import (
    ScopeRisk,
    detect_dangerous_scope,
    detect_for_each_scope,
)

# Alias for backward compatibility in tests
BULK_THRESHOLD = SCOPE_BULK_THRESHOLD
FOR_EACH_MUTATION_THRESHOLD = get_settings().for_each_mutation_threshold


# ============================================================================
# Tests detect_dangerous_scope (existing)
# ============================================================================


class TestDetectDangerousScope:
    """Tests for dangerous scope detection."""

    def test_low_risk_single_item(self):
        """Single item operations should be low risk."""
        scope = detect_dangerous_scope(
            operation_type="delete_email",
            query="delete this email",
            affected_count=1,
        )

        assert scope.risk_level == ScopeRisk.LOW
        assert scope.requires_confirmation is False

    def test_medium_risk_bulk_delete(self):
        """Bulk delete at threshold should require confirmation."""
        scope = detect_dangerous_scope(
            operation_type="delete_emails",
            query="delete these emails",
            affected_count=BULK_THRESHOLD,
        )

        assert scope.risk_level in (ScopeRisk.MEDIUM, ScopeRisk.HIGH)
        assert scope.requires_confirmation is True

    def test_high_risk_all_pattern(self):
        """'All' pattern should trigger high risk."""
        scope = detect_dangerous_scope(
            operation_type="delete_emails",
            query="delete all emails from Jean",
            affected_count=5,
        )

        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.requires_confirmation is True
        assert "broad_scope" in str(scope.indicators)

    def test_critical_risk_large_count(self):
        """Large count should trigger critical risk."""
        scope = detect_dangerous_scope(
            operation_type="delete_emails",
            query="delete these emails",
            affected_count=100,
        )

        assert scope.risk_level == ScopeRisk.CRITICAL
        assert scope.requires_confirmation is True


# ============================================================================
# Tests detect_for_each_scope (plan_planner.md Section 12)
# ============================================================================


class TestDetectForEachScope:
    """Tests for for_each scope detection."""

    def test_small_read_iteration_no_approval(self):
        """Small read-only iteration should not require approval."""
        scope = detect_for_each_scope(
            iteration_count=3,
            tool_name="get_weather_tool",
            is_mutation=False,
        )

        assert scope.requires_approval is False
        assert scope.risk_level == ScopeRisk.LOW
        assert scope.is_mutation is False

    def test_mutation_threshold_requires_approval(self):
        """Mutation at threshold should require approval."""
        scope = detect_for_each_scope(
            iteration_count=FOR_EACH_MUTATION_THRESHOLD,
            tool_name="send_email_tool",
            is_mutation=True,
        )

        assert scope.requires_approval is True
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.is_mutation is True

    def test_mutation_auto_detected(self):
        """Mutation should be auto-detected from tool name."""
        scope = detect_for_each_scope(
            iteration_count=5,
            tool_name="delete_contact_tool",
            is_mutation=False,  # Not explicitly set, should be detected
        )

        # 'delete' in tool name should trigger mutation detection
        assert scope.is_mutation is True
        assert scope.requires_approval is True

    def test_large_read_iteration_warning(self):
        """Large read iteration should trigger warning."""
        scope = detect_for_each_scope(
            iteration_count=FOR_EACH_WARNING_THRESHOLD,
            tool_name="get_weather_tool",
            is_mutation=False,
        )

        assert scope.requires_approval is True
        assert scope.risk_level == ScopeRisk.MEDIUM

    def test_exceeds_for_each_max(self):
        """Iteration exceeding for_each_max should require approval."""
        scope = detect_for_each_scope(
            iteration_count=15,
            tool_name="get_weather_tool",
            is_mutation=False,
            for_each_max=10,
        )

        assert scope.requires_approval is True
        assert "exceeds limit" in scope.reason

    def test_send_email_mutation_detection(self):
        """send_email should be detected as mutation."""
        scope = detect_for_each_scope(
            iteration_count=5,
            tool_name="send_email_tool",
            is_mutation=False,  # Not set explicitly
        )

        assert scope.is_mutation is True  # 'send' pattern detected

    def test_create_event_mutation_detection(self):
        """create_event should be detected as mutation."""
        scope = detect_for_each_scope(
            iteration_count=4,
            tool_name="create_event_tool",
            is_mutation=False,
        )

        assert scope.is_mutation is True  # 'create' pattern detected
        assert scope.requires_approval is True

    def test_two_mutations_requires_approval(self):
        """Two mutations should require approval (default threshold=1)."""
        scope = detect_for_each_scope(
            iteration_count=2,
            tool_name="send_email_tool",
            is_mutation=True,
        )

        # With default threshold=1, 2 mutations → HIGH risk, requires approval
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.requires_approval is True

    def test_one_mutation_requires_approval(self):
        """Single mutation should require approval (default threshold=1)."""
        scope = detect_for_each_scope(
            iteration_count=1,
            tool_name="send_email_tool",
            is_mutation=True,
        )

        # With default threshold=1, 1 mutation → HIGH risk, requires approval
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.requires_approval is True


class TestForEachScopeThresholds:
    """Tests for for_each threshold values."""

    def test_thresholds_are_reasonable(self):
        """Verify threshold values are sensible."""
        assert FOR_EACH_APPROVAL_THRESHOLD == 5
        assert FOR_EACH_WARNING_THRESHOLD == 10
        # Default mutation threshold is 1 (strictest - any mutation requires approval)
        # Configurable via FOR_EACH_MUTATION_THRESHOLD env var
        assert FOR_EACH_MUTATION_THRESHOLD == 1

    def test_mutation_threshold_lower_than_read(self):
        """Mutation threshold should be lower than read threshold."""
        assert FOR_EACH_MUTATION_THRESHOLD < FOR_EACH_APPROVAL_THRESHOLD

    def test_approval_threshold_lower_than_warning(self):
        """Approval threshold should be lower than warning."""
        assert FOR_EACH_APPROVAL_THRESHOLD < FOR_EACH_WARNING_THRESHOLD
