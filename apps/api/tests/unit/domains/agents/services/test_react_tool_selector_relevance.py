"""The ReAct loop binds tools by RELEVANCE, never by registration order.

Measured on a dev instance (2026-09-17): on an account with more tools than
the cap, every ReAct turn was capped and the tools cut were the SAME ones on
every turn, whatever the question — every family registered late, the user's
own MCP tools among them — because the cap sliced the registration order
after the detected domains' tools. A cap that cuts by position is a blind
spot, not a selection.

The composition is tool-based, with no tool name written anywhere: the
detected domains' tools first; then every OTHER family keeps its best-ranked
tools (the catalogue's own domain-coverage rule, one shared constant) so a
family the router did not name stays reachable; then the first K of the
turn's global ranking; the cap remains the safety net. Without a ranking, or
with K = 0, every available tool is bound in registration order — the
behaviour before this change — and the cap trims priority-last.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from src.core.config import settings
from src.core.constants import (
    CATALOGUE_DOMAIN_COVERAGE_TOP_N,
    MCP_ITERATIVE_TASK_SUFFIX,
    MCP_USER_TOOL_NAME_PREFIX,
)
from src.core.context import request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.infrastructure.mcp.user_context import UserMCPToolsContext

pytestmark = pytest.mark.unit

#: (manifest name, family) in REGISTRATION order — three families of three, one of one.
CATALOGUE: list[tuple[str, str]] = [
    ("calendar_get", "event_agent"),
    ("calendar_search", "event_agent"),
    ("calendar_list", "event_agent"),
    ("email_get", "email_agent"),
    ("email_search", "email_agent"),
    ("email_detail", "email_agent"),
    ("web_a", "web_agent"),
    ("web_b", "web_agent"),
    ("web_c", "web_agent"),
    ("docs_search", "document_agent"),
]
#: The turn's global order, most relevant first.
RANKING = [
    "web_c",
    "email_search",
    "web_a",
    "email_get",
    "docs_search",
    "email_detail",
    "web_b",
    "calendar_search",
]


class _Tool(BaseTool):
    """A native-shaped tool: its instance name IS its manifest name."""

    name: str
    description: str = "a tool"

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return ""


class _Harness:
    def __init__(self) -> None:
        self.manifests = [
            SimpleNamespace(
                name=name, agent=agent, permissions=SimpleNamespace(hitl_required=False)
            )
            for name, agent in CATALOGUE
        ]
        self.ctx = UserMCPToolsContext()
        for name, _agent in CATALOGUE:
            self.ctx.tool_instances[name] = _Tool(name=name)
        self.ctx.tool_manifests = self.manifests

    def select(
        self, *, domains: list[str] | None, ranking: list[str] | None
    ) -> tuple[list[str], dict[str, bool]]:
        man_token = request_tool_manifests_ctx.set(self.manifests)
        ctx_token = user_mcp_tools_ctx.set(self.ctx)
        try:
            intelligence = SimpleNamespace(domains=domains) if domains is not None else None
            wrapped, hitl_map = ReactToolSelector().select(intelligence, ranking=ranking)
        finally:
            user_mcp_tools_ctx.reset(ctx_token)
            request_tool_manifests_ctx.reset(man_token)
        return [t.name for t in wrapped], hitl_map


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> _Harness:
    monkeypatch.setattr(settings, "react_agent_max_tools", 100)
    monkeypatch.setattr(settings, "react_tool_semantic_top_k", 6)
    return _Harness()


class TestRelevanceComposition:
    def test_priority_then_family_coverage_then_the_semantic_top_k(self, harness: _Harness) -> None:
        assert CATALOGUE_DOMAIN_COVERAGE_TOP_N == 2, "the composition below is written for two"
        bound, hitl_map = harness.select(domains=["event"], ranking=RANKING)

        assert bound == [
            "calendar_get",  # the detected domain's tools, registration order
            "calendar_search",
            "calendar_list",
            "web_c",  # the two best-ranked of every other family, by rank
            "email_search",
            "web_a",
            "email_get",
            "docs_search",
            "email_detail",  # the semantic top-6 adds what coverage left out
        ]
        assert set(hitl_map) == set(bound)

    def test_beyond_the_top_k_a_tool_is_dropped_by_relevance(self, harness: _Harness) -> None:
        bound, _ = harness.select(domains=["event"], ranking=RANKING)
        assert "web_b" not in bound  # ranked 7th, third of its family

    def test_a_family_the_ranking_does_not_know_stays_reachable(self, harness: _Harness) -> None:
        """Coverage is by family, never by score alone: an unranked family keeps its first tools."""
        bound, _ = harness.select(domains=["event"], ranking=["web_c"])
        assert "email_get" in bound and "email_search" in bound and "docs_search" in bound

    def test_the_cap_still_applies_after_relevance(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_agent_max_tools", 5)
        bound, hitl_map = harness.select(domains=["event"], ranking=RANKING)

        assert bound == [
            "calendar_get",
            "calendar_search",
            "calendar_list",
            "web_c",
            "email_search",
        ]
        assert set(hitl_map) == set(bound)

    def test_no_intelligence_binds_coverage_and_the_top_k(self, harness: _Harness) -> None:
        bound, _ = harness.select(domains=None, ranking=RANKING)
        assert bound[:2] == ["web_c", "email_search"]
        assert "web_b" not in bound


class TestNothingRegresses:
    def test_no_ranking_means_the_previous_behaviour(self, harness: _Harness) -> None:
        bound, _ = harness.select(domains=["event"], ranking=None)
        assert bound == [name for name, _agent in CATALOGUE]

    def test_k_zero_switches_relevance_off(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 0)
        bound, _ = harness.select(domains=["event"], ranking=RANKING)
        assert bound == [name for name, _agent in CATALOGUE]

    def test_without_a_ranking_the_cap_keeps_every_family_reachable(
        self, harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Priority first, then two per family in registration order, then the rest."""
        monkeypatch.setattr(settings, "react_agent_max_tools", 6)
        bound, _ = harness.select(domains=["event"], ranking=None)
        assert bound == [
            "calendar_get",
            "calendar_search",
            "calendar_list",
            "email_get",
            "email_search",
            "web_a",
        ]


