"""A chart axis is a bounded vocabulary, or it is a leak (ADR-263).

Measured on the developer instance, 2026-09-05: ``token_usage_logs.node_name``
holds 102 distinct values over 53 934 rows, and two of its families are not
ours to publish —

- ``sub-agent: Consultant expert en communication écrit`` (24 values): the
  title a USER gave their own sub-agent. On the administrator's cross-account
  chart that puts one account's private naming in front of an operator.
- ``MCP Iterative: GITHUB REPOS``: a third-party server's own name, whose value
  set belongs to nobody — the very reason the effect metrics refuse
  ``tool_name`` as a Prometheus label.

The remaining 78 are graph nodes this repository chose, and they are what the
chart is about. So both families collapse to one word, exactly as MCP tools
collapse to ``mcp`` in the consultation register.
"""

from __future__ import annotations

import pytest

from src.domains.agents.effects.statistics_labels import (
    UNSPECIFIED,
    collapse_node_name,
    collapse_slot,
)

pytestmark = [pytest.mark.unit]


class TestWhatSomebodyElseWroteIsCOLLAPSED:
    @pytest.mark.parametrize(
        "written",
        [
            "sub-agent: Consultant expert en communication écrit",
            "sub-agent: assistant de tri et synthese d'emails (specialiste)",
            "sub-agent: ",
        ],
    )
    def test_a_users_own_sub_agent_title_never_becomes_a_label(self, written: str) -> None:
        assert collapse_node_name(written) == "sub-agent"

    @pytest.mark.parametrize(
        "written",
        [
            "MCP Iterative: GITHUB REPOS",
            "MCP Iterative: excalidraw",
            "MCP Iterative: ai.aarna/atars-mcp",
        ],
    )
    def test_a_third_party_server_name_never_becomes_a_label(self, written: str) -> None:
        """Its value set belongs to nobody — the rule the effect metrics
        already live by."""
        assert collapse_node_name(written) == "mcp"

    def test_the_collapsed_label_carries_none_of_the_original(self) -> None:
        secret = "sub-agent: Rapport confidentiel Marie Dupont"

        assert "Marie" not in collapse_node_name(secret)
        assert "Dupont" not in collapse_node_name(secret)


class TestWhatWeCHOSEIsKept:
    @pytest.mark.parametrize(
        "node",
        [
            "planner",
            "response",
            "query_analyzer",
            "memory_extraction",
            "semantic_validator",
            "interest_llm_reflection",
        ],
    )
    def test_a_graph_node_keeps_its_own_name(self, node: str) -> None:
        """78 of the 102 values are ours, and they are what the chart is for."""
        assert collapse_node_name(node) == node


class TestAnAbsentValueIsNAMEDRatherThanDropped:
    @pytest.mark.parametrize("empty", [None, ""])
    def test_a_node_with_no_name_is_counted_under_one_label(self, empty: str | None) -> None:
        assert collapse_node_name(empty) == UNSPECIFIED

    @pytest.mark.parametrize("empty", [None, ""])
    def test_a_call_with_no_slot_is_counted_too(self, empty: str | None) -> None:
        """Rows written before ADR-244 carry no slot, and they are the majority
        of any long history. Dropping them would understate the very period the
        chart claims to describe."""
        assert collapse_slot(empty) == UNSPECIFIED

    def test_a_slot_that_exists_is_kept(self) -> None:
        assert collapse_slot("response") == "response"


class TestATooolNameOnAnAxisIsBoundedToo:
    """The latency chart drew RAW tool names, and MCP tool names are not ours.

    ``treatment_domain`` already refuses to read meaning into a third-party
    server's vocabulary; the chart that groups by tool must obey the same rule,
    or an operator's cross-account screen shows one account's installed servers.
    """

    def test_a_native_tool_keeps_its_own_name(self) -> None:
        from src.domains.agents.effects.statistics_labels import collapse_tool_name

        assert collapse_tool_name("get_emails_tool") == "get_emails_tool"

    def test_a_third_party_mcp_tool_collapses_to_one_word(self) -> None:
        from src.domains.agents.effects.statistics_labels import collapse_tool_name
        from src.domains.agents.registry.catalogue import MCP_TOOL_NAME_PREFIX

        assert collapse_tool_name(f"{MCP_TOOL_NAME_PREFIX}_github_list_repos") == "mcp"

    def test_a_draft_executor_keeps_its_family(self) -> None:
        from src.domains.agents.effects.statistics_labels import collapse_tool_name

        assert collapse_tool_name("draft:email_send") == "draft:email_send"

    def test_nothing_stored_is_named_rather_than_dropped(self) -> None:
        from src.domains.agents.effects.statistics_labels import UNSPECIFIED, collapse_tool_name

        assert collapse_tool_name(None) == UNSPECIFIED
        assert collapse_tool_name("") == UNSPECIFIED
