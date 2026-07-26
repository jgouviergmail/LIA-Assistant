"""``SemanticToolSelector.select_tools`` — which tools the LLM is even shown.

Everything downstream is bounded by this call: a tool that does not come out of
here is never injected, never planned, never executed. The failure is silent by
construction — the assistant simply answers that it cannot do the thing.

The existing suites cover the *arithmetic* in isolation (softmax calibration,
the hybrid formula, the content hash). What was never driven is the selection
itself: the threshold that drops a tool, the truncation, the per-request MCP
embeddings fallback, and the manifest lookup that decides whether a high-scoring
tool survives at all.

The embeddings are deterministic orthonormal vectors, so every cosine
similarity here is an exact 1.0 or 0.0 — the assertions are about the selection
logic, never about a model's mood.
"""

import pytest

from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.agents.services.tool_selector import (
    DEFAULT_CALIBRATED_PRIMARY_MIN,
    DEFAULT_MAX_TOOLS,
    SemanticToolSelector,
)

pytestmark = pytest.mark.unit

# Orthonormal basis: cosine(v_i, v_j) == 1.0 when i == j, else 0.0.
_DIM = 4
AXES: dict[str, list[float]] = {
    name: [1.0 if i == index else 0.0 for i in range(_DIM)]
    for index, name in enumerate(("emails", "events", "contacts", "files"))
}


class _StubEmbeddings:
    """Embeds a query by looking up the axis its text names."""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._mapping = mapping
        self.calls: list[str] = []

    async def aembed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        return self._mapping.get(text, [0.0] * _DIM)


def make_manifest(name: str, agent: str = "test_agent") -> ToolManifest:
    """A manifest carrying only what the selector reads."""
    return ToolManifest(
        name=name,
        agent=agent,
        description=f"Description of {name}",
        parameters=[],
        outputs=[OutputFieldSchema(path="items[]", type="array", description="Items")],
        cost=CostProfile(est_tokens_in=10, est_tokens_out=10),
        permissions=PermissionProfile(required_scopes=[]),
    )


def build_selector(
    *,
    tools: dict[str, str],
    manifests: dict[str, ToolManifest] | None = None,
    hybrid_enabled: bool = False,
    calibrated_primary_min: float = 0.0,
    max_tools: int = 10,
) -> SemanticToolSelector:
    """A selector wired by hand — ``initialize()`` would call the LLM factory.

    Args:
        tools: tool name → axis name its single keyword embeds on.
        manifests: overrides the cached manifests (defaults to one per tool).
        hybrid_enabled: whether description embeddings take part in scoring.
        calibrated_primary_min: exclusion threshold on the CALIBRATED score.
        max_tools: default truncation.
    """
    selector = SemanticToolSelector()
    selector._embeddings = _StubEmbeddings(AXES)
    selector._initialized = True
    selector._hybrid_enabled = hybrid_enabled
    selector._calibrated_primary_min = calibrated_primary_min
    selector._max_tools = max_tools
    for tool_name, axis in tools.items():
        selector._tool_keyword_embeddings[tool_name] = [AXES[axis]]
        selector._tool_keywords[tool_name] = [axis]
    selector._tool_manifests = (
        manifests
        if manifests is not None
        else {tool_name: make_manifest(tool_name) for tool_name in tools}
    )
    return selector


@pytest.fixture
def selector() -> SemanticToolSelector:
    return build_selector(
        tools={"search_emails_tool": "emails", "get_events_tool": "events"},
    )


class TestInitializationGuard:
    async def test_selecting_before_initialization_is_a_loud_failure(self) -> None:
        # A silent empty result would look like "no tool matches" and the
        # assistant would answer that it cannot help.
        raw = SemanticToolSelector()

        with pytest.raises(RuntimeError, match="not initialized"):
            await raw.select_tools("anything")

    async def test_an_initialized_flag_without_embeddings_still_fails(self) -> None:
        raw = SemanticToolSelector()
        raw._initialized = True

        with pytest.raises(RuntimeError):
            await raw.select_tools("anything")