# ---------------------------------------------------------------------------
# An expanded iterative MCP server: its tools rank on their own, its door stays
# ---------------------------------------------------------------------------

_SERVER = f"{MCP_USER_TOOL_NAME_PREFIX}_srv1"
_DOOR = f"{_SERVER}{MCP_ITERATIVE_TASK_SUFFIX}"
_INDIVIDUAL = [f"{_SERVER}_a", f"{_SERVER}_b", f"{_SERVER}_c"]


@pytest.fixture
def mcp_harness(harness: _Harness, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    """The catalogue plus one iterative server: a task manifest, three hidden tools."""
    monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", True)
    harness.manifests.append(
        SimpleNamespace(
            name=_DOOR, agent="mcp_srv1_agent", permissions=SimpleNamespace(hitl_required=False)
        )
    )
    for name in (_DOOR, *_INDIVIDUAL):
        harness.ctx.tool_instances[name] = _Tool(name=name)
    return harness


class TestExpandedServer:
    def test_its_tools_are_bound_by_their_own_rank_and_the_door_rides_along(
        self, mcp_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The task tool is the one delegation affordance the individual tools
        cannot express (measured 2026-09-02): relevance never drops it while
        its server is bound, and it takes no coverage seat from the tools."""
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 3)
        ranking = [f"{_SERVER}_b", f"{_SERVER}_a", "web_c", "email_search", f"{_SERVER}_c"]
        bound, hitl_map = mcp_harness.select(domains=["event"], ranking=ranking)
        assert f"{_SERVER}_b" in bound and f"{_SERVER}_a" in bound
        assert _DOOR in bound
        assert f"{_SERVER}_c" not in bound  # ranked 5th, beyond K and the two seats
        assert set(hitl_map) == set(bound)

    def test_without_a_ranking_the_whole_server_is_bound(self, mcp_harness: _Harness) -> None:
        bound, _ = mcp_harness.select(domains=["event"], ranking=None)
        assert set(bound) >= {_DOOR, *_INDIVIDUAL}

    def test_under_the_cap_the_door_survives_with_its_family(
        self, mcp_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The door ranks as the best tool behind it: the cap trims the unranked
        coverage of OTHER families before it, never the door of a relevant server."""
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 3)
        monkeypatch.setattr(settings, "react_agent_max_tools", 9)
        ranking = [f"{_SERVER}_b", f"{_SERVER}_a", "web_c", "email_search", f"{_SERVER}_c"]
        bound, hitl_map = mcp_harness.select(domains=["event"], ranking=ranking)
        assert len(bound) == 9
        assert _DOOR in bound and f"{_SERVER}_b" in bound and f"{_SERVER}_a" in bound
        assert "web_a" not in bound  # unranked coverage of another family went first
        assert set(hitl_map) == set(bound)


# ---------------------------------------------------------------------------
# A binding unit is bound whole or not at all (2026-09-20)
# ---------------------------------------------------------------------------
#
# Replayed on dev (`task react:selection:measure`): for « montre moi où je suis »
# the ranking placed activate_skill_tool and dropped run_skill_script — the loop
# activated the skill and could not run its script, and answered in prose (the
# production motif on both skills, 2026-09-20). A skill's tools are ONE
# affordance: each alone is a dead end (ADR-249's rule on a tool nobody can
# run). The manifests declare it (`binding_unit`), the selector reads it.

_UNIT = [
    ("skill_activate", "query_agent"),
    ("skill_run", "query_agent"),
    ("skill_read", "query_agent"),
]


@pytest.fixture
def unit_harness(harness: _Harness) -> _Harness:
    """The catalogue plus a family holding a three-tool unit and one loose tool."""
    for name, agent in [*_UNIT, ("query_state", "query_agent")]:
        harness.manifests.append(
            SimpleNamespace(
                name=name,
                agent=agent,
                permissions=SimpleNamespace(hitl_required=False),
                binding_unit="skills" if name != "query_state" else None,
            )
        )
        harness.ctx.tool_instances[name] = _Tool(name=name)
    return harness


class TestBindingUnit:
    def test_one_ranked_member_binds_the_whole_unit_on_one_coverage_seat(
        self, unit_harness: _Harness
    ) -> None:
        # Only the activation ranks; the run and the read are unranked. The
        # unit takes its best member's rank and ONE seat, so the loose tool of
        # the same family keeps the family's second seat.
        ranking = ["skill_activate", *RANKING, "query_state"]
        bound, hitl_map = unit_harness.select(domains=["event"], ranking=ranking)
        assert {"skill_activate", "skill_run", "skill_read"} <= set(bound)
        assert "query_state" in bound
        assert set(hitl_map) == set(bound)

    def test_a_unit_no_member_of_which_is_reached_is_dropped_whole(
        self, unit_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The loose tool outranks the unit and the family has one seat: the
        # unit is not half bound behind it.
        monkeypatch.setattr(
            "src.domains.agents.services.react_tool_selector.CATALOGUE_DOMAIN_COVERAGE_TOP_N", 1
        )
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 2)
        ranking = ["query_state", "web_c", "skill_activate", *RANKING]
        bound, _ = unit_harness.select(domains=["event"], ranking=ranking)
        assert "query_state" in bound
        assert not {"skill_activate", "skill_run", "skill_read"} & set(bound)

    def test_the_unit_rides_the_semantic_tail_whole(
        self, unit_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two seats go to the loose tool and… the unit (one seat); with a
        # third family member the tail is where a unit member lands, whole.
        monkeypatch.setattr(
            "src.domains.agents.services.react_tool_selector.CATALOGUE_DOMAIN_COVERAGE_TOP_N", 1
        )
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 3)
        ranking = ["query_state", "web_c", "skill_run", *RANKING]
        bound, _ = unit_harness.select(domains=["event"], ranking=ranking)
        assert {"skill_activate", "skill_run", "skill_read"} <= set(bound)

    def test_the_cap_never_cuts_inside_a_unit(
        self, unit_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The cap falls on the unit's second member: the whole unit goes, the
        # cap holds, and nothing else moves.
        ranking = ["skill_activate", *RANKING, "query_state"]
        bound_free, _ = unit_harness.select(domains=["event"], ranking=ranking)
        first_member = min(
            bound_free.index(n) for n in ("skill_activate", "skill_run", "skill_read")
        )
        monkeypatch.setattr(settings, "react_agent_max_tools", first_member + 2)
        bound, hitl_map = unit_harness.select(domains=["event"], ranking=ranking)
        assert len(bound) == first_member
        assert not {"skill_activate", "skill_run", "skill_read"} & set(bound)
        assert bound == bound_free[:first_member]
        assert set(hitl_map) == set(bound)

    def test_without_a_ranking_the_unit_is_bound_like_everything_else(
        self, unit_harness: _Harness
    ) -> None:
        bound, _ = unit_harness.select(domains=["event"], ranking=None)
        assert {"skill_activate", "skill_run", "skill_read"} <= set(bound)
