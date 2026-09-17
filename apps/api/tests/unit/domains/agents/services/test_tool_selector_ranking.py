"""``SemanticToolSelector.rank_tools`` — the GLOBAL relevance order of every tool.

The router scores only the detected domains' tools (the planner's catalogue is
built from those), so nothing ranked the others for the ReAct loop, whose cap
then cut in REGISTRATION order — on an account with more tools than the cap,
the same tools were invisible on every turn (measured on a dev instance,
2026-09-17). The ranking reuses the query embedding the router already paid
for, scores the per-request MCP tools through their pre-computed embeddings,
and never raises: an unscorable tool ranks last, in input order.

The embeddings are the orthonormal stubs of the selection suite, so every
cosine is an exact 1.0 or 0.0 and the assertions are about ORDER only.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.tool_selector import SemanticToolSelector
from tests.unit.domains.agents.services.test_tool_selector_selection import (
    AXES,
    build_selector,
    make_manifest,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def selector() -> SemanticToolSelector:
    return build_selector(
        tools={
            "search_emails_tool": "emails",
            "get_events_tool": "events",
            "get_contacts_tool": "contacts",
        },
    )


class TestRankTools:
    def test_the_matching_tool_ranks_first_and_the_rest_keep_their_order(
        self, selector: SemanticToolSelector
    ) -> None:
        manifests = [
            make_manifest("get_contacts_tool"),
            make_manifest("search_emails_tool"),
            make_manifest("get_events_tool"),
        ]
        ranked = selector.rank_tools(AXES["emails"], manifests)
        assert ranked == ["search_emails_tool", "get_contacts_tool", "get_events_tool"]

    def test_a_per_request_tool_is_scored_through_its_own_embeddings(
        self, selector: SemanticToolSelector
    ) -> None:
        """User MCP tools live outside the startup caches: their vectors travel per request."""
        manifests = [make_manifest("search_emails_tool"), make_manifest("mcp_user_ab_repo_search")]
        extra = {"mcp_user_ab_repo_search": {"description": None, "keywords": [AXES["files"]]}}
        ranked = selector.rank_tools(AXES["files"], manifests, extra_embeddings=extra)
        assert ranked[0] == "mcp_user_ab_repo_search"

    def test_a_per_request_vector_without_a_manifest_is_ranked_too(
        self, selector: SemanticToolSelector
    ) -> None:
        """An iterative user MCP server exposes ONE task manifest; its individual
        tools have vectors and no manifest of their own. They must rank, or the
        loop could never bind them by relevance — the very tools ADR-293 is for."""
        manifests = [make_manifest("search_emails_tool"), make_manifest("mcp_user_ab_task")]
        extra = {"mcp_user_ab_repo_search": {"description": None, "keywords": [AXES["files"]]}}
        ranked = selector.rank_tools(AXES["files"], manifests, extra_embeddings=extra)
        assert ranked[0] == "mcp_user_ab_repo_search"
        assert set(ranked) == {"search_emails_tool", "mcp_user_ab_task", "mcp_user_ab_repo_search"}

    def test_a_vector_that_is_also_a_manifest_ranks_once(
        self, selector: SemanticToolSelector
    ) -> None:
        manifests = [make_manifest("search_emails_tool"), make_manifest("mcp_user_ab_repo_search")]
        extra = {"mcp_user_ab_repo_search": {"description": None, "keywords": [AXES["files"]]}}
        ranked = selector.rank_tools(AXES["files"], manifests, extra_embeddings=extra)
        assert len(ranked) == 2

    def test_an_unscorable_tool_ranks_last_and_never_raises(
        self, selector: SemanticToolSelector
    ) -> None:
        manifests = [make_manifest("unknown_tool"), make_manifest("search_emails_tool")]
        assert selector.rank_tools(AXES["emails"], manifests) == [
            "search_emails_tool",
            "unknown_tool",
        ]

    def test_the_order_agrees_with_the_calibrated_scores(
        self, selector: SemanticToolSelector
    ) -> None:
        """Calibration is monotonic: the ranking and ``all_scores`` cannot disagree."""
        manifests = [
            make_manifest("get_contacts_tool"),
            make_manifest("search_emails_tool"),
            make_manifest("get_events_tool"),
        ]
        ranked = selector.rank_tools(AXES["emails"], manifests)
        assert ranked[0] == "search_emails_tool"


class TestEmbeddingReuse:
    async def test_embed_query_is_the_one_paid_call(self, selector: SemanticToolSelector) -> None:
        embedding = await selector.embed_query("emails")
        assert embedding == AXES["emails"]
        assert selector._embeddings.calls == ["emails"]  # type: ignore[union-attr]

    async def test_select_tools_reuses_a_given_embedding(
        self, selector: SemanticToolSelector
    ) -> None:
        result = await selector.select_tools("emails", query_embedding=AXES["emails"])
        assert result.tool_names[0] == "search_emails_tool"
        assert selector._embeddings.calls == []  # type: ignore[union-attr]
