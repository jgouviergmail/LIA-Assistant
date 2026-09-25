"""The journal search tool — LIA re-reads its own notebooks on a subject (ADR-318).

Three gates, read at CALL time and never from the run's context alone: the
instance capability (the operator's switch), the person's own preference (read
from their row, because a voice lookup runs on a runtime that carries no
preference), and the query. A search that could not run is never « nothing is
noted » (ADR-303), and what the manifest publishes is what the tool enforces
(ADR-184).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.journal.catalogue_manifests import (
    JOURNAL_SEARCH_QUERY_MIN_CHARS,
    search_journal_catalogue_manifest,
)
from src.domains.agents.tools import journal_search_tools
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


def _entry(**over: object) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "title": "Short answers before nine",
        "content": "WHEN a question arrives before nine → DO answer in two lines",
        "theme": "learnings",
        "level": "L1",
        "confidence": "high",
        "created_at": datetime(2026, 9, 1, 7, 30, tzinfo=UTC),
    }
    return SimpleNamespace(**{**base, **over})


async def _call(
    *,
    results: object = (),
    capability: bool = True,
    preference: bool = True,
    query: str = "morning answers",
    timezone: str | None = None,
    **kwargs: object,
) -> tuple[UnifiedToolOutput, AsyncMock, AsyncMock]:
    search = AsyncMock(return_value=None if results is None else list(results))
    track = patch.object(journal_search_tools, "track_injected_entries")
    with (
        patch.object(
            journal_search_tools, "is_capability_enabled", AsyncMock(return_value=capability)
        ),
        patch.object(
            journal_search_tools, "journal_enabled_for", AsyncMock(return_value=preference)
        ),
        patch.object(journal_search_tools, "search_journal", search),
        track as tracked,
    ):
        output = await journal_search_tools.search_journal_tool.coroutine(
            query=query,
            runtime=(
                make_tool_runtime(store=object(), timezone=timezone)
                if timezone
                else make_tool_runtime(store=object())
            ),
            **kwargs,
        )
    return output, search, tracked


class TestLookup:
    async def test_matching_entries_reach_the_model_with_what_they_are(self) -> None:
        entry = _entry()

        output, search, tracked = await _call(results=[(entry, 0.812)])

        assert output.success
        assert output.structured_data == {
            "entries": [
                {
                    "title": "Short answers before nine",
                    "content": entry.content,
                    "theme": "learnings",
                    "kind": "directive",
                    "confidence": "high",
                    "written_on": "2026-09-01",
                    "relevance": 0.81,
                }
            ],
            "count": 1,
        }
        tracked.assert_called_once_with([entry.id])
        # The configured floor — never the injection's learned one (measured, ADR-318).
        assert search.await_args.kwargs["min_score"] == settings.journal_context_min_score

    @pytest.mark.parametrize(
        ("level", "kind"), [("L1", "directive"), ("L2", "pattern"), ("L3", "portrait_facet")]
    )
    async def test_the_level_is_named_for_the_model(self, level: str, kind: str) -> None:
        output, _search, _tracked = await _call(results=[(_entry(level=level), 0.7)])

        data = output.structured_data or {}
        assert data["entries"][0]["kind"] == kind

    async def test_the_day_written_is_the_person_s_own(self) -> None:
        """23:30 UTC on the 1st is already the 2nd in Paris."""
        entry = _entry(created_at=datetime(2026, 9, 1, 23, 30, tzinfo=UTC))

        output, _search, _tracked = await _call(results=[(entry, 0.7)], timezone="Europe/Paris")

        data = output.structured_data or {}
        assert data["entries"][0]["written_on"] == "2026-09-02"

    async def test_a_capped_list_never_claims_to_be_every_match(self) -> None:
        output, _search, _tracked = await _call(results=[(_entry(), 0.9), (_entry(), 0.8)])

        assert output.message.startswith("The 2 most relevant journal entries")
        assert "match" not in output.message

    async def test_nothing_matching_is_an_empty_success(self) -> None:
        output, _search, tracked = await _call(results=[])

        assert output.success
        assert output.structured_data == {"entries": [], "count": 0}
        tracked.assert_not_called()

    async def test_the_ceiling_is_the_published_maximum(self) -> None:
        published = {
            c.kind: c.value
            for p in search_journal_catalogue_manifest.parameters
            if p.name == "max_results"
            for c in p.constraints
        }
        assert published["maximum"] == settings.journal_search_max_results

        _output, search, _tracked = await _call(max_results=10_000)

        assert search.await_args.kwargs["limit"] == settings.journal_search_max_results


class TestWhatIsNeverNothing:
    async def test_a_search_that_could_not_run(self) -> None:
        output, _search, _tracked = await _call(results=None)

        assert output.success is False
        assert output.error_code == ToolErrorCode.DEPENDENCY_ERROR.value
        assert "never" in output.message.lower()

    async def test_the_instance_switch(self) -> None:
        output, search, _tracked = await _call(capability=False)

        assert output.error_code == ToolErrorCode.FORBIDDEN.value
        search.assert_not_awaited()

    async def test_the_person_s_preference(self) -> None:
        output, search, _tracked = await _call(preference=False)

        assert output.error_code == ToolErrorCode.FORBIDDEN.value
        assert "not noted" in output.message or "nothing is noted" in output.message
        search.assert_not_awaited()

    async def test_a_query_too_short(self) -> None:
        output, search, _tracked = await _call(
            query=" " + "a" * (JOURNAL_SEARCH_QUERY_MIN_CHARS - 1)
        )

        assert output.error_code == ToolErrorCode.INVALID_INPUT.value
        search.assert_not_awaited()


@pytest.mark.parametrize(
    ("manifest_path", "mode"),
    [
        (
            "src.domains.agents.journal.catalogue_manifests:search_journal_catalogue_manifest",
            "semantic",
        ),
        (
            "src.domains.agents.memory.catalogue_manifests:search_memories_catalogue_manifest",
            "semantic",
        ),
        (
            "src.domains.agents.documents.catalogue_manifests:search_user_documents_catalogue_manifest",
            "hybrid",
        ),
    ],
)
def test_a_semantic_store_declares_it(manifest_path: str, mode: str) -> None:
    """In ``autocorrect`` mode the validator strips conceptual terms from a LITERAL
    search's query: a vector store left at the default would lose the very words
    it matches on (found on the three semantic lookups, ADR-318)."""
    import importlib

    module_name, attribute = manifest_path.split(":")
    manifest = getattr(importlib.import_module(module_name), attribute)

    assert manifest.text_search_mode == mode
