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
from uuid import UUID

import pytest
from langchain_core.tools import BaseTool

from src.core.config import settings
from src.core.constants import (
    CATALOGUE_DOMAIN_COVERAGE_TOP_N,
    MCP_ITERATIVE_TASK_SUFFIX,
    MCP_USER_TOOL_NAME_PREFIX,
)
from src.core.context import request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.registry.catalogue import CostProfile, PermissionProfile, ToolManifest
from src.domains.agents.services.react_tool_selector import ReactToolSelector
from src.infrastructure.mcp.registration import (
    build_mcp_react_task_manifest,
    build_mcp_tool_manifest,
)
from src.infrastructure.mcp.user_context import UserMCPToolsContext
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.unit.domains.agents.services.test_react_tool_selector import _task_instance

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


def _native_manifest(name: str, agent: str, *, binding_unit: str | None = None) -> ToolManifest:
    return ToolManifest(
        name=name,
        agent=agent,
        description="Native-shaped selector fixture",
        parameters=[],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(hitl_required=False),
        binding_unit=binding_unit,
    )


class _Harness:
    def __init__(self) -> None:
        self.manifests = [_native_manifest(name, agent) for name, agent in CATALOGUE]
        self.ctx = UserMCPToolsContext()
        for name, _agent in CATALOGUE:
            self.ctx.tool_instances[name] = _Tool(name=name)
        self.ctx.tool_manifests = self.manifests

    def select(
        self, *, domains: list[str] | None, ranking: list[str] | None, every_tool: bool = False
    ) -> tuple[list[str], dict[str, bool]]:
        man_token = request_tool_manifests_ctx.set(self.manifests)
        ctx_token = user_mcp_tools_ctx.set(self.ctx)
        try:
            intelligence = SimpleNamespace(domains=domains) if domains is not None else None
            wrapped, hitl_map = ReactToolSelector().select(
                intelligence, ranking=ranking, every_tool=every_tool
            )
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

_SERVER_ID = UUID("12345678-2222-3333-4444-555555555555")
_SERVER = f"{MCP_USER_TOOL_NAME_PREFIX}_{str(_SERVER_ID)[:8]}"
_DOOR = f"{_SERVER}{MCP_ITERATIVE_TASK_SUFFIX}"
_INDIVIDUAL = [f"{_SERVER}_a", f"{_SERVER}_b", f"{_SERVER}_c"]


def _add_iterative_server(harness: _Harness) -> None:
    """Publish an owned task and real per-server adapters in registration order."""
    harness.manifests.append(
        build_mcp_react_task_manifest(
            _DOOR,
            "mcp_srv1_agent",
            "Selector server",
            "Selector fixture delegation",
            [],
            [],
            mcp_origin="user",
            mcp_server_key=str(_SERVER_ID),
        )
    )
    harness.ctx.tool_instances[_DOOR] = _task_instance(
        name=_DOOR, server_id=_SERVER_ID, server_name="Selector server"
    )
    for rpc, name in zip(("a", "b", "c"), _INDIVIDUAL, strict=True):
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=_SERVER_ID,
            user_id=UUID(int=1),
            server_name="Selector server",
            tool_name=rpc,
            description="Selector fixture individual",
            input_schema={"type": "object", "properties": {}},
        )
        assert adapter.name == name
        harness.ctx.tool_instances[name] = adapter
        harness.ctx.reactive_tool_manifests[name] = build_mcp_tool_manifest(
            name,
            "mcp_srv1_agent",
            rpc,
            adapter.description,
            {"type": "object", "properties": {}},
            [],
            False,
            mcp_origin="user",
            mcp_server_key=str(_SERVER_ID),
        )


@pytest.fixture
def mcp_harness(harness: _Harness, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    """The catalogue plus one iterative server: a task manifest, three hidden tools."""
    monkeypatch.setattr(settings, "react_mcp_expand_iterative_enabled", True)
    _add_iterative_server(harness)
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
            _native_manifest(
                name,
                agent,
                binding_unit="skills" if name != "query_state" else None,
            )
        )
        harness.ctx.tool_instances[name] = _Tool(name=name)
    return harness


