"""The router scores a turn's tools ONCE: the planner's domain scores, the global order.

Measured 2026-09-17: the router's semantic scores covered only the detected
domains' tools, so the ReAct loop — which binds many tools — had no relevance
order and cut its cap in registration order. The global ranking is computed
from the SAME query embedding (no second paid call), covers every available
manifest, and reads the user's MCP vectors even when no MCP domain was
detected; the planner's own scores are byte-for-byte what they were.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.core.context import request_tool_manifests_ctx, user_mcp_tools_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.nodes import router_tool_scoring as scoring
from src.domains.agents.nodes.router_tool_scoring import GLOBAL_RANKING_KEY, score_tools_for_turn
from src.domains.agents.services.tool_selector import ToolMatch, ToolSelectionResult
from src.infrastructure.mcp.user_context import UserMCPToolsContext

pytestmark = [pytest.mark.unit]


def _intelligence(**overrides: Any) -> QueryIntelligence:
    base: dict[str, Any] = {
        "original_query": "mes emails",
        "english_query": "my emails",
        "immediate_intent": "search",
        "immediate_confidence": 0.9,
        "user_goal": next(iter(UserGoal)),
        "goal_reasoning": "",
        "domains": ["email"],
        "primary_domain": "email",
        "route_to": "planner",
    }
    base.update(overrides)
    return QueryIntelligence(**base)


def _manifest(name: str, agent: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, agent=agent)


class _FakeSelector:
    """Records what it was asked; ranks by a fixed order."""

    def __init__(self, ranking: list[str]) -> None:
        self.ranking = ranking
        self.embed_calls: list[str] = []
        self.select_calls: list[dict[str, Any]] = []
        self.rank_calls: list[dict[str, Any]] = []
        self.initialized = True

    def is_initialized(self) -> bool:
        return self.initialized

    async def embed_query(self, query: str) -> list[float]:
        self.embed_calls.append(query)
        return [1.0, 0.0]

    def rank_tools(
        self, query_embedding: Any, manifests: Any, extra_embeddings: Any = None
    ) -> list[str]:
        self.rank_calls.append(
            {"manifests": [m.name for m in manifests], "extra": extra_embeddings}
        )
        return [n for n in self.ranking if n in {m.name for m in manifests}]

    async def select_tools(self, **kwargs: Any) -> ToolSelectionResult:
        self.select_calls.append(kwargs)
        names = [m.name for m in kwargs["available_tools"]]
        return ToolSelectionResult(
            selected_tools=[
                ToolMatch(
                    tool_name=names[0],
                    tool_manifest=kwargs["available_tools"][0],
                    score=0.9,
                    primary_min=0.07,
                )
            ],
            top_score=0.9,
            has_uncertainty=False,
            all_scores=dict.fromkeys(names, 0.5),
        )


@pytest.fixture
def manifests() -> list[SimpleNamespace]:
    return [
        _manifest("get_emails_tool", "email_agent"),
        _manifest("get_events_tool", "event_agent"),
        _manifest("mcp_user_ab_search", "mcp_user_ab_agent"),
    ]


@pytest.fixture
def selector(monkeypatch: pytest.MonkeyPatch) -> _FakeSelector:
    fake = _FakeSelector(["mcp_user_ab_search", "get_events_tool", "get_emails_tool"])

    async def _get() -> _FakeSelector:
        return fake

    monkeypatch.setattr("src.domains.agents.services.tool_selector.get_tool_selector", _get)
    return fake


@pytest.fixture(autouse=True)
def _request_ctx(manifests: list[SimpleNamespace]) -> Any:
    man_token = request_tool_manifests_ctx.set(manifests)
    ctx = UserMCPToolsContext()
    ctx.tool_embeddings["mcp_user_ab_search"] = {"description": [0.0, 1.0], "keywords": []}
    ctx_token = user_mcp_tools_ctx.set(ctx)
    yield
    user_mcp_tools_ctx.reset(ctx_token)
    request_tool_manifests_ctx.reset(man_token)


class TestOneEmbeddingTwoReaders:
    async def test_the_planner_scores_are_unchanged_and_the_global_order_is_added(
        self, selector: _FakeSelector
    ) -> None:
        scores = await score_tools_for_turn(_intelligence(), "run-1")

        assert scores is not None
        # The planner's view: the detected domain's tools only, as before.
        assert set(scores["all_scores"]) == {"get_emails_tool"}
        assert scores["selected_tools"][0]["tool_name"] == "get_emails_tool"
        assert scores["top_score"] == 0.9 and scores["has_uncertainty"] is False
        # The global order: every available manifest, MCP tools included.
        assert scores[GLOBAL_RANKING_KEY] == [
            "mcp_user_ab_search",
            "get_events_tool",
            "get_emails_tool",
        ]

    async def test_the_query_is_embedded_once_for_both(self, selector: _FakeSelector) -> None:
        await score_tools_for_turn(_intelligence(), "run-1")

        assert selector.embed_calls == ["my emails"]
        assert selector.select_calls[0]["query_embedding"] == [1.0, 0.0]

    async def test_mcp_vectors_reach_the_ranking_even_without_an_mcp_domain(
        self, selector: _FakeSelector
    ) -> None:
        await score_tools_for_turn(_intelligence(), "run-1")

        assert selector.rank_calls[0]["extra"] == {
            "mcp_user_ab_search": {"description": [0.0, 1.0], "keywords": []}
        }
        # ...while the planner's domain scores keep their old gate (no MCP domain → none).
        assert selector.select_calls[0]["extra_embeddings"] is None

    async def test_a_domain_with_no_tool_still_yields_the_global_order(
        self, selector: _FakeSelector
    ) -> None:
        scores = await score_tools_for_turn(_intelligence(domains=["weather"]), "run-1")

        assert scores is not None
        assert "all_scores" not in scores
        assert scores[GLOBAL_RANKING_KEY]
        assert selector.select_calls == []


class TestTheOldGatesStand:
    async def test_a_conversation_turn_is_not_scored(self, selector: _FakeSelector) -> None:
        assert await score_tools_for_turn(_intelligence(route_to="response"), "run-1") is None
        assert selector.embed_calls == []

    async def test_no_domain_means_no_planner_scores_but_the_global_order(
        self, selector: _FakeSelector
    ) -> None:
        """The planner scores need domains; the ranking needs a question. An
        actionable turn the router could not place in a domain is exactly where
        the loop used to bind everything — the ranking must not skip it."""
        scores = await score_tools_for_turn(_intelligence(domains=[]), "run-1")
        assert scores is not None
        assert "all_scores" not in scores
        assert scores[GLOBAL_RANKING_KEY]
        assert selector.select_calls == []

    async def test_an_empty_pivot_is_not_scored(self, selector: _FakeSelector) -> None:
        assert (
            await score_tools_for_turn(_intelligence(domains=[], english_query=""), "run-1") is None
        )
        assert selector.embed_calls == []

    async def test_an_uninitialized_selector_scores_nothing(self, selector: _FakeSelector) -> None:
        selector.initialized = False
        assert await score_tools_for_turn(_intelligence(), "run-1") is None

    async def test_a_failure_degrades_to_no_scores_never_raises(
        self, selector: _FakeSelector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _boom(query: str) -> list[float]:
            raise RuntimeError("embedding provider down")

        monkeypatch.setattr(selector, "embed_query", _boom)
        assert await score_tools_for_turn(_intelligence(), "run-1") is None


class TestTheRouterUsesIt:
    def test_the_router_node_delegates_its_scoring(self) -> None:
        import inspect

        from src.domains.agents.nodes import router_node_v3

        source = inspect.getsource(router_node_v3.router_node_v3)
        assert "score_tools_for_turn(intelligence, run_id)" in source
        assert "select_tools(" not in source, "the router scores through the one seam"
        assert scoring.GLOBAL_RANKING_KEY == "global_ranking"
