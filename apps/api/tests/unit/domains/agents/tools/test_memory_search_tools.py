"""The memory search tool — long-term memory as an active lookup (ADR-313).

What the loop and the planner get back, under the person's own memory switch;
a search that could not run is never read as « nothing is remembered »
(ADR-303); and every bound the manifest publishes is the bound the tool
enforces, from the same source (ADR-184).
"""

from __future__ import annotations

import typing
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.memory.catalogue_manifests import (
    MEMORY_SEARCH_CATEGORIES,
    MEMORY_SEARCH_QUERY_MIN_CHARS,
    search_memories_catalogue_manifest,
)
from src.domains.agents.tools import memory_search_tools
from src.domains.agents.tools.memory_tools import MemoryCategoryType


def _memory(**over: object) -> SimpleNamespace:
    base = {
        "content": "Drinks green tea every morning",
        "category": "preference",
        "usage_nuance": "",
        "emotional_weight": 0,
        "created_at": datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
    }
    return SimpleNamespace(**{**base, **over})


def _runtime(*, memory_enabled: bool = True) -> SimpleNamespace:
    context = LiaRuntimeContext(
        user_id=uuid4(),
        thread_id="t",
        conversation_id="t",
        memory_enabled=memory_enabled,
    )
    return SimpleNamespace(context=context, config={})


async def _call(
    *,
    results: object,
    query: str = "tea",
    runtime: SimpleNamespace | None = None,
    **kwargs: object,
) -> tuple[object, AsyncMock, AsyncMock]:
    search = AsyncMock(return_value=results)
    track = AsyncMock()
    config = SimpleNamespace(user_id=str(uuid4()))
    with (
        patch.object(memory_search_tools, "validate_runtime_config", return_value=config),
        patch("src.domains.memories.search.search_memories", search),
        patch("src.domains.agents.middleware.memory_injection.track_memory_usage", track),
    ):
        output = await memory_search_tools.search_memories_tool.coroutine(
            query=query, runtime=runtime or _runtime(), **kwargs
        )
    return output, search, track


@pytest.mark.unit
class TestLookup:
    async def test_matching_memories_reach_the_model_with_how_to_use_them(self) -> None:
        painful = _memory(
            content="Father passed away in 2024",
            category="personal",
            usage_nuance="Only mention if the user brings it up",
            emotional_weight=-6,
        )
        output, search, track = await _call(results=[(_memory(), 0.912), (painful, 0.81)])

        assert output.success is True
        memories = output.structured_data["memories"]
        assert output.structured_data["count"] == 2
        assert memories[0] == {
            "content": "Drinks green tea every morning",
            "category": "preference",
            "usage_nuance": None,
            "sensitive": False,
            "recorded_on": "2026-05-04",
            "relevance": 0.91,
        }
        # A painful memory carries its nuance as an obligation flag.
        assert memories[1]["sensitive"] is True
        assert memories[1]["usage_nuance"] == "Only mention if the user brings it up"
        # Used memories feed the purge's usage statistics, like the injection's.
        track.assert_awaited_once()
        assert search.await_args.kwargs["min_score"] == settings.memory_min_search_score

    async def test_an_empty_search_is_a_success_that_says_nothing_matched(self) -> None:
        output, _search, track = await _call(results=[])

        assert output.success is True
        assert output.structured_data == {"memories": [], "count": 0}
        track.assert_not_awaited()

    async def test_a_search_that_could_not_run_is_never_read_as_nothing_remembered(
        self,
    ) -> None:
        output, _search, _track = await _call(results=None)

        assert output.success is False
        assert output.error_code == "DEPENDENCY_ERROR"
        assert "never conclude that nothing is remembered" in output.message

    async def test_the_person_s_memory_switch_is_honoured(self) -> None:
        output, search, _track = await _call(
            results=[(_memory(), 0.9)], runtime=_runtime(memory_enabled=False)
        )

        assert output.success is False
        assert output.error_code == "FORBIDDEN"
        search.assert_not_awaited()

    @pytest.mark.parametrize("query", ["", " ", "a"])
    async def test_a_subject_too_short_is_refused(self, query: str) -> None:
        output, search, _track = await _call(results=[], query=query)

        assert output.success is False
        assert output.error_code == "INVALID_INPUT"
        search.assert_not_awaited()


@pytest.mark.unit
class TestBounds:
    @pytest.mark.parametrize(
        ("asked", "expected"),
        [(None, "ceiling"), (0, 1), (3, 3), (10_000, "ceiling")],
    )
    async def test_max_results_is_clamped_to_the_published_ceiling(
        self, asked: int | None, expected: object
    ) -> None:
        ceiling = settings.memory_max_results
        _output, search, _track = await _call(results=[], max_results=asked)

        limit = search.await_args.kwargs["limit"]
        assert limit == (ceiling if expected == "ceiling" else min(int(expected), ceiling))

    async def test_a_category_narrows_the_search_to_that_family(self) -> None:
        _output, search, _track = await _call(results=[], category="procedural")

        assert search.await_args.kwargs["categories"] == {"procedural"}

    async def test_an_unknown_category_is_refused(self) -> None:
        output, search, _track = await _call(results=[], category="gossip")

        assert output.error_code == "INVALID_PARAM_VALUE"
        search.assert_not_awaited()


@pytest.mark.unit
class TestManifestPublishesWhatTheToolEnforces:
    """ADR-184: a bound the tool enforces is a bound the planner can read."""

    def _parameter(self, name: str) -> object:
        return next(p for p in search_memories_catalogue_manifest.parameters if p.name == name)

    def _constraint(self, name: str, kind: str) -> object:
        return next(c.value for c in self._parameter(name).constraints if c.kind == kind)

    def test_the_result_ceiling_is_the_setting_the_tool_clamps_to(self) -> None:
        assert self._constraint("max_results", "maximum") == settings.memory_max_results
        assert self._constraint("max_results", "minimum") == 1

    def test_the_categories_are_the_stored_vocabulary(self) -> None:
        assert tuple(self._constraint("category", "enum")) == typing.get_args(MemoryCategoryType)
        assert MEMORY_SEARCH_CATEGORIES == typing.get_args(MemoryCategoryType)

    def test_the_category_description_names_every_published_family(self) -> None:
        # A list typed in prose goes stale the day a family is added.
        description = self._parameter("category").description
        for family in typing.get_args(MemoryCategoryType):
            assert family in description

    def test_the_subject_floor_is_the_one_the_tool_applies(self) -> None:
        assert self._constraint("query", "min_length") == MEMORY_SEARCH_QUERY_MIN_CHARS