class TestBindingUnit:
    def test_one_ranked_member_binds_the_whole_unit_as_the_family_s_coverage(
        self, unit_harness: _Harness
    ) -> None:
        # Only the activation ranks; the run and the read are unranked. The
        # unit takes its best member's rank and is the family's first seat,
        # so it is bound whole; the family holds one unit, so a seat is a seat
        # (the 2026-09-20 rule): the loose tool is the second one, even
        # unranked, like any family's second-best tool.
        ranking = ["skill_activate", *RANKING, "query_state"]
        bound, hitl_map = unit_harness.select(domains=["event"], ranking=ranking)
        assert {"skill_activate", "skill_run", "skill_read", "query_state"} <= set(bound)
        assert set(hitl_map) == set(bound)

    def test_in_a_family_of_one_unit_the_unit_is_one_seat_whichever_ranks_first(
        self, unit_harness: _Harness
    ) -> None:
        # The loose tool outranks the unit and the family has two seats: the
        # unit is the second seat WHOLE, whatever its size — the measured rule
        # of 2026-09-20. Counting tools here would have dropped the skills
        # whenever a sibling outranked them (reviewed 2026-10-12).
        ranking = ["query_state", "skill_read", *RANKING]
        bound, hitl_map = unit_harness.select(domains=["event"], ranking=ranking)
        assert {"query_state", "skill_activate", "skill_run", "skill_read"} <= set(bound)
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

    def test_a_unit_never_rides_the_semantic_tail(
        self, unit_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The loose tool took the family's one seat; the unit's best member
        # ranks within K, and still the unit is NOT bound: a unit lands whole
        # through its family's priority or coverage, never on a rank of the
        # tail (2026-10-12 — forty settings sections rode the tail that way).
        monkeypatch.setattr(
            "src.domains.agents.services.react_tool_selector.CATALOGUE_DOMAIN_COVERAGE_TOP_N", 1
        )
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 3)
        ranking = ["query_state", "web_c", "skill_run", *RANKING]
        bound, _ = unit_harness.select(domains=["event"], ranking=ranking)
        assert not {"skill_activate", "skill_run", "skill_read"} & set(bound)

    def test_a_unit_binds_whole_through_its_detected_domain(
        self, unit_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The same ranking, the family's domain detected: the unit is priority,
        # bound whole beside the family's loose tool.
        monkeypatch.setattr(
            "src.domains.agents.services.react_tool_selector.CATALOGUE_DOMAIN_COVERAGE_TOP_N", 1
        )
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 3)
        ranking = ["query_state", "web_c", "skill_run", *RANKING]
        bound, hitl_map = unit_harness.select(domains=["query"], ranking=ranking)
        assert {"skill_activate", "skill_run", "skill_read", "query_state"} <= set(bound)
        assert set(hitl_map) == set(bound)

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


# ---------------------------------------------------------------------------
# A binding unit binds through its domain (2026-10-12)
# ---------------------------------------------------------------------------
#
# Measured on production: the settings catalogue declares 40 binding units
# holding 180 tools in ONE family (commit 499c4cecc). A unit took ONE coverage
# seat and ONE rank of the semantic tail whatever its size, so on a question
# about the agenda 71 settings tools were bound through 12 units — 45 % of the
# 156 tools and about 26K tokens of schemas on every model call — while the
# loop called one settings tool in 125 turns of 7 days; on dev, the family's
# best section (18 tools) rode the coverage seat on every turn and its other
# sections rode the tail. The owner's verdict: the settings tools were treated
# unlike every other family, and that is abnormal.
#
# The rule now: a unit never rides the tail; a family holding at most ONE
# unit keeps the 2026-09-20 rule (its unit is ONE seat among N, whatever its
# size — the skills); a family of SEVERAL units is a catalogue of sections
# whose coverage seats count TOOLS, reachable through its domain: when the
# router names it, its loose tools are all bound and its units by rank under
# K tools, the first whole; when it does not, no section wider than the count
# is bound. The walk stops at the first seat that does not fit (ADR-286's
# doctrine for the paging of a tool result).

_SECTIONS: list[tuple[str, str | None]] = [
    ("meet_get", "lia_meetings"),
    ("meet_update", "lia_meetings"),
    ("meet_delete", "lia_meetings"),
    ("meet_template", "lia_meetings"),
    ("peer_get", "lia_peers"),
    ("peer_request", "lia_peers"),
    ("peer_block", "lia_peers"),
    ("habit_get", "lia_habits"),
    ("habit_set", "lia_habits"),
    ("habit_delete", "lia_habits"),
    ("setting_loose", None),
    ("setting_loose_2", None),
]
_MEETINGS = {name for name, unit in _SECTIONS if unit == "lia_meetings"}
_PEERS = {name for name, unit in _SECTIONS if unit == "lia_peers"}
_HABITS = {name for name, unit in _SECTIONS if unit == "lia_habits"}
_UNIT_TOOLS = _MEETINGS | _PEERS | _HABITS


@pytest.fixture
def sections_harness(harness: _Harness) -> _Harness:
    """The catalogue plus a settings-shaped family: three units, two loose tools."""
    for name, unit in _SECTIONS:
        harness.manifests.append(_native_manifest(name, "setting_agent", binding_unit=unit))
        harness.ctx.tool_instances[name] = _Tool(name=name)
    return harness


