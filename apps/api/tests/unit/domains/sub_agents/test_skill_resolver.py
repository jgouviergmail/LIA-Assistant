"""Unit tests for sub-agent tool filtering and skill visibility (post-ADR-083 Phase 2).

`build_subagent_system_prompt` and `resolve_skills_context` were deleted along
with the bespoke `SubAgentExecutor` pipeline; tests for them are gone too.
"""

from unittest.mock import MagicMock

import pytest

from src.domains.sub_agents.skill_resolver import (
    is_skill_visible_to_agent,
    resolve_tools_for_subagent,
)


@pytest.fixture(autouse=True)
def _all_fakes_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise the allow/block MECHANICS, not the policy filter.

    Since ADR-263 the resolver also refuses anything that is not declared
    ``read``; the fakes below have no manifest, so they declare one here and
    the policy filter has its own file (``test_subagent_is_read_only_by_policy``).
    """
    monkeypatch.setattr("src.domains.agents.effects.runtime.resolve_policy", lambda _name: "read")


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
            allowed_tools=[],
            blocked_tools=["send_email_tool"],
            all_tools=tools,
            policy_of=lambda _n: "read",
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
        result = resolve_tools_for_subagent(
            allowed_tools=[], blocked_tools=[], all_tools=tools, policy_of=lambda _n: "read"
        )
        assert len(result) == 1
        assert result[0].name == "search_emails_tool"

    def test_block_delegate_to_sub_agent_tool(self):
        """ADR-083: delegate_to_sub_agent_tool MUST be excluded from a sub-agent's toolset.

        Anti-recursion: with ReactSubAgentRunner picking up tools from the global
        registry, the delegate tool would otherwise be available — a sub-agent
        could spawn another sub-agent and the depth limit would only catch it
        after the fact. Exclusion at the tool-resolution layer is the primary
        anti-recursion mechanism.
        """
        tools = [
            self._make_tool("search_emails_tool"),
            self._make_tool("delegate_to_sub_agent_tool"),
        ]
        result = resolve_tools_for_subagent(
            allowed_tools=[], blocked_tools=[], all_tools=tools, policy_of=lambda _n: "read"
        )
        names = {t.name for t in result}
        assert "delegate_to_sub_agent_tool" not in names
        assert "search_emails_tool" in names

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
            policy_of=lambda _n: "read",
        )
        assert len(result) == 2
        names = {t.name for t in result}
        assert names == {"search_emails_tool", "brave_search_tool"}

    def test_empty_allowed_means_all(self):
        """Empty allowed_tools means all tools (except blocked)."""
        tools = [self._make_tool("a"), self._make_tool("b"), self._make_tool("c")]
        result = resolve_tools_for_subagent(
            allowed_tools=[], blocked_tools=["b"], all_tools=tools, policy_of=lambda _n: "read"
        )
        assert len(result) == 2

    def test_blocked_takes_priority(self):
        """Blocked tools override allowed tools."""
        tools = [self._make_tool("search_emails_tool")]
        result = resolve_tools_for_subagent(
            allowed_tools=["search_emails_tool"],
            blocked_tools=["search_emails_tool"],
            all_tools=tools,
            policy_of=lambda _n: "read",
        )
        assert len(result) == 0


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
