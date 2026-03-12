"""
Unit tests for HITL configuration utilities.

Phase: Session 11 - Tests Quick Wins (utils/hitl_config)
Created: 2025-11-20
Updated: 2026-01-19 - Removed tests for removed tool_approval_enabled flag
Enhanced: 2026-02-05 - Added comprehensive edge cases and integration tests

Focus: Tool approval requirements (manifest-driven)
NOTE: Tool approval is always enabled (no global kill switch)
"""

from unittest.mock import Mock, patch

import pytest

from src.domains.agents.utils.hitl_config import (
    get_approval_config,
    requires_approval,
)


class TestRequiresApproval:
    """Tests for requires_approval() function."""

    def test_requires_approval_when_tool_requires_hitl(self):
        """Test that requires_approval returns True when manifest.permissions.hitl_required=True."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            # Mock registry - tool requires approval
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            result = requires_approval("search_contacts_tool")

            # Verify registry was queried
            mock_registry.requires_tool_approval.assert_called_once_with("search_contacts_tool")
            assert result is True

    def test_requires_approval_when_tool_does_not_require_hitl(self):
        """Test that requires_approval returns False when manifest.permissions.hitl_required=False."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            # Mock registry - tool does NOT require approval
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = False
            mock_get_registry.return_value = mock_registry

            result = requires_approval("get_context_state")

            # Verify registry was queried
            mock_registry.requires_tool_approval.assert_called_once_with("get_context_state")
            assert result is False

    def test_requires_approval_unknown_tool(self):
        """Test that requires_approval returns False for unknown tools (defensive)."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            # Mock registry - tool not found, defaults to False
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = False
            mock_get_registry.return_value = mock_registry

            result = requires_approval("unknown_tool")

            assert result is False

    def test_requires_approval_logs_when_required(self):
        """Test that requires_approval logs when tool requires approval."""
        with (
            patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry,
            patch("src.domains.agents.utils.hitl_config.logger") as mock_logger,
        ):
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            requires_approval("test_tool")

            # Verify debug log was called
            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args[0]
            assert call_args[0] == "tool_requires_approval"


class TestGetApprovalConfig:
    """Tests for get_approval_config() function."""

    def test_get_approval_config_returns_dict(self):
        """Test that get_approval_config returns a dict."""
        config = get_approval_config("search_contacts_tool")
        assert isinstance(config, dict)

    def test_get_approval_config_contains_allowed_decisions(self):
        """Test that config contains 'allowed_decisions' key."""
        config = get_approval_config("search_contacts_tool")
        assert "allowed_decisions" in config

    def test_get_approval_config_allowed_decisions_format(self):
        """Test that allowed_decisions is a list."""
        config = get_approval_config("search_contacts_tool")
        assert isinstance(config["allowed_decisions"], list)

    def test_get_approval_config_contains_all_decisions(self):
        """Test that config contains approve, edit, reject."""
        config = get_approval_config("search_contacts_tool")
        decisions = config["allowed_decisions"]
        assert "approve" in decisions
        assert "edit" in decisions
        assert "reject" in decisions

    def test_get_approval_config_same_for_all_tools(self):
        """Test that all tools get the same config (current behavior)."""
        config1 = get_approval_config("tool1")
        config2 = get_approval_config("tool2")
        assert config1 == config2

    def test_get_approval_config_exact_structure(self):
        """Test exact structure of returned config."""
        config = get_approval_config("test_tool")
        assert config == {"allowed_decisions": ["approve", "edit", "reject"]}


# ============================================================================
# Additional tests for requires_approval() - edge cases
# ============================================================================


class TestRequiresApprovalEdgeCases:
    """Edge case tests for requires_approval() function."""

    def test_requires_approval_returns_boolean_true(self):
        """Test that requires_approval returns a boolean True."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            result = requires_approval("test_tool")

            assert result is True
            assert isinstance(result, bool)

    def test_requires_approval_returns_boolean_false(self):
        """Test that requires_approval returns a boolean False."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = False
            mock_get_registry.return_value = mock_registry

            result = requires_approval("test_tool")

            assert result is False
            assert isinstance(result, bool)

    def test_requires_approval_does_not_log_when_not_required(self):
        """Test that requires_approval does NOT log when tool does not require approval."""
        with (
            patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry,
            patch("src.domains.agents.utils.hitl_config.logger") as mock_logger,
        ):
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = False
            mock_get_registry.return_value = mock_registry

            requires_approval("no_approval_tool")

            # Verify debug log was NOT called
            mock_logger.debug.assert_not_called()

    def test_requires_approval_with_empty_string(self):
        """Test requires_approval with empty tool name."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = False
            mock_get_registry.return_value = mock_registry

            result = requires_approval("")

            mock_registry.requires_tool_approval.assert_called_once_with("")
            assert result is False

    def test_requires_approval_with_special_characters(self):
        """Test requires_approval with tool name containing special characters."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            result = requires_approval("tool-with_special.chars")

            mock_registry.requires_tool_approval.assert_called_once_with("tool-with_special.chars")
            assert result is True

    def test_requires_approval_with_unicode_characters(self):
        """Test requires_approval with unicode tool name."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = False
            mock_get_registry.return_value = mock_registry

            result = requires_approval("tool_émoji_🔧")

            mock_registry.requires_tool_approval.assert_called_once_with("tool_émoji_🔧")
            assert result is False

    def test_requires_approval_caches_registry_lookup(self):
        """Test that requires_approval calls registry for each invocation."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            # Call multiple times
            requires_approval("tool1")
            requires_approval("tool2")
            requires_approval("tool1")  # Same tool again

            # Registry should be called each time (no caching in function)
            assert mock_get_registry.call_count == 3

    @pytest.mark.parametrize(
        "tool_name",
        [
            "search_contacts_tool",
            "create_event_tool",
            "send_email_tool",
            "delete_task_tool",
            "update_calendar_event",
        ],
    )
    def test_requires_approval_various_tool_names(self, tool_name: str):
        """Test requires_approval with various realistic tool names."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            result = requires_approval(tool_name)

            mock_registry.requires_tool_approval.assert_called_once_with(tool_name)
            assert result is True


