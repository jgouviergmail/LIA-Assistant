"""
Unit tests for parameter validation in parallel executor.

Created: 2026-01-02
Focus: _is_param_empty and _validate_required_params functions
Coverage: MULTI-ORDINAL FIX - AND/OR validation logic for batch mode tools

Tests cover:
- AND logic (list of required params - all must be present)
- OR logic (one_of syntax - at least one must be present)
- Edge cases (empty values, None, whitespace)
- Rétro-compatibility with existing tool configurations
"""

import pytest

from src.domains.agents.orchestration.parallel_executor import (
    REQUIRED_PARAMS_BY_TOOL,
    _get_jinja_required_params,
    _is_param_empty,
    _validate_required_params,
)

# =============================================================================
# Tests for _is_param_empty helper
# =============================================================================


class TestIsParamEmpty:
    """Tests for _is_param_empty helper function."""

    def test_none_is_empty(self):
        """None should be considered empty."""
        assert _is_param_empty(None) is True

    def test_empty_string_is_empty(self):
        """Empty string should be considered empty."""
        assert _is_param_empty("") is True

    def test_whitespace_string_is_empty(self):
        """Whitespace-only string should be considered empty."""
        assert _is_param_empty("   ") is True
        assert _is_param_empty("\t\n") is True

    def test_empty_list_is_empty(self):
        """Empty list should be considered empty."""
        assert _is_param_empty([]) is True

    def test_non_empty_string_is_not_empty(self):
        """Non-empty string should not be empty."""
        assert _is_param_empty("hello") is False
        assert _is_param_empty("  hello  ") is False  # Has content

    def test_non_empty_list_is_not_empty(self):
        """Non-empty list should not be empty."""
        assert _is_param_empty(["item"]) is False
        assert _is_param_empty(["a", "b"]) is False

    def test_zero_is_not_empty(self):
        """Zero should not be considered empty (valid value)."""
        assert _is_param_empty(0) is False

    def test_false_is_not_empty(self):
        """False should not be considered empty (valid value)."""
        assert _is_param_empty(False) is False

    def test_dict_is_not_empty(self):
        """Dict should not be considered empty (not handled)."""
        assert _is_param_empty({}) is False  # Not in empty check
        assert _is_param_empty({"key": "value"}) is False


# =============================================================================
# Tests for _validate_required_params - AND logic (list)
# =============================================================================


class TestValidateRequiredParamsAndLogic:
    """Tests for AND logic (list of required params)."""

    def test_and_logic_all_params_present(self):
        """All required params present should pass."""
        is_valid, error = _validate_required_params(
            "send_email_tool",
            {"to": "user@example.com", "subject": "Test", "body": "Content"},
        )
        assert is_valid is True
        assert error is None

    def test_and_logic_missing_one_param(self):
        """Missing one required param should fail."""
        # Use create_event_tool which requires ["summary", "start_datetime", "end_datetime"]
        is_valid, error = _validate_required_params(
            "create_event_tool",
            {"summary": "Meeting", "start_datetime": "2026-01-15T10:00:00"},  # Missing end_datetime
        )
        assert is_valid is False
        assert "end_datetime" in error
        assert "empty" in error.lower()

    def test_and_logic_empty_string_param(self):
        """Empty string for required param should fail."""
        # Use create_event_tool which requires ["summary", "start_datetime", "end_datetime"]
        is_valid, error = _validate_required_params(
            "create_event_tool",
            {
                "summary": "",
                "start_datetime": "2026-01-15T10:00:00",
                "end_datetime": "2026-01-15T11:00:00",
            },
        )
        assert is_valid is False
        assert "summary" in error

    def test_and_logic_none_param(self):
        """None for required param should fail."""
        is_valid, error = _validate_required_params(
            "send_email_tool",
            {"to": None, "subject": "Test", "body": "Content"},
        )
        assert is_valid is False
        assert "to" in error

    def test_empty_required_list_always_passes(self):
        """Empty required list (all optional) should always pass."""
        is_valid, error = _validate_required_params(
            "search_emails_tool",
            {},  # No params at all
        )
        assert is_valid is True
        assert error is None

    def test_empty_required_list_with_extra_params(self):
        """Empty required list with extra params should pass."""
        is_valid, error = _validate_required_params(
            "search_emails_tool",
            {"query": "test", "limit": 10},
        )
        assert is_valid is True
        assert error is None


