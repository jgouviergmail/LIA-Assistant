"""A skill template keeps every step its turn can run — as the executor resolves it.

The bypass used to keep a template step only when its tool NAME was in the
turn's catalogue. The executor resolves a step through the canonical resolver
(``resolve_tool_manifest_named``), which also admits a hallucinated MCP suffix
and a reactive user-MCP tool its server's task offers: the narrowing filter was
stricter than the decider, so such a step was dropped in silence. The filter now
asks the resolver itself; these tests hold the two to the same verdict.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from typing import Literal

import pytest

from src.core.context import UserMCPToolsContext, request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.manifest_resolution import resolve_tool_manifest_named
from src.domains.agents.services.planner.strategies.skill_bypass import _steps_the_turn_offers
from src.domains.agents.sub_agents.catalogue_manifests import (
    delegate_to_sub_agent_catalogue_manifest,
)

pytestmark = pytest.mark.unit

_USER_SERVER = "00000001-0000-0000-0000-000000000001"


def _manifest(
    name: str,
    *,
    mcp_origin: Literal["admin", "user"] | None = None,
    mcp_server_key: str | None = None,
    delegates_execution: bool = False,
) -> ToolManifest:
    """A real manifest under another name, with the MCP identity a resolver reads."""
    return replace(
        delegate_to_sub_agent_catalogue_manifest,
        name=name,
        mcp_origin=mcp_origin,
        mcp_server_key=mcp_server_key,
        delegates_execution=delegates_execution,
    )


@contextmanager
def _turn(
    offered: Sequence[ToolManifest], user_mcp: UserMCPToolsContext | None = None
) -> Iterator[None]:
    """Publish the turn's catalogue (and the person's MCP context), as the request does."""
    manifests_token = request_tool_manifests_ctx.set(list(offered))
    mcp_token = user_mcp_tools_ctx.set(user_mcp)
    try:
        yield
    finally:
        user_mcp_tools_ctx.reset(mcp_token)
        request_tool_manifests_ctx.reset(manifests_token)


def _kept(tool_name: str) -> bool:
    """Whether a one-step template naming ``tool_name`` keeps its step this turn."""
    steps = [{"step_id": "s1", "tool_name": tool_name}]
    return _steps_the_turn_offers(steps) == steps


def _resolved(tool_name: str) -> bool:
    """Whether the executor's resolver finds ``tool_name`` this turn."""
    return resolve_tool_manifest_named(tool_name)[0] is not None


class TestTheFilterAgreesWithTheResolver:
    def test_a_hallucinated_mcp_suffix_is_kept(self) -> None:
        offered = [
            _manifest("mcp_atlas_search", mcp_origin="admin", mcp_server_key="Atlas Catalogue")
        ]
        with _turn(offered):
            assert _resolved("mcp_atlas_search_tool")
            assert _kept("mcp_atlas_search_tool")

    def test_a_reactive_user_mcp_tool_its_server_offers_is_kept(self) -> None:
        task = _manifest(
            "mcp_canvas_task",
            delegates_execution=True,
            mcp_origin="user",
            mcp_server_key=_USER_SERVER,
        )
        individual = _manifest("mcp_canvas_draw", mcp_origin="user", mcp_server_key=_USER_SERVER)
        user_mcp = UserMCPToolsContext(reactive_tool_manifests={individual.name: individual})
        with _turn([task], user_mcp):
            assert _resolved("mcp_canvas_draw")
            assert _kept("mcp_canvas_draw")

    def test_an_ambiguous_name_is_dropped_as_the_executor_refuses_it(self) -> None:
        offered = [
            _manifest("mcp_twin_search", mcp_origin="admin", mcp_server_key="Twin A"),
            _manifest("mcp_twin_search", mcp_origin="admin", mcp_server_key="Twin B"),
        ]
        with _turn(offered):
            assert not _resolved("mcp_twin_search")
            assert not _kept("mcp_twin_search")

    def test_a_tool_the_turn_withholds_is_dropped(self) -> None:
        with _turn([_manifest("get_event_tool")]):
            assert not _resolved("run_python_tool")
            assert not _kept("run_python_tool")
            assert _kept("get_event_tool")