class TestSelection:
    async def test_the_matching_tool_ranks_first(self, selector: SemanticToolSelector) -> None:
        result = await selector.select_tools("emails")

        assert result.tool_names[0] == "search_emails_tool"

    async def test_the_query_is_embedded_once(self, selector: SemanticToolSelector) -> None:
        await selector.select_tools("emails")

        assert selector._embeddings.calls == ["emails"]  # type: ignore[union-attr]

    async def test_every_scored_tool_appears_in_all_scores(
        self, selector: SemanticToolSelector
    ) -> None:
        result = await selector.select_tools("emails")

        assert set(result.all_scores) == {"search_emails_tool", "get_events_tool"}

    async def test_calibrated_scores_form_a_distribution(
        self, selector: SemanticToolSelector
    ) -> None:
        result = await selector.select_tools("emails")

        assert sum(result.all_scores.values()) == pytest.approx(1.0)
        assert result.top_score == pytest.approx(max(result.all_scores.values()))

    async def test_a_query_matching_nothing_still_returns_a_ranking(
        self, selector: SemanticToolSelector
    ) -> None:
        # Every raw score is 0 → the calibration cannot discriminate and hands
        # back a uniform distribution. Nothing is "the" answer.
        result = await selector.select_tools("unrelated")

        assert len(result.all_scores) == 2
        assert all(score == pytest.approx(0.5) for score in result.all_scores.values())


class TestProductionDefaults:
    """The shipped constants, exercised as they actually run."""

    async def test_a_negligible_score_is_excluded_by_the_default_threshold(self) -> None:
        # Softmax at temperature 0.1 leaves the loser around 4.5e-5 — a number
        # that reads as "0.0" in the logs but is strictly positive. Only the
        # 0.15 default keeps it out of the injected set; a threshold of 0 would
        # hand the LLM a tool the query does not match at all.
        selector = build_selector(
            tools={"search_emails_tool": "emails", "get_events_tool": "events"},
            calibrated_primary_min=DEFAULT_CALIBRATED_PRIMARY_MIN,
        )

        result = await selector.select_tools("emails")

        assert result.tool_names == ["search_emails_tool"]
        assert 0 < result.all_scores["get_events_tool"] < DEFAULT_CALIBRATED_PRIMARY_MIN

    async def test_a_zero_threshold_lets_a_negligible_score_through(self) -> None:
        # Characterizes WHY the threshold exists, rather than asserting a value.
        selector = build_selector(
            tools={"search_emails_tool": "emails", "get_events_tool": "events"},
            calibrated_primary_min=0.0,
        )

        result = await selector.select_tools("emails")

        assert "get_events_tool" in result.tool_names

    async def test_the_default_cap_is_eight_tools(self) -> None:
        selector = SemanticToolSelector()

        assert selector._max_tools == DEFAULT_MAX_TOOLS == 8


class TestThresholdAndTruncation:
    async def test_a_tool_at_or_below_the_threshold_is_dropped(self) -> None:
        selector = build_selector(
            tools={"search_emails_tool": "emails", "get_events_tool": "events"},
            calibrated_primary_min=0.5,
        )

        result = await selector.select_tools("emails")

        # The loser's calibrated score sits under the bar; the winner's is above.
        assert result.tool_names == ["search_emails_tool"]
        assert "get_events_tool" in result.all_scores

    async def test_the_threshold_is_strict(self) -> None:
        # Two identical scores calibrate to 0.5 each; a 0.5 bar excludes BOTH.
        selector = build_selector(
            tools={"a_tool": "emails", "b_tool": "emails"},
            calibrated_primary_min=0.5,
        )

        result = await selector.select_tools("emails")

        assert result.tool_names == []

    async def test_max_results_truncates_before_the_threshold_is_applied(self) -> None:
        selector = build_selector(
            tools={"a_tool": "emails", "b_tool": "events", "c_tool": "contacts"},
        )

        result = await selector.select_tools("emails", max_results=1)

        assert result.tool_names == ["a_tool"]
        # The other candidates are still scored — truncation is a display cap,
        # not a scoring cap.
        assert len(result.all_scores) == 3

    async def test_the_configured_default_caps_the_list(self) -> None:
        selector = build_selector(
            tools={f"tool_{i}": "emails" for i in range(5)},
            max_tools=2,
        )

        result = await selector.select_tools("emails")

        assert len(result.tool_names) == 2

    async def test_an_explicit_max_results_overrides_the_default(self) -> None:
        selector = build_selector(
            tools={f"tool_{i}": "emails" for i in range(5)},
            max_tools=2,
        )

        result = await selector.select_tools("emails", max_results=4)

        assert len(result.tool_names) == 4


