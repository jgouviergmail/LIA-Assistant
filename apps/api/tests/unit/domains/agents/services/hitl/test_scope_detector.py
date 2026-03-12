"""
Unit tests for HITL Scope Detector.

Tests dangerous scope detection for operations requiring enhanced HITL confirmation.
Covers: detect_dangerous_scope, should_escalate_to_destructive_confirm, detect_for_each_scope

@created: 2026-02-02
@coverage: scope_detector.py
"""

from unittest.mock import patch

from src.domains.agents.services.hitl.scope_detector import (
    DangerousScope,
    ForEachScope,
    ScopeRisk,
    _build_reason,
    _extract_operation_type,
    detect_dangerous_scope,
    detect_for_each_scope,
    should_escalate_to_destructive_confirm,
)

# ============================================================================
# ScopeRisk Enum Tests
# ============================================================================


class TestScopeRiskEnum:
    """Tests for ScopeRisk enumeration."""

    def test_scope_risk_values(self):
        """Test all ScopeRisk enum values exist."""
        assert ScopeRisk.LOW == "low"
        assert ScopeRisk.MEDIUM == "medium"
        assert ScopeRisk.HIGH == "high"
        assert ScopeRisk.CRITICAL == "critical"

    def test_scope_risk_is_str_enum(self):
        """Test ScopeRisk inherits from str."""
        assert isinstance(ScopeRisk.LOW, str)
        assert ScopeRisk.LOW == "low"


# ============================================================================
# DangerousScope Dataclass Tests
# ============================================================================


class TestDangerousScopeDataclass:
    """Tests for DangerousScope dataclass."""

    def test_dangerous_scope_required_fields(self):
        """Test DangerousScope can be created with required fields only."""
        scope = DangerousScope(
            requires_confirmation=True,
            risk_level=ScopeRisk.HIGH,
            operation_type="delete_emails",
        )
        assert scope.requires_confirmation is True
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.operation_type == "delete_emails"

    def test_dangerous_scope_defaults(self):
        """Test DangerousScope default values."""
        scope = DangerousScope(
            requires_confirmation=False,
            risk_level=ScopeRisk.LOW,
            operation_type="read_emails",
        )
        assert scope.affected_count == 1
        assert scope.reason == ""
        assert scope.indicators == []

    def test_dangerous_scope_all_fields(self):
        """Test DangerousScope with all fields populated."""
        scope = DangerousScope(
            requires_confirmation=True,
            risk_level=ScopeRisk.CRITICAL,
            operation_type="delete_emails",
            affected_count=100,
            reason="Critical operation",
            indicators=["broad_scope:all", "count:100>=critical"],
        )
        assert scope.affected_count == 100
        assert scope.reason == "Critical operation"
        assert len(scope.indicators) == 2


# ============================================================================
# ForEachScope Dataclass Tests
# ============================================================================


class TestForEachScopeDataclass:
    """Tests for ForEachScope dataclass."""

    def test_for_each_scope_required_fields(self):
        """Test ForEachScope creation with required fields."""
        scope = ForEachScope(
            requires_approval=True,
            risk_level=ScopeRisk.HIGH,
            iteration_count=15,
            is_mutation=True,
            tool_name="send_email_tool",
        )
        assert scope.requires_approval is True
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.iteration_count == 15
        assert scope.is_mutation is True
        assert scope.tool_name == "send_email_tool"
        assert scope.reason == ""  # default

    def test_for_each_scope_with_reason(self):
        """Test ForEachScope with reason field."""
        scope = ForEachScope(
            requires_approval=True,
            risk_level=ScopeRisk.MEDIUM,
            iteration_count=5,
            is_mutation=False,
            tool_name="get_weather_tool",
            reason="Moderate iteration count",
        )
        assert scope.reason == "Moderate iteration count"


# ============================================================================
# detect_dangerous_scope Function Tests
# ============================================================================


