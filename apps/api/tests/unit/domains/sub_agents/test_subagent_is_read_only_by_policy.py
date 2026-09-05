"""A sub-agent's read-only guarantee is structural, not a list (ADR-263).

Measured 2026-09-03: the sub-agent is documented READ-ONLY, and the only thing
enforcing it was a hand-written blocklist of 17 names. Four mutating tools were
not on it — the three Hue tools, the browser agent, the scheduled-action toggle
and ``delete_task_tool`` — and the ``.env`` whitelist that can widen the toolset
is validated for FORMAT only (snake_case), never for what the tools do.

The declared policy answers exactly that question, so the filter now reads it:
a tool that is not ``read`` cannot reach a sub-agent, whoever edits which list.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domains.sub_agents.constants import SUBAGENT_DEFAULT_BLOCKED_TOOLS
from src.domains.sub_agents.skill_resolver import resolve_tools_for_subagent

pytestmark = [pytest.mark.unit]


def _tools(*names: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(name=name) for name in names]


def _policies(mapping: dict[str, str | None]):
    """The injected policy reader — the resolver takes it as a parameter."""
    return lambda name: mapping.get(name)


class TestOnlyReadingToolsReachASubAgent:
    def test_a_mutating_tool_is_filtered_even_when_whitelisted(self) -> None:
        """The measured hole: the whitelist is checked for shape, not for effect."""
        names = ("brave_search_tool", "control_hue_light_tool", "browser_task_tool")
        kept = resolve_tools_for_subagent(
            allowed_tools=list(names),
            blocked_tools=[],
            all_tools=_tools(*names),
            policy_of=_policies(
                {
                    "brave_search_tool": "read",
                    "control_hue_light_tool": "reversible",
                    "browser_task_tool": "reversible",
                }
            ),
        )
        assert [t.name for t in kept] == ["brave_search_tool"]

    def test_a_draft_producing_tool_is_filtered_too(self) -> None:
        """A draft would never be confirmed: the sub-agent runs on its own thread."""
        kept = resolve_tools_for_subagent(
            allowed_tools=[],
            blocked_tools=[],
            all_tools=_tools("send_email_tool", "brave_search_tool"),
            policy_of=_policies({"send_email_tool": "draft", "brave_search_tool": "read"}),
        )
        assert [t.name for t in kept] == ["brave_search_tool"]

    def test_a_tool_with_no_declared_policy_is_filtered(self) -> None:
        """Doubt closes: an undeclared tool is not proven harmless."""
        kept = resolve_tools_for_subagent(
            allowed_tools=[],
            blocked_tools=[],
            all_tools=_tools("mystery_tool", "brave_search_tool"),
            policy_of=_policies({"mystery_tool": None, "brave_search_tool": "read"}),
        )
        assert [t.name for t in kept] == ["brave_search_tool"]

    def test_the_default_research_toolset_survives(self) -> None:
        """No capability regression: the three research tools all read."""
        names = ("perplexity_search_tool", "brave_search_tool", "fetch_web_page_tool")
        kept = resolve_tools_for_subagent(
            allowed_tools=list(names),
            blocked_tools=SUBAGENT_DEFAULT_BLOCKED_TOOLS,
            all_tools=_tools(*names),
            policy_of=_policies(dict.fromkeys(names, "read")),
        )
        assert sorted(t.name for t in kept) == sorted(names)


class TestTheOlderProtectionsStillApply:
    def test_the_blocklist_still_blocks(self) -> None:
        kept = resolve_tools_for_subagent(
            allowed_tools=[],
            blocked_tools=["brave_search_tool"],
            all_tools=_tools("brave_search_tool"),
            policy_of=_policies({"brave_search_tool": "read"}),
        )
        assert kept == []

    def test_recursion_is_still_impossible(self) -> None:
        """A sub-agent that could spawn a sub-agent is a loop, whatever it reads."""
        kept = resolve_tools_for_subagent(
            allowed_tools=[],
            blocked_tools=[],
            all_tools=_tools("delegate_to_sub_agent_tool", "brave_search_tool"),
            policy_of=_policies(
                {"delegate_to_sub_agent_tool": "read", "brave_search_tool": "read"}
            ),
        )
        assert [t.name for t in kept] == ["brave_search_tool"]
