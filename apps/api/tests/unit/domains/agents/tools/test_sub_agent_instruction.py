"""What a sub-agent is told it can do, and the cap on what it is handed (point 38).

The planner reads the delegation tool's manifest; the ReAct loop binds its
``@tool`` schema and never the manifest. The schema told the loop that the
expert « fetches what it needs » while its tools were public research only,
and the cap on the instruction was checked by the PIPELINE executor alone — a
ReAct delegation could hand the expert any amount of text.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.sub_agents.catalogue_manifests import (
    delegate_to_sub_agent_catalogue_manifest,
)
from src.domains.agents.tools.react_runner import ReactSubAgentResult
from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool
from src.domains.sub_agents.instruction_contract import expert_reach

pytestmark = pytest.mark.unit

_MODULE = "src.domains.agents.tools.sub_agent_tools"


def _schema_description() -> str:
    """The description the model is shown: the call schema, injected arguments aside."""
    schema = delegate_to_sub_agent_tool.tool_call_schema.model_json_schema()
    return str(schema["properties"]["instruction"]["description"])


def _manifest_description() -> str:
    (parameter,) = [
        p for p in delegate_to_sub_agent_catalogue_manifest.parameters if p.name == "instruction"
    ]
    return parameter.description


class TestBothModesStateTheSameFacts:
    def test_the_loop_and_the_planner_are_told_the_same_reach(self) -> None:
        assert expert_reach() in _schema_description()
        assert expert_reach() in _manifest_description()

    def test_the_loop_is_told_the_expert_s_tools_and_the_enforced_cap(self) -> None:
        """The loop has no delegation section: the schema is where it reads both."""
        description = _schema_description()

        for tool in settings.subagent_research_tools_whitelist_parsed:
            assert tool in description
        assert str(settings.subagent_instruction_max_tokens_resolved) in description
        assert "fetches what it needs" not in description
        assert "$steps" not in description  # a loop has no steps to reference


class TestTheReachIsClaimedOnlyWhereItHolds:
    """ADR-284: the whitelist is an operator's setting. « It cannot read the
    user's data » holds for the research tools LIA ships; a whitelist naming
    another tool is stated as it is, never with that claim."""

    def test_the_shipped_research_tools_carry_the_claim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "subagent_research_tools_whitelist", "brave_search_tool")

        assert "cannot read the user's data" in expert_reach()

    def test_another_tool_is_listed_without_the_claim(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            settings, "subagent_research_tools_whitelist", "brave_search_tool,get_emails_tool"
        )

        reach = expert_reach()

        assert "brave_search_tool" in reach and "get_emails_tool" in reach
        assert "it cannot read the user's data" not in reach


@pytest.fixture
def runner() -> Iterator[MagicMock]:
    """The tool with everything around the cap replaced: the runner is a spy."""
    fake_runner = MagicMock()
    fake_runner.run = AsyncMock(
        return_value=ReactSubAgentResult(
            final_message="analysis", messages=[], duration_ms=1, iteration_count=1
        )
    )
    config = SimpleNamespace(session_id="thread-1", user_id=str(uuid4()))
    with (
        patch(f"{_MODULE}.validate_runtime_config", return_value=config),
        patch(
            "src.domains.feature_switches.registry.is_capability_enabled",
            AsyncMock(return_value=True),
        ),
        patch(f"{_MODULE}.get_all_tools", return_value={}),
        patch(f"{_MODULE}.ReactSubAgentRunner", return_value=fake_runner),
    ):
        yield fake_runner


async def _delegate(instruction: str) -> Any:
    return await delegate_to_sub_agent_tool.coroutine(
        expertise="tax adviser", instruction=instruction, runtime=None
    )


class TestTheToolEnforcesItsOwnCap:
    async def test_an_oversized_instruction_is_refused_before_any_model_runs(
        self, runner: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "subagent_instruction_max_tokens_resolved", 50)

        output = await _delegate("figure " * 2_000)

        assert output.success is False
        assert output.error_code == "INVALID_INPUT"
        assert "50" in output.message
        runner.run.assert_not_awaited()

    async def test_an_instruction_under_the_cap_runs(self, runner: MagicMock) -> None:
        output = await _delegate("Review these three figures: 12, 15, 9.")

        assert output.success is True
        assert runner.run.await_args.kwargs["task"] == "Review these three figures: 12, 15, 9."