# ============================================================================
# Additional tests for requires_approval() - logging
# ============================================================================


class TestRequiresApprovalLogging:
    """Logging tests for requires_approval() function."""

    def test_requires_approval_log_contains_tool_name(self):
        """Test that log message contains tool name."""
        with (
            patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry,
            patch("src.domains.agents.utils.hitl_config.logger") as mock_logger,
        ):
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            requires_approval("my_test_tool")

            # Verify tool_name is in kwargs
            call_kwargs = mock_logger.debug.call_args[1]
            assert call_kwargs["tool_name"] == "my_test_tool"

    def test_requires_approval_log_contains_source(self):
        """Test that log message contains source information."""
        with (
            patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry,
            patch("src.domains.agents.utils.hitl_config.logger") as mock_logger,
        ):
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            requires_approval("test_tool")

            # Verify source is in kwargs
            call_kwargs = mock_logger.debug.call_args[1]
            assert "source" in call_kwargs
            assert "manifest" in call_kwargs["source"]


# ============================================================================
# Additional tests for get_approval_config() - edge cases
# ============================================================================


class TestGetApprovalConfigEdgeCases:
    """Edge case tests for get_approval_config() function."""

    def test_get_approval_config_with_empty_string(self):
        """Test get_approval_config with empty tool name."""
        config = get_approval_config("")
        assert config == {"allowed_decisions": ["approve", "edit", "reject"]}

    def test_get_approval_config_with_none_like_name(self):
        """Test get_approval_config with 'None' as string."""
        config = get_approval_config("None")
        assert config == {"allowed_decisions": ["approve", "edit", "reject"]}

    def test_get_approval_config_decisions_count(self):
        """Test that allowed_decisions has exactly 3 elements."""
        config = get_approval_config("test_tool")
        assert len(config["allowed_decisions"]) == 3

    def test_get_approval_config_decisions_are_strings(self):
        """Test that all decisions are strings."""
        config = get_approval_config("test_tool")
        for decision in config["allowed_decisions"]:
            assert isinstance(decision, str)

    def test_get_approval_config_decisions_are_lowercase(self):
        """Test that all decisions are lowercase."""
        config = get_approval_config("test_tool")
        for decision in config["allowed_decisions"]:
            assert decision == decision.lower()

    def test_get_approval_config_returns_new_dict_each_time(self):
        """Test that get_approval_config returns a new dict each call."""
        config1 = get_approval_config("tool1")
        config2 = get_approval_config("tool2")
        # Should be equal but not the same object
        assert config1 == config2
        assert config1 is not config2

    def test_get_approval_config_returns_new_list_each_time(self):
        """Test that get_approval_config returns a new list in dict each call."""
        config1 = get_approval_config("tool1")
        config2 = get_approval_config("tool1")
        # Lists should be equal but not the same object
        assert config1["allowed_decisions"] == config2["allowed_decisions"]
        assert config1["allowed_decisions"] is not config2["allowed_decisions"]

    def test_get_approval_config_mutation_does_not_affect_future_calls(self):
        """Test that mutating returned config doesn't affect future calls."""
        config1 = get_approval_config("tool1")
        config1["allowed_decisions"].append("custom")
        config1["extra_key"] = "extra_value"

        config2 = get_approval_config("tool1")
        # Should be clean, unaffected by mutations
        assert "custom" not in config2["allowed_decisions"]
        assert "extra_key" not in config2

    @pytest.mark.parametrize(
        "tool_name",
        [
            "search_contacts_tool",
            "create_event_tool",
            "send_email_tool",
            "delete_task_tool",
            "unknown_tool",
            "",
            "tool-with-dashes",
            "tool_with_underscores",
        ],
    )
    def test_get_approval_config_consistent_for_various_tools(self, tool_name: str):
        """Test that all tools get consistent config."""
        config = get_approval_config(tool_name)
        assert config == {"allowed_decisions": ["approve", "edit", "reject"]}


