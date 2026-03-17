"""
Unit tests for sub-agent skill resolver.

Tests tool filtering, system prompt building, and skill visibility.
"""

from unittest.mock import MagicMock

from src.domains.sub_agents.skill_resolver import (
    build_subagent_system_prompt,
    is_skill_visible_to_agent,
    resolve_tools_for_subagent,
)


class TestResolveToolsForSubagent:
    """Tests for resolve_tools_for_subagent()."""

    def _make_tool(self, name: str) -> MagicMock:
        tool = MagicMock()
        tool.name = name
        return tool

    def test_block_write_tools(self):
        """Blocked tools are filtered out."""
        tools = [self._make_tool("search_emails_tool"), self._make_tool("send_email_tool")]
        result = resolve_tools_for_subagent(
            allowed_tools=[], blocked_tools=["send_email_tool"], all_tools=tools
        )
        assert len(result) == 1
        assert result[0].name == "search_emails_tool"

    def test_block_sub_agent_tools(self):
        """Sub-agent tools are always blocked (depth=1)."""
        tools = [
            self._make_tool("search_emails_tool"),
            self._make_tool("execute_sub_agent_tool"),
            self._make_tool("create_sub_agent_tool"),
        ]
        result = resolve_tools_for_subagent(allowed_tools=[], blocked_tools=[], all_tools=tools)
        assert len(result) == 1
        assert result[0].name == "search_emails_tool"

    def test_allowed_tools_whitelist(self):
        """Only allowed tools are included when whitelist is non-empty."""
        tools = [
            self._make_tool("search_emails_tool"),
            self._make_tool("get_weather_tool"),
            self._make_tool("brave_search_tool"),
        ]
        result = resolve_tools_for_subagent(
            allowed_tools=["search_emails_tool", "brave_search_tool"],
            blocked_tools=[],
            all_tools=tools,
        )
        assert len(result) == 2
        names = {t.name for t in result}
        assert names == {"search_emails_tool", "brave_search_tool"}

    def test_empty_allowed_means_all(self):
        """Empty allowed_tools means all tools (except blocked)."""
        tools = [self._make_tool("a"), self._make_tool("b"), self._make_tool("c")]
        result = resolve_tools_for_subagent(allowed_tools=[], blocked_tools=["b"], all_tools=tools)
        assert len(result) == 2

    def test_blocked_takes_priority(self):
        """Blocked tools override allowed tools."""
        tools = [self._make_tool("search_emails_tool")]
        result = resolve_tools_for_subagent(
            allowed_tools=["search_emails_tool"],
            blocked_tools=["search_emails_tool"],
            all_tools=tools,
        )
        assert len(result) == 0


class TestBuildSubagentSystemPrompt:
    """Tests for build_subagent_system_prompt()."""

    def test_basic_prompt(self):
        """Build prompt with required fields only."""
        prompt = build_subagent_system_prompt(system_prompt="You are a research specialist.")
        assert "read-only" in prompt.lower()
        assert "You are a research specialist." in prompt

    def test_with_all_fields(self):
        """Build prompt with all optional fields."""
        prompt = build_subagent_system_prompt(
            system_prompt="Research specialist.",
            personality_instruction="Be concise.",
            context_instructions="Focus on recent data.",
            last_execution_summary="Found 3 articles.",
            skills_context="## Skill: deep-search\nInstructions here.",
        )
        assert "Research specialist." in prompt
        assert "Be concise." in prompt
        assert "Focus on recent data." in prompt
        assert "Previous execution context: Found 3 articles." in prompt
        assert "deep-search" in prompt

    def test_read_only_prefix_first(self):
        """Read-only prefix is at the beginning."""
        prompt = build_subagent_system_prompt(system_prompt="Custom instructions.")
        assert prompt.startswith("You are a read-only sub-agent.")


class TestIsSkillVisibleToAgent:
    """Tests for is_skill_visible_to_agent()."""

    def test_no_visibility_field(self):
        """Skills without agent_visibility are visible to all."""
        skill = {"name": "web-search", "description": "Search"}
        assert is_skill_visible_to_agent(skill, "research_assistant") is True
        assert is_skill_visible_to_agent(skill, "principal") is True

    def test_include_mode_match(self):
        """Include mode: visible to listed agents."""
        skill = {
            "name": "deep-research",
            "agent_visibility": ["research_assistant"],
            "visibility_mode": "include",
        }
        assert is_skill_visible_to_agent(skill, "research_assistant") is True
        assert is_skill_visible_to_agent(skill, "writing_assistant") is False

    def test_exclude_mode(self):
        """Exclude mode: hidden from listed agents."""
        skill = {
            "name": "general-skill",
            "agent_visibility": ["principal"],
            "visibility_mode": "exclude",
        }
        assert is_skill_visible_to_agent(skill, "principal") is False
        assert is_skill_visible_to_agent(skill, "research_assistant") is True

    def test_string_visibility(self):
        """agent_visibility as string (not list) is handled."""
        skill = {
            "name": "single-agent",
            "agent_visibility": "data_analyst",
            "visibility_mode": "include",
        }
        assert is_skill_visible_to_agent(skill, "data_analyst") is True
        assert is_skill_visible_to_agent(skill, "other") is False

    def test_default_include_mode(self):
        """Default visibility_mode is 'include'."""
        skill = {
            "name": "default-mode",
            "agent_visibility": ["research_assistant"],
        }
        assert is_skill_visible_to_agent(skill, "research_assistant") is True
        assert is_skill_visible_to_agent(skill, "other") is False