class TestAUnitBindsThroughItsDomain:
    def test_a_family_of_several_units_takes_no_coverage_seat_through_a_unit(
        self, sections_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two seats per family. The best seat is a four-tool unit and the family
        # holds three units: no reachability exception — the first seat does not
        # fit, the walk stops, and nothing of the family is bound (before: the
        # whole first section, 18 tools on production, on every turn).
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 1)
        ranking = ["web_c", "meet_get", "peer_get", "habit_get", "setting_loose", *RANKING]
        bound, hitl_map = sections_harness.select(domains=["event"], ranking=ranking)
        assert not (_UNIT_TOOLS | {"setting_loose", "setting_loose_2"}) & set(bound)
        assert set(hitl_map) == set(bound)

    def test_the_loose_seats_of_such_a_family_still_take_its_coverage(
        self, sections_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Ranked ahead of the units, the family's two loose tools are its two
        # seats: the family stays reachable through tools that weigh one.
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 1)
        ranking = ["web_c", "setting_loose", "setting_loose_2", "meet_get", *RANKING]
        bound, _ = sections_harness.select(domains=["event"], ranking=ranking)
        assert {"setting_loose", "setting_loose_2"} <= set(bound)
        assert not _UNIT_TOOLS & set(bound)

    def test_the_family_coverage_stops_at_the_first_seat_that_does_not_fit(
        self, sections_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A loose tool, then a three-tool unit, then a loose tool that WOULD
        # fit: the unit does not fit beside the first and the walk stops there
        # — the second loose tool is never bound in place of the unit that
        # outranks it.
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 1)
        ranking = ["web_c", "setting_loose", "peer_get", "setting_loose_2", "meet_get", *RANKING]
        bound, _ = sections_harness.select(domains=["event"], ranking=ranking)
        assert "setting_loose" in bound
        assert "setting_loose_2" not in bound
        assert not _UNIT_TOOLS & set(bound)

    def test_a_unit_never_rides_the_tail(
        self, sections_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # K = 5: three units rank first, then a loose settings tool. The tail
        # binds the loose tool and none of the units, whatever their rank
        # (before: all three, seven tools on three ranks).
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 5)
        ranking = ["meet_get", "peer_get", "habit_get", "setting_loose", "web_c", *RANKING]
        bound, hitl_map = sections_harness.select(domains=["event"], ranking=ranking)
        assert "setting_loose" in bound
        assert not _UNIT_TOOLS & set(bound)
        assert set(hitl_map) == set(bound)

    def test_a_detected_family_binds_its_units_by_rank_under_k(
        self, sections_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The router named the settings domain: every loose tool of the family
        # is bound, and its units by rank under K = 7 tools — meetings (four,
        # the first, whole), peers (three, fits), habits (would make ten): stop.
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 7)
        ranking = ["meet_get", "peer_get", "habit_get", "web_c", *RANKING]
        bound, hitl_map = sections_harness.select(domains=["setting"], ranking=ranking)
        assert _MEETINGS | _PEERS | {"setting_loose", "setting_loose_2"} <= set(bound)
        assert not _HABITS & set(bound)
        assert set(hitl_map) == set(bound)

    def test_a_detected_family_s_first_unit_passes_whole(
        self, sections_harness: _Harness, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # K = 2 cannot hold the four-tool unit; the question IS about the
        # family, so its best section is bound whole all the same.
        monkeypatch.setattr(settings, "react_tool_semantic_top_k", 2)
        ranking = ["meet_get", "peer_get", "web_c", *RANKING]
        bound, _ = sections_harness.select(domains=["setting"], ranking=ranking)
        assert _MEETINGS <= set(bound)
        assert not _PEERS & set(bound)

    def test_without_a_ranking_a_detected_family_is_bound_whole(
        self, sections_harness: _Harness
    ) -> None:
        # Relevance off: the previous behaviour, every tool bound, the cap alone.
        bound, _ = sections_harness.select(domains=["setting"], ranking=None)
        assert _UNIT_TOOLS | {"setting_loose", "setting_loose_2"} <= set(bound)

    def test_the_selection_log_states_each_tier(self, sections_harness: _Harness) -> None:
        # What the loop binds is stated per tier, so a bound set can be read
        # back from the log — the rhythm and the volume used to be invisible.
        from structlog.testing import capture_logs

        ranking = ["meet_get", "peer_get", "web_c", *RANKING]
        with capture_logs() as logs:
            bound, _ = sections_harness.select(domains=["event"], ranking=ranking)
        relevance = next(log for log in logs if log["event"] == "react_tool_selector_relevance")
        complete = next(log for log in logs if log["event"] == "react_tool_selector_complete")
        assert relevance["priority_count"] == 3  # the event family, whole
        assert relevance["priority_count"] + relevance["coverage_count"] + relevance[
            "tail_count"
        ] == len(bound)
        assert relevance["unit_count"] == 0 and relevance["unit_tool_count"] == 0
        assert complete["every_tool_requested"] is False