class TestDetectDangerousScope:
    """Tests for detect_dangerous_scope function."""

    # --- Basic behavior tests ---

    def test_no_parameters_returns_safe_scope(self):
        """Test with no parameters returns safe (LOW risk)."""
        scope = detect_dangerous_scope()
        assert scope.requires_confirmation is False
        assert scope.risk_level == ScopeRisk.LOW
        assert scope.operation_type == "unknown"

    def test_single_item_no_query_is_safe(self):
        """Test single item operation is safe."""
        scope = detect_dangerous_scope(operation_type="delete_emails", affected_count=1)
        assert scope.requires_confirmation is False
        assert scope.risk_level == ScopeRisk.LOW

    # --- Affected count threshold tests ---

    def test_bulk_threshold_medium_risk(self):
        """Test 3+ items triggers MEDIUM risk (SCOPE_BULK_THRESHOLD=3)."""
        scope = detect_dangerous_scope(operation_type="list_emails", affected_count=3)
        assert scope.risk_level == ScopeRisk.MEDIUM
        assert "count:3>=bulk" in scope.indicators

    def test_high_risk_threshold(self):
        """Test 10+ items triggers HIGH risk (SCOPE_HIGH_RISK_THRESHOLD=10)."""
        scope = detect_dangerous_scope(operation_type="list_emails", affected_count=10)
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.requires_confirmation is True
        assert "count:10>=high" in scope.indicators

    def test_critical_threshold(self):
        """Test 50+ items triggers CRITICAL risk (SCOPE_CRITICAL_THRESHOLD=50)."""
        scope = detect_dangerous_scope(operation_type="delete_emails", affected_count=50)
        assert scope.risk_level == ScopeRisk.CRITICAL
        assert scope.requires_confirmation is True
        assert "count:50>=critical" in scope.indicators

    def test_critical_threshold_with_higher_count(self):
        """Test 100 items is still CRITICAL."""
        scope = detect_dangerous_scope(operation_type="delete_emails", affected_count=100)
        assert scope.risk_level == ScopeRisk.CRITICAL
        assert scope.requires_confirmation is True

    # --- Broad scope pattern tests ---

    def test_broad_scope_all_pattern(self):
        """Test 'all' in query triggers HIGH risk."""
        scope = detect_dangerous_scope(query="delete all emails from Jean")
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.requires_confirmation is True
        # Check indicator contains "all" pattern
        broad_indicators = [i for i in scope.indicators if i.startswith("broad_scope:")]
        assert len(broad_indicators) > 0

    def test_broad_scope_every_pattern(self):
        """Test 'every' pattern triggers HIGH risk."""
        scope = detect_dangerous_scope(query="remove every contact")
        assert scope.risk_level == ScopeRisk.HIGH
        assert scope.requires_confirmation is True

    def test_broad_scope_entire_pattern(self):
        """Test 'entire' pattern triggers HIGH risk."""
        scope = detect_dangerous_scope(query="delete entire inbox")
        assert scope.risk_level == ScopeRisk.HIGH

    # --- Destructive keyword tests ---

    def test_destructive_keyword_delete(self):
        """Test 'delete' keyword is detected."""
        scope = detect_dangerous_scope(query="delete some files")
        destructive_indicators = [i for i in scope.indicators if i.startswith("destructive:")]
        assert len(destructive_indicators) > 0

    def test_destructive_keyword_remove(self):
        """Test 'remove' keyword is detected."""
        scope = detect_dangerous_scope(query="remove contacts")
        destructive_indicators = [i for i in scope.indicators if i.startswith("destructive:")]
        assert len(destructive_indicators) > 0

    def test_destructive_keyword_clear(self):
        """Test 'clear' keyword is detected."""
        scope = detect_dangerous_scope(query="clear the calendar")
        destructive_indicators = [i for i in scope.indicators if i.startswith("destructive:")]
        assert len(destructive_indicators) > 0

    # --- Operation type extraction ---

    def test_operation_type_from_query(self):
        """Test operation type is extracted from query when not provided."""
        scope = detect_dangerous_scope(query="delete emails from John")
        assert "delete" in scope.operation_type or scope.operation_type == "delete_emails"

    def test_explicit_operation_type_used(self):
        """Test explicit operation_type takes precedence."""
        scope = detect_dangerous_scope(
            operation_type="custom_delete",
            query="send emails to everyone",
        )
        assert scope.operation_type == "custom_delete"

    # --- Medium risk + destructive requires confirmation ---

    def test_medium_delete_requires_confirmation(self):
        """Test MEDIUM risk + delete operation requires confirmation."""
        scope = detect_dangerous_scope(operation_type="delete_contacts", affected_count=3)
        assert scope.risk_level == ScopeRisk.MEDIUM
        assert scope.requires_confirmation is True

    def test_medium_read_no_confirmation(self):
        """Test MEDIUM risk + read operation does NOT require confirmation."""
        scope = detect_dangerous_scope(operation_type="list_contacts", affected_count=3)
        assert scope.risk_level == ScopeRisk.MEDIUM
        assert scope.requires_confirmation is False

    # --- Language parameter (legacy, now ignored) ---

    def test_language_parameter_ignored(self):
        """Test language parameter is ignored (patterns are English only)."""
        # French query but patterns are English-only
        scope_fr = detect_dangerous_scope(query="delete all emails", language="fr")
        scope_en = detect_dangerous_scope(query="delete all emails", language="en")
        # Both should have same result since patterns are English
        assert scope_fr.risk_level == scope_en.risk_level
        assert scope_fr.requires_confirmation == scope_en.requires_confirmation