# =============================================================================
# Tests for _validate_required_params - Unified tools v2.0
# =============================================================================


class TestValidateUnifiedToolsV2:
    """Tests for unified tools v2.0 (all params optional)."""

    def test_unified_emails_tool_all_optional(self):
        """get_emails_tool should pass with any params (v2.0 unified)."""
        # No params at all
        is_valid, error = _validate_required_params("get_emails_tool", {})
        assert is_valid is True
        assert error is None

    def test_unified_emails_tool_with_query(self):
        """get_emails_tool should pass with query param."""
        is_valid, error = _validate_required_params(
            "get_emails_tool",
            {"query": "from:test@example.com"},
        )
        assert is_valid is True
        assert error is None

    def test_unified_contacts_tool_all_optional(self):
        """get_contacts_tool should pass with any params (v2.0 unified)."""
        is_valid, error = _validate_required_params("get_contacts_tool", {})
        assert is_valid is True
        assert error is None

    def test_unified_events_tool_all_optional(self):
        """get_events_tool should pass with any params (v2.0 unified)."""
        is_valid, error = _validate_required_params("get_events_tool", {})
        assert is_valid is True
        assert error is None

    def test_unified_files_tool_all_optional(self):
        """get_files_tool should pass with any params (v2.0 unified)."""
        is_valid, error = _validate_required_params("get_files_tool", {})
        assert is_valid is True
        assert error is None

    def test_unified_tasks_tool_all_optional(self):
        """get_tasks_tool should pass with any params (v2.0 unified)."""
        is_valid, error = _validate_required_params("get_tasks_tool", {})
        assert is_valid is True
        assert error is None

    def test_unified_places_tool_all_optional(self):
        """get_places_tool should pass with any params (v2.0 unified)."""
        is_valid, error = _validate_required_params("get_places_tool", {})
        assert is_valid is True
        assert error is None


# =============================================================================
# Tests for all unified tools v2.0 (rétro-compatibility)
# =============================================================================


class TestUnifiedToolsValidation:
    """Tests verifying all unified tools v2.0 accept optional params."""

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_emails_tool",
            "get_contacts_tool",
            "get_events_tool",
            "get_files_tool",
            "get_tasks_tool",
            "get_places_tool",
        ],
    )
    def test_unified_tool_no_params_passes(self, tool_name):
        """Each unified tool should pass without any params (v2.0 all optional)."""
        is_valid, error = _validate_required_params(
            tool_name,
            {},
        )
        assert is_valid is True, f"{tool_name} should pass without params"
        assert error is None

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_emails_tool",
            "get_contacts_tool",
            "get_events_tool",
            "get_files_tool",
            "get_tasks_tool",
            "get_places_tool",
        ],
    )
    def test_unified_tool_with_extra_params_passes(self, tool_name):
        """Each unified tool should pass with extra params."""
        is_valid, error = _validate_required_params(
            tool_name,
            {"query": "test", "extra_param": "value"},
        )
        assert is_valid is True, f"{tool_name} should pass with extra params"


# =============================================================================
# Tests for unknown/missing tool configurations
# =============================================================================


class TestUnknownToolConfigurations:
    """Tests for edge cases with unknown tools."""

    def test_unknown_tool_passes(self):
        """Unknown tool should pass (no config = no validation)."""
        is_valid, error = _validate_required_params(
            "unknown_future_tool",
            {"any_param": "value"},
        )
        assert is_valid is True
        assert error is None

    def test_unknown_tool_empty_args_passes(self):
        """Unknown tool with empty args should pass."""
        is_valid, error = _validate_required_params(
            "unknown_future_tool",
            {},
        )
        assert is_valid is True
        assert error is None


# =============================================================================
# Tests for REQUIRED_PARAMS_BY_TOOL configuration integrity
# =============================================================================


