"""Making is not playing, in the loop too (ADR-370).

Measured 2026-11-05 on real turns: routed to the page by the analyzer, the loop still
read the catalogue and ran the skill of a neighbouring game, six times out of six. With
no catalogue, it played the game in text on two turns out of six.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import INTERACTIVE_PAGE_TOOL_NAME
from src.domains.agents.nodes import react_context
from src.domains.agents.nodes import react_nodes as nodes

pytestmark = pytest.mark.unit

CATALOGUE = "<AvailableSkills>\ntic-tac-toe\n</AvailableSkills>"


@pytest.fixture(autouse=True)
def _only_the_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "build_memory_profile_block",
        "build_knowledge_block",
        "build_designated_items_block",
        "build_user_model_block",
        "build_journal_directives_block",
        "build_degradations_block",
        "build_mcp_auth_notices_block",
    ):
        monkeypatch.setattr(react_context, name, AsyncMock(return_value=None))
    monkeypatch.setattr(react_context, "build_reference_resolution_block", lambda *args: None)
    monkeypatch.setattr(react_context, "build_skills_catalog_block", lambda: CATALOGUE)


def _turn(domains: list[str]) -> dict[str, dict[str, list[str]]]:
    return {"query_intelligence": {"domains": domains}}


async def test_a_turn_making_a_page_shows_the_loop_no_skill() -> None:
    built = await react_context.build_setup_blocks(_turn(["interactive_page"]), {})

    assert built.skills_catalog == ""
    assert CATALOGUE not in built.blocks


@pytest.mark.parametrize(
    "domains",
    [[], ["event"], ["event", "interactive_page"], ["mcp_excalidraw"]],
)
async def test_every_other_turn_keeps_the_catalogue(domains: list[str]) -> None:
    built = await react_context.build_setup_blocks(_turn(domains), {})

    assert built.skills_catalog == CATALOGUE
    assert CATALOGUE in built.blocks


class TestThePageRequest:
    def test_a_page_turn_names_the_tool_to_call(self) -> None:
        block = react_context.build_page_request_block(
            _turn(["interactive_page"]), [INTERACTIVE_PAGE_TOOL_NAME]
        )

        assert block is not None
        assert INTERACTIVE_PAGE_TOOL_NAME in block

    def test_nothing_is_promised_when_the_tool_is_not_bound(self) -> None:
        assert (
            react_context.build_page_request_block(_turn(["interactive_page"]), ["other_tool"])
            is None
        )

    @pytest.mark.parametrize("domains", [[], ["event"], ["event", "interactive_page"]])
    def test_another_turn_hears_nothing_of_it(self, domains: list[str]) -> None:
        assert (
            react_context.build_page_request_block(_turn(domains), [INTERACTIVE_PAGE_TOOL_NAME])
            is None
        )

    @pytest.mark.parametrize(
        ("domains", "asked"), [(["interactive_page"], True), (["event"], False)]
    )
    async def test_the_setup_hands_it_to_the_loop(
        self, monkeypatch: pytest.MonkeyPatch, domains: list[str], asked: bool
    ) -> None:
        monkeypatch.setattr(nodes.settings, "react_agent_enabled", True, raising=False)
        tool = MagicMock()
        tool.name = INTERACTIVE_PAGE_TOOL_NAME
        selector = MagicMock()
        selector.select.return_value = ([tool], {})
        state: dict[str, Any] = {"messages": [], **_turn(domains)}
        with (
            patch.object(nodes, "ReactToolSelector", return_value=selector),
            patch.object(nodes, "build_bound_system_prompt", AsyncMock(return_value="P")),
            patch.object(nodes, "bound_tool_tokens", return_value=0),
            patch.object(nodes, "get_query_intelligence_from_state", return_value=MagicMock()),
        ):
            update = await nodes.react_setup_node(state, {"configurable": {}})

        assert any("<MakePage>" in block for block in update["react_system_blocks"]) is asked