# ============================================================================
# _extract_operation_type Helper Tests
# ============================================================================


class TestExtractOperationType:
    """Tests for _extract_operation_type helper function."""

    def test_extract_delete_keyword(self):
        """Test extraction of 'delete' keyword."""
        result = _extract_operation_type("delete emails from John")
        assert "delete" in result.lower()

    def test_extract_remove_keyword(self):
        """Test extraction of 'remove' keyword."""
        result = _extract_operation_type("remove all contacts")
        assert "remove" in result.lower() or result != "unknown"

    def test_extract_send_keyword(self):
        """Test extraction of 'send' keyword."""
        result = _extract_operation_type("send email to team")
        assert result != "unknown" or "send" in result.lower()

    def test_extract_unknown_query(self):
        """Test unknown query returns 'unknown'."""
        result = _extract_operation_type("xyz abc 123")
        assert result == "unknown"

    def test_extract_empty_query(self):
        """Test empty query returns 'unknown'."""
        result = _extract_operation_type("")
        assert result == "unknown"


# ============================================================================
# _build_reason Helper Tests
# ============================================================================


class TestBuildReason:
    """Tests for _build_reason helper function."""

    def test_critical_reason(self):
        """Test reason for CRITICAL risk."""
        reason = _build_reason(ScopeRisk.CRITICAL, 100, [])
        assert "100" in reason
        assert "Critical" in reason or "critical" in reason.lower()

    def test_high_reason(self):
        """Test reason for HIGH risk."""
        reason = _build_reason(ScopeRisk.HIGH, 20, [])
        assert "20" in reason
        assert "High" in reason or "high" in reason.lower()

    def test_medium_reason(self):
        """Test reason for MEDIUM risk."""
        reason = _build_reason(ScopeRisk.MEDIUM, 5, [])
        assert "5" in reason
        assert "Bulk" in reason or "bulk" in reason.lower()

    def test_low_reason_fallback(self):
        """Test reason for LOW risk (fallback)."""
        reason = _build_reason(ScopeRisk.LOW, 2, [])
        assert "2" in reason


# ============================================================================
# should_escalate_to_destructive_confirm Tests
# ============================================================================