# ============================================================================
# Additional tests for get_approval_config() - decisions
# ============================================================================


class TestGetApprovalConfigDecisions:
    """Tests for allowed decisions in get_approval_config()."""

    def test_get_approval_config_approve_is_first(self):
        """Test that 'approve' is the first decision (primary action)."""
        config = get_approval_config("test_tool")
        assert config["allowed_decisions"][0] == "approve"

    def test_get_approval_config_edit_is_second(self):
        """Test that 'edit' is the second decision."""
        config = get_approval_config("test_tool")
        assert config["allowed_decisions"][1] == "edit"

    def test_get_approval_config_reject_is_third(self):
        """Test that 'reject' is the third decision."""
        config = get_approval_config("test_tool")
        assert config["allowed_decisions"][2] == "reject"

    def test_get_approval_config_no_duplicate_decisions(self):
        """Test that there are no duplicate decisions."""
        config = get_approval_config("test_tool")
        decisions = config["allowed_decisions"]
        assert len(decisions) == len(set(decisions))


# ============================================================================
# Integration tests
# ============================================================================


class TestHITLConfigIntegration:
    """Integration tests for HITL configuration utilities."""

    def test_workflow_check_approval_then_get_config(self):
        """Test typical workflow: check if approval needed, then get config."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            tool_name = "create_event_tool"

            # Step 1: Check if approval is required
            if requires_approval(tool_name):
                # Step 2: Get approval config
                config = get_approval_config(tool_name)

                # Verify workflow completed
                assert "approve" in config["allowed_decisions"]

    def test_workflow_skip_config_when_no_approval_needed(self):
        """Test workflow when approval is not needed."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            mock_registry.requires_tool_approval.return_value = False
            mock_get_registry.return_value = mock_registry

            tool_name = "get_weather_tool"
            config_fetched = False

            # Step 1: Check if approval is required
            if requires_approval(tool_name):
                config_fetched = True
                get_approval_config(tool_name)

            # Verify config was NOT fetched
            assert config_fetched is False

    def test_multiple_tools_approval_check(self):
        """Test checking approval for multiple tools."""
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = Mock()
            # First tool requires approval, second doesn't
            mock_registry.requires_tool_approval.side_effect = [True, False, True]
            mock_get_registry.return_value = mock_registry

            tools = ["create_event", "get_weather", "send_email"]
            approval_needed = [requires_approval(t) for t in tools]

            assert approval_needed == [True, False, True]

    def test_config_can_be_used_for_ui_rendering(self):
        """Test that config structure is suitable for UI rendering."""
        config = get_approval_config("test_tool")

        # Simulate UI button generation
        buttons = []
        for decision in config["allowed_decisions"]:
            buttons.append({"label": decision.title(), "action": decision})

        assert len(buttons) == 3
        assert buttons[0]["label"] == "Approve"
        assert buttons[1]["label"] == "Edit"
        assert buttons[2]["label"] == "Reject"
