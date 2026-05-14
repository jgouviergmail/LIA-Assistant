"""Unit tests for the surviving sub-agents constants (post-ADR-083 Phase 2)."""

from src.domains.sub_agents.constants import SUBAGENT_DEFAULT_BLOCKED_TOOLS


class TestDefaultBlockedTools:
    """Tests for the read-only enforcement list consumed by resolve_tools_for_subagent."""

    def test_default_blocked_tools_non_empty(self):
        """Default blocked tools list is not empty."""
        assert len(SUBAGENT_DEFAULT_BLOCKED_TOOLS) > 0

    def test_blocked_tools_include_write_operations(self):
        """Blocked tools include key write/destructive operations across domains."""
        # Email write
        assert "send_email_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "delete_email_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        # Calendar write
        assert "create_event_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "delete_event_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        # Tasks write
        assert "create_task_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS

    def test_blocked_tools_do_not_include_read_operations(self):
        """Read-only tools must NOT be in the default blocklist."""
        assert "get_emails_tool" not in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "search_emails_tool" not in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "get_events_tool" not in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "list_tasks_tool" not in SUBAGENT_DEFAULT_BLOCKED_TOOLS