class TestShouldEscalateToDestructiveConfirm:
    """Tests for should_escalate_to_destructive_confirm function."""

    def test_non_delete_tool_returns_none(self):
        """Test non-delete tool does not escalate."""
        result = should_escalate_to_destructive_confirm(
            tool_name="send_email",
            tool_args={"to": "user@example.com"},
            result_count=10,
        )
        assert result is None

    def test_delete_email_escalates_on_high_count(self):
        """Test delete_email with high count escalates."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_email",
            tool_args={},
            result_count=50,
            original_query="delete emails from spam",
        )
        assert result is not None
        assert result.requires_confirmation is True
        assert result.operation_type == "delete_emails"

    def test_delete_emails_escalates_on_high_count(self):
        """Test delete_emails (plural) with high count escalates."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_emails",
            tool_args={},
            result_count=20,
        )
        assert result is not None
        assert result.requires_confirmation is True

    def test_delete_contact_with_low_count_no_escalation(self):
        """Test delete_contact with low count does not escalate."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_contact",
            tool_args={},
            result_count=1,
        )
        assert result is None

    def test_delete_contacts_with_bulk_escalates(self):
        """Test delete_contacts with bulk count escalates."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_contacts",
            tool_args={},
            result_count=15,
        )
        assert result is not None
        assert result.operation_type == "delete_contacts"

    def test_delete_event_escalation(self):
        """Test delete_event/delete_events escalation."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_events",
            tool_args={},
            result_count=25,
        )
        assert result is not None
        assert result.operation_type == "delete_events"

    def test_delete_task_escalation(self):
        """Test delete_task escalation."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_task",
            tool_args={},
            result_count=50,
        )
        assert result is not None
        assert result.operation_type == "delete_tasks"

    def test_delete_file_escalation(self):
        """Test delete_file escalation."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_files",
            tool_args={},
            result_count=30,
        )
        assert result is not None
        assert result.operation_type == "delete_files"

    def test_original_query_affects_risk(self):
        """Test original_query with broad pattern increases risk."""
        # Without broad pattern
        _ = should_escalate_to_destructive_confirm(
            tool_name="delete_emails",
            tool_args={},
            result_count=5,
            original_query="delete old newsletters",
        )

        # With broad pattern
        result_broad = should_escalate_to_destructive_confirm(
            tool_name="delete_emails",
            tool_args={},
            result_count=5,
            original_query="delete all emails from John",
        )

        # Broad pattern should trigger escalation even with lower count
        assert result_broad is not None
        assert result_broad.risk_level in (ScopeRisk.HIGH, ScopeRisk.CRITICAL)

    def test_result_count_none_defaults_to_one(self):
        """Test result_count None defaults to 1."""
        result = should_escalate_to_destructive_confirm(
            tool_name="delete_emails",
            tool_args={},
            result_count=None,
        )
        # Single item deletion should not escalate
        assert result is None


# ============================================================================
# detect_for_each_scope Tests
# ============================================================================


class TestDetectForEachScope:
    """Tests for detect_for_each_scope function."""

    # --- Mutation tool detection ---

    def test_mutation_tool_detected_by_name(self):
        """Test mutation tool is auto-detected from name."""
        scope = detect_for_each_scope(
            iteration_count=5,
            tool_name="send_email_tool",
            is_mutation=False,  # will be overridden
        )
        assert scope.is_mutation is True

    def test_create_tool_is_mutation(self):
        """Test 'create' in tool name detects mutation."""
        scope = detect_for_each_scope(
            iteration_count=5,
            tool_name="create_contact",
            is_mutation=False,
        )
        assert scope.is_mutation is True

    def test_update_tool_is_mutation(self):
        """Test 'update' in tool name detects mutation."""
        scope = detect_for_each_scope(
            iteration_count=3,
            tool_name="update_event",
            is_mutation=False,
        )
        assert scope.is_mutation is True

    def test_delete_tool_is_mutation(self):
        """Test 'delete' in tool name detects mutation."""
        scope = detect_for_each_scope(
            iteration_count=2,
            tool_name="delete_task",
            is_mutation=False,
        )
        assert scope.is_mutation is True

    def test_read_tool_not_mutation(self):
        """Test read-only tool is not a mutation."""
        scope = detect_for_each_scope(
            iteration_count=10,
            tool_name="get_weather",
            is_mutation=False,
        )
        assert scope.is_mutation is False

    # --- Mutation approval thresholds (using mocked settings) ---

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_mutation_threshold_triggers_approval(self, mock_settings):
        """Test mutation with count >= threshold requires approval."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=3,
            tool_name="send_email_tool",
            is_mutation=True,
        )
        assert scope.requires_approval is True
        assert scope.risk_level == ScopeRisk.HIGH
        assert "3 times" in scope.reason or "3" in scope.reason

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_mutation_below_threshold_medium_risk(self, mock_settings):
        """Test mutation with 2 items is MEDIUM risk without approval."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=2,
            tool_name="send_email_tool",
            is_mutation=True,
        )
        assert scope.requires_approval is False
        assert scope.risk_level == ScopeRisk.MEDIUM

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_mutation_single_item_low_risk(self, mock_settings):
        """Test single mutation is LOW risk."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=1,
            tool_name="send_email_tool",
            is_mutation=True,
        )
        assert scope.risk_level == ScopeRisk.LOW
        assert scope.requires_approval is False

    # --- Non-mutation (read-only) thresholds ---

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_non_mutation_warning_threshold(self, mock_settings):
        """Test non-mutation with high count triggers approval."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=10,
            tool_name="get_weather",
            is_mutation=False,
        )
        assert scope.requires_approval is True
        assert scope.risk_level == ScopeRisk.MEDIUM

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_non_mutation_approval_threshold(self, mock_settings):
        """Test non-mutation with moderate count is LOW risk."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=5,
            tool_name="get_weather",
            is_mutation=False,
        )
        assert scope.requires_approval is False
        assert scope.risk_level == ScopeRisk.LOW
        assert scope.reason != ""  # has advisory reason

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_non_mutation_low_count(self, mock_settings):
        """Test non-mutation with low count is safe."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=2,
            tool_name="get_weather",
            is_mutation=False,
        )
        assert scope.requires_approval is False
        assert scope.risk_level == ScopeRisk.LOW

    # --- for_each_max limit tests ---

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_exceeds_for_each_max_triggers_approval(self, mock_settings):
        """Test count exceeding for_each_max always triggers approval."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=15,
            tool_name="get_weather",
            is_mutation=False,
            for_each_max=10,
        )
        assert scope.requires_approval is True
        assert "exceeds limit" in scope.reason

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_exactly_at_for_each_max(self, mock_settings):
        """Test count exactly at for_each_max does not trigger for that reason."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=10,
            tool_name="get_weather",
            is_mutation=False,
            for_each_max=10,
        )
        # At 10 items (warning threshold), it triggers for that reason, not exceeds
        assert scope.requires_approval is True
        assert "exceeds limit" not in scope.reason

    # --- Tool name and basic fields ---

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_tool_name_preserved(self, mock_settings):
        """Test tool_name is preserved in result."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=5,
            tool_name="my_custom_tool",
            is_mutation=False,
        )
        assert scope.tool_name == "my_custom_tool"

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_iteration_count_preserved(self, mock_settings):
        """Test iteration_count is preserved in result."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=7,
            tool_name="get_data",
            is_mutation=False,
        )
        assert scope.iteration_count == 7


# ============================================================================
# Edge Cases and Integration Tests
# ============================================================================


class TestScopeDetectorEdgeCases:
    """Edge cases and integration tests."""

    def test_empty_query_with_operation_type(self):
        """Test empty query with operation type still works."""
        scope = detect_dangerous_scope(operation_type="delete_emails", query="")
        assert scope.operation_type == "delete_emails"

    def test_none_query_with_operation_type(self):
        """Test None query with operation type still works."""
        scope = detect_dangerous_scope(operation_type="delete_emails", query=None)
        assert scope.operation_type == "delete_emails"

    def test_case_insensitive_pattern_matching(self):
        """Test patterns match case-insensitively."""
        scope_lower = detect_dangerous_scope(query="delete all emails")
        scope_upper = detect_dangerous_scope(query="DELETE ALL EMAILS")
        scope_mixed = detect_dangerous_scope(query="Delete All Emails")

        assert scope_lower.risk_level == scope_upper.risk_level
        assert scope_lower.risk_level == scope_mixed.risk_level

    def test_combined_high_count_and_broad_pattern(self):
        """Test both high count and broad pattern increases risk."""
        scope = detect_dangerous_scope(
            query="delete all emails",
            affected_count=50,
        )
        assert scope.risk_level == ScopeRisk.CRITICAL
        assert scope.requires_confirmation is True
        # Should have both count and broad_scope indicators
        count_indicators = [i for i in scope.indicators if i.startswith("count:")]
        broad_indicators = [i for i in scope.indicators if i.startswith("broad_scope:")]
        assert len(count_indicators) > 0
        assert len(broad_indicators) > 0

    @patch("src.domains.agents.services.hitl.scope_detector.settings")
    def test_for_each_explicit_is_mutation_overrides_detection(self, mock_settings):
        """Test explicit is_mutation=True is respected."""
        mock_settings.for_each_mutation_threshold = 3
        mock_settings.for_each_warning_threshold = 10
        mock_settings.for_each_approval_threshold = 5

        scope = detect_for_each_scope(
            iteration_count=5,
            tool_name="safe_read_tool",  # No mutation keywords
            is_mutation=True,  # Explicitly marked as mutation
        )
        assert scope.is_mutation is True
        assert scope.requires_approval is True
        assert scope.risk_level == ScopeRisk.HIGH

    def test_unicode_in_query(self):
        """Test Unicode characters in query don't break detection."""
        scope = detect_dangerous_scope(query="delete all émails with accénts")
        # Should still detect 'all' and 'delete'
        assert scope.risk_level == ScopeRisk.HIGH

    def test_very_long_query(self):
        """Test very long query is handled."""
        long_query = "delete " + "x" * 10000 + " all emails"
        scope = detect_dangerous_scope(query=long_query)
        # Should still detect patterns
        assert scope.operation_type != "unknown" or scope.risk_level != ScopeRisk.LOW