class TestRequiredParamsConfiguration:
    """Tests verifying REQUIRED_PARAMS_BY_TOOL is correctly configured."""

    def test_unified_tools_have_empty_list(self):
        """All unified v2.0 tools should have empty list (all optional)."""
        unified_tools = [
            "get_emails_tool",
            "get_contacts_tool",
            "get_events_tool",
            "get_files_tool",
            "get_tasks_tool",
            "get_places_tool",
        ]
        for tool_name in unified_tools:
            config = REQUIRED_PARAMS_BY_TOOL.get(tool_name)
            assert config is not None, f"{tool_name} missing from REQUIRED_PARAMS_BY_TOOL"
            assert isinstance(config, list), f"{tool_name} should use list config"
            assert len(config) == 0, f"{tool_name} should have empty list (v2.0 all optional)"

    def test_and_logic_tools_use_list(self):
        """AND logic tools should use list syntax."""
        and_tools = [
            "send_email_tool",
            "create_event_tool",
            "create_task_tool",
            "perplexity_search_tool",
        ]
        for tool_name in and_tools:
            config = REQUIRED_PARAMS_BY_TOOL.get(tool_name)
            assert config is not None, f"{tool_name} missing from REQUIRED_PARAMS_BY_TOOL"
            assert isinstance(config, list), f"{tool_name} should use list config"
            assert len(config) > 0, f"{tool_name} should have required params"

    def test_optional_tools_have_empty_list(self):
        """Optional-only tools should have empty list."""
        optional_tools = [
            "get_emails_tool",
            "get_contacts_tool",
            "get_events_tool",
            "list_calendars_tool",
        ]
        for tool_name in optional_tools:
            config = REQUIRED_PARAMS_BY_TOOL.get(tool_name)
            assert config is not None, f"{tool_name} missing from REQUIRED_PARAMS_BY_TOOL"
            assert isinstance(config, list), f"{tool_name} should use list config"
            assert len(config) == 0, f"{tool_name} should have empty list (all optional)"


# =============================================================================
# Tests for _get_jinja_required_params (Jinja/validation separation)
# =============================================================================


class TestGetJinjaRequiredParams:
    """Tests for _get_jinja_required_params helper function.

    This function extracts required params for Jinja template evaluation.
    Unified tools v2.0 have all optional params, so they return [].
    """

    def test_and_logic_tool_returns_list(self):
        """AND logic tools should return their param list for Jinja validation."""
        # Use create_event_tool which has multiple required params
        result = _get_jinja_required_params("create_event_tool")
        assert isinstance(result, list)
        assert "summary" in result
        assert "start_datetime" in result
        assert "end_datetime" in result

    def test_unified_tool_returns_empty_list(self):
        """Unified v2.0 tools should return [] (all optional)."""
        result = _get_jinja_required_params("get_emails_tool")
        assert result == []

    def test_optional_tool_returns_empty_list(self):
        """Optional-only tools should return []."""
        result = _get_jinja_required_params("get_events_tool")
        assert result == []

    def test_unknown_tool_returns_empty_list(self):
        """Unknown tools should return [] (safe default)."""
        result = _get_jinja_required_params("unknown_future_tool")
        assert result == []

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_emails_tool",
            "get_contacts_tool",
            "get_events_tool",
            "get_files_tool",
            "get_tasks_tool",
            "get_places_tool",
        ],
    )
    def test_all_unified_tools_return_empty_for_jinja(self, tool_name):
        """All unified v2.0 tools should return [] for Jinja validation."""
        result = _get_jinja_required_params(tool_name)
        assert result == [], f"{tool_name} should return [] for Jinja"

    @pytest.mark.parametrize(
        "tool_name,expected_params",
        [
            ("send_email_tool", ["to"]),  # Only "to" required with content_instruction fallback
            ("create_event_tool", ["summary", "start_datetime", "end_datetime"]),
            ("create_task_tool", ["title"]),
            ("perplexity_search_tool", ["query"]),
        ],
    )
    def test_and_logic_tools_return_correct_params(self, tool_name, expected_params):
        """AND logic tools should return their full param list."""
        result = _get_jinja_required_params(tool_name)
        assert result == expected_params