class TestAvailableToolsRestriction:
    async def test_only_the_offered_tools_are_scored(self, selector: SemanticToolSelector) -> None:
        offered = [make_manifest("get_events_tool")]

        result = await selector.select_tools("emails", available_tools=offered)

        assert set(result.all_scores) == {"get_events_tool"}
        assert result.tool_names == ["get_events_tool"]

    async def test_an_offered_tool_with_no_embedding_scores_zero_not_crash(
        self, selector: SemanticToolSelector
    ) -> None:
        offered = [make_manifest("get_events_tool"), make_manifest("unknown_tool")]

        result = await selector.select_tools("events", available_tools=offered)

        assert result.all_scores["unknown_tool"] == pytest.approx(min(result.all_scores.values()))

    async def test_the_offered_manifest_wins_over_the_cached_one(
        self, selector: SemanticToolSelector
    ) -> None:
        # Same name, different agent: the per-request manifest must be the one
        # handed back, otherwise a user MCP tool resolves to a stale contract.
        offered = [make_manifest("search_emails_tool", agent="user_mcp_agent")]

        result = await selector.select_tools("emails", available_tools=offered)

        assert result.selected_tools[0].tool_manifest.agent == "user_mcp_agent"


class TestExtraEmbeddings:
    """Per-request vectors — how user MCP tools get scored at all."""

    async def test_a_tool_known_only_through_extra_embeddings_is_scored(self) -> None:
        selector = build_selector(tools={"search_emails_tool": "emails"})
        mcp_manifest = make_manifest("hub_search", agent="user_mcp_agent")

        result = await selector.select_tools(
            "contacts",
            available_tools=[make_manifest("search_emails_tool"), mcp_manifest],
            extra_embeddings={
                "hub_search": {
                    "description": AXES["contacts"],
                    "keywords": [AXES["contacts"]],
                    "keyword_names": ["contacts"],
                }
            },
        )

        assert result.tool_names[0] == "hub_search"

    async def test_the_singleton_cache_wins_over_the_per_request_vectors(self) -> None:
        # A stale per-request vector must never override the startup cache.
        selector = build_selector(tools={"search_emails_tool": "emails"})

        result = await selector.select_tools(
            "emails",
            available_tools=[make_manifest("search_emails_tool")],
            extra_embeddings={
                "search_emails_tool": {
                    "keywords": [AXES["files"]],
                    "keyword_names": ["files"],
                }
            },
        )

        assert result.all_scores["search_emails_tool"] == pytest.approx(1.0)

    async def test_extra_keywords_without_names_still_score(self) -> None:
        selector = build_selector(tools={"search_emails_tool": "emails"})

        result = await selector.select_tools(
            "contacts",
            available_tools=[make_manifest("search_emails_tool"), make_manifest("hub_search")],
            extra_embeddings={"hub_search": {"keywords": [AXES["contacts"]]}},
        )

        assert result.tool_names[0] == "hub_search"


