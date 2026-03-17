"""
Unit tests for Sub-Agents constants and templates.
"""

from src.domains.sub_agents.constants import (
    SUBAGENT_DEFAULT_BLOCKED_TOOLS,
    SUBAGENT_READ_ONLY_PREFIX,
    SUBAGENT_TEMPLATES,
    get_template_by_id,
)


class TestTemplates:
    """Tests for pre-defined templates."""

    def test_templates_exist(self):
        """At least 3 templates are defined."""
        assert len(SUBAGENT_TEMPLATES) >= 3

    def test_template_structure(self):
        """Each template has all required fields."""
        required_fields = {
            "id",
            "name_default",
            "description_default",
            "icon",
            "system_prompt",
            "suggested_skill_ids",
            "suggested_tools",
            "default_blocked_tools",
        }
        for template in SUBAGENT_TEMPLATES:
            missing = required_fields - set(template.keys())
            assert not missing, f"Template {template['id']} missing: {missing}"

    def test_template_ids_unique(self):
        """All template IDs are unique."""
        ids = [t["id"] for t in SUBAGENT_TEMPLATES]
        assert len(ids) == len(set(ids))

    def test_templates_have_i18n_keys(self):
        """Each template has i18n keys for name and description."""
        for template in SUBAGENT_TEMPLATES:
            assert "name_i18n_key" in template
            assert "description_i18n_key" in template
            assert template["name_i18n_key"].startswith("sub_agents.templates.")
            assert template["description_i18n_key"].startswith("sub_agents.templates.")

    def test_default_blocked_tools_non_empty(self):
        """Default blocked tools list is not empty."""
        assert len(SUBAGENT_DEFAULT_BLOCKED_TOOLS) > 0

    def test_blocked_tools_include_write_operations(self):
        """Blocked tools include key write/destructive operations."""
        assert "send_email_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "delete_email_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "create_event_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "delete_event_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS
        assert "create_task_tool" in SUBAGENT_DEFAULT_BLOCKED_TOOLS


class TestGetTemplateById:
    """Tests for get_template_by_id()."""

    def test_found(self):
        """Return template when found."""
        template = get_template_by_id("research_assistant")
        assert template is not None
        assert template["id"] == "research_assistant"

    def test_not_found(self):
        """Return None for unknown ID."""
        assert get_template_by_id("nonexistent") is None


class TestReadOnlyPrefix:
    """Tests for read-only system prompt prefix."""

    def test_prefix_content(self):
        """Prefix mentions read-only constraint."""
        assert "read-only" in SUBAGENT_READ_ONLY_PREFIX.lower()
        assert "MUST NOT" in SUBAGENT_READ_ONLY_PREFIX
