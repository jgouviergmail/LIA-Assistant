"""
Unit tests for skills injection agent-visibility filtering (F6).

Tests the _is_skill_visible_to_agent function added to injection.py.
"""

from src.domains.skills.injection import _is_skill_visible_to_agent


class TestIsSkillVisibleToAgent:
    """Tests for _is_skill_visible_to_agent() in injection.py."""

    def test_no_visibility_field_visible_to_all(self):
        """Skills without agent_visibility are visible to everyone."""
        skill = {"name": "general"}
        assert _is_skill_visible_to_agent(skill, "research_assistant") is True
        assert _is_skill_visible_to_agent(skill, "principal") is True

    def test_none_visibility_visible_to_all(self):
        """Explicit None is treated as 'visible to all'."""
        skill = {"name": "general", "agent_visibility": None}
        assert _is_skill_visible_to_agent(skill, "any_agent") is True

    def test_include_mode_match(self):
        """Include mode: visible only to listed agents."""
        skill = {
            "name": "deep-research",
            "agent_visibility": ["research_assistant", "data_analyst"],
            "visibility_mode": "include",
        }
        assert _is_skill_visible_to_agent(skill, "research_assistant") is True
        assert _is_skill_visible_to_agent(skill, "data_analyst") is True
        assert _is_skill_visible_to_agent(skill, "writing_assistant") is False

    def test_exclude_mode(self):
        """Exclude mode: hidden from listed agents."""
        skill = {
            "name": "expert-only",
            "agent_visibility": ["principal"],
            "visibility_mode": "exclude",
        }
        assert _is_skill_visible_to_agent(skill, "principal") is False
        assert _is_skill_visible_to_agent(skill, "research_assistant") is True

    def test_string_visibility(self):
        """Single string (not list) is normalized to list."""
        skill = {
            "name": "single",
            "agent_visibility": "data_analyst",
            "visibility_mode": "include",
        }
        assert _is_skill_visible_to_agent(skill, "data_analyst") is True
        assert _is_skill_visible_to_agent(skill, "other") is False

    def test_default_mode_is_include(self):
        """Without visibility_mode, default is 'include'."""
        skill = {
            "name": "default-mode",
            "agent_visibility": ["research_assistant"],
        }
        assert _is_skill_visible_to_agent(skill, "research_assistant") is True
        assert _is_skill_visible_to_agent(skill, "other") is False

    def test_empty_list_visibility(self):
        """Empty list with include mode = visible to nobody."""
        skill = {
            "name": "nobody",
            "agent_visibility": [],
            "visibility_mode": "include",
        }
        # Empty list is falsy in Python → treated as "no constraint" → visible to all
        assert _is_skill_visible_to_agent(skill, "any_agent") is True

    def test_unknown_mode_defaults_visible(self):
        """Unknown visibility_mode defaults to visible."""
        skill = {
            "name": "unknown",
            "agent_visibility": ["some_agent"],
            "visibility_mode": "unknown_mode",
        }
        assert _is_skill_visible_to_agent(skill, "any_agent") is True