class TestManifestResolution:
    async def test_a_top_scoring_tool_without_a_manifest_is_dropped(self) -> None:
        # Reachable when a per-request embedding names a tool that neither the
        # offered list nor the startup cache knows. The score survives in
        # `all_scores`, so `top_score` can point at a tool that was never
        # injected — a discrepancy the debug panel surfaces.
        selector = build_selector(
            tools={"search_emails_tool": "emails", "ghost_tool": "contacts"},
            manifests={"search_emails_tool": make_manifest("search_emails_tool")},
        )

        result = await selector.select_tools("contacts")

        assert "ghost_tool" not in result.tool_names
        assert result.all_scores["ghost_tool"] == pytest.approx(result.top_score)

    async def test_the_drop_is_logged_rather_than_silent(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # The assistant will answer that it cannot do the thing it scored
        # highest on; without this line nothing in the logs explains why.
        selector = build_selector(
            tools={"search_emails_tool": "emails", "ghost_tool": "contacts"},
            manifests={"search_emails_tool": make_manifest("search_emails_tool")},
        )

        with caplog.at_level("WARNING"):
            await selector.select_tools("contacts")

        assert "semantic_tool_selection_manifest_missing" in caplog.text
        assert "ghost_tool" in caplog.text

    async def test_a_resolvable_tool_logs_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        selector = build_selector(tools={"search_emails_tool": "emails"})

        with caplog.at_level("WARNING"):
            await selector.select_tools("emails")

        assert "semantic_tool_selection_manifest_missing" not in caplog.text

    async def test_a_manifest_missing_for_everything_yields_no_tool(self) -> None:
        selector = build_selector(tools={"a_tool": "emails"}, manifests={})

        result = await selector.select_tools("emails")

        assert result.selected_tools == []


class TestUncertaintyFlag:
    async def test_a_confident_winner_raises_no_uncertainty(self) -> None:
        selector = build_selector(
            tools={"search_emails_tool": "emails", "get_events_tool": "events"},
            calibrated_primary_min=0.3,
        )

        result = await selector.select_tools("emails")

        assert result.tool_names == ["search_emails_tool"]
        assert result.has_uncertainty is False

    async def test_a_thin_winner_among_many_flags_uncertainty(self) -> None:
        # Five equal candidates → 0.2 each, under the 0.40 confidence bar.
        selector = build_selector(tools={f"tool_{i}": "emails" for i in range(5)})

        result = await selector.select_tools("emails")

        assert result.has_uncertainty is True
        assert all(match.confidence != "high" for match in result.selected_tools)


class TestHybridScoring:
    async def test_the_description_vector_contributes_when_hybrid_is_on(self) -> None:
        selector = build_selector(
            tools={"a_tool": "emails", "b_tool": "emails"},
            hybrid_enabled=True,
        )
        # Same keyword axis for both; only the description separates them.
        selector._tool_description_embeddings["a_tool"] = AXES["emails"]
        selector._tool_description_embeddings["b_tool"] = AXES["files"]

        result = await selector.select_tools("emails")

        assert result.tool_names[0] == "a_tool"

    async def test_descriptions_are_ignored_when_hybrid_is_off(self) -> None:
        selector = build_selector(
            tools={"a_tool": "emails", "b_tool": "emails"},
            hybrid_enabled=False,
        )
        selector._tool_description_embeddings["a_tool"] = AXES["emails"]
        selector._tool_description_embeddings["b_tool"] = AXES["files"]

        result = await selector.select_tools("emails")

        assert result.all_scores["a_tool"] == pytest.approx(result.all_scores["b_tool"])


class TestKeywordMaxPooling:
    async def test_the_best_keyword_of_a_tool_decides_its_score(self) -> None:
        selector = build_selector(tools={"multi_tool": "files"})
        # Add a second keyword that matches the query exactly.
        selector._tool_keyword_embeddings["multi_tool"] = [AXES["files"], AXES["emails"]]
        selector._tool_keywords["multi_tool"] = ["files", "emails"]
        selector._tool_manifests["other_tool"] = make_manifest("other_tool")
        selector._tool_keyword_embeddings["other_tool"] = [AXES["events"]]
        selector._tool_keywords["other_tool"] = ["events"]

        result = await selector.select_tools("emails")

        # Max-pooling, not averaging: the matching keyword carries the tool.
        assert result.tool_names[0] == "multi_tool"


class TestPublicHelpers:
    def test_cached_tools_list_what_scoring_can_reach(self, selector: SemanticToolSelector) -> None:
        assert set(selector.get_cached_tools()) == {"search_emails_tool", "get_events_tool"}

    def test_is_initialized_reflects_the_flag(self, selector: SemanticToolSelector) -> None:
        assert selector.is_initialized() is True
        assert SemanticToolSelector().is_initialized() is False

    def test_reset_instance_clears_the_singleton(self) -> None:
        SemanticToolSelector._instance = SemanticToolSelector()

        SemanticToolSelector.reset_instance()

        assert SemanticToolSelector._instance is None
