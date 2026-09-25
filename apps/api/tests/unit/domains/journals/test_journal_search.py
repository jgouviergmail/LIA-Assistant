"""The one door between a LOOKUP and LIA's journal (ADR-318).

The subject is embedded with the JOURNAL's own model — the one its entries were
indexed with — BEFORE any session opens (ADR-304); the raw L0 feedstock is left
out; the lookup never FEEDS the controller that learns the injection's floor;
and « I could not look » (no vector) is never flattened into « there is
nothing ».
"""

from __future__ import annotations

import ast
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH
from src.domains.journals import search as search_module

pytestmark = pytest.mark.unit

_VECTOR = [0.1] * 8


def _repository(results: list[tuple[object, float]]) -> MagicMock:
    repo = MagicMock()
    repo.search_by_relevance = AsyncMock(return_value=results)
    return repo


def _embeddings(vector: list[float] | None, events: list[str] | None = None) -> MagicMock:
    async def embed(text: str) -> list[float] | None:
        if events is not None:
            events.append("embed")
        return vector

    model = MagicMock()
    model.aembed_query = AsyncMock(side_effect=embed)
    return model


class TestSearchJournal:
    async def test_the_subject_is_embedded_by_the_journal_model_before_any_session(self) -> None:
        events: list[str] = []
        entry = SimpleNamespace(title="Short answers in the morning")
        repo = _repository([(entry, 0.81)])
        model = _embeddings(_VECTOR, events)

        @asynccontextmanager
        async def session() -> AsyncIterator[MagicMock]:
            events.append("session")
            yield MagicMock()

        with (
            patch.object(search_module, "get_journal_embeddings", return_value=model),
            patch.object(search_module, "get_db_context", session),
            patch.object(search_module, "JournalEntryRepository", return_value=repo),
        ):
            results = await search_module.search_journal(
                uuid4(), "morning routine", limit=4, min_score=0.6
            )

        assert events == ["embed", "session"]
        assert results == [(entry, 0.81)]
        kwargs = repo.search_by_relevance.await_args.kwargs
        assert kwargs["query_embedding"] == _VECTOR
        assert kwargs["limit"] == 4 and kwargs["min_score"] == 0.6
        assert kwargs["exclude_levels"] == ["L0"]

    def test_the_lookup_never_reads_nor_feeds_the_injection_s_learned_floor(self) -> None:
        """Structural, because a patched source module cannot see a direct import:
        the door imports nothing from the adaptive controller (measured: its
        learned floor kept one of six matching entries, ADR-318)."""
        tree = ast.parse(Path(search_module.__file__).read_text(encoding="utf-8"))
        imported = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ] + [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ]

        assert not [name for name in imported if name.startswith("src.infrastructure.adaptive")]

    async def test_no_vector_means_could_not_look_and_opens_nothing(self) -> None:
        with (
            patch.object(search_module, "get_journal_embeddings", return_value=_embeddings(None)),
            patch.object(
                search_module, "get_db_context", side_effect=AssertionError("session opened")
            ),
        ):
            assert (
                await search_module.search_journal(uuid4(), "morning", limit=3, min_score=0.5)
                is None
            )

    async def test_a_failing_provider_is_could_not_look_too(self) -> None:
        model = MagicMock()
        model.aembed_query = AsyncMock(side_effect=RuntimeError("provider down"))
        with patch.object(search_module, "get_journal_embeddings", return_value=model):
            assert (
                await search_module.search_journal(uuid4(), "morning", limit=3, min_score=0.5)
                is None
            )

    async def test_the_subject_is_cut_where_every_embedding_is(self) -> None:
        model = _embeddings(_VECTOR)
        with (
            patch.object(search_module, "get_journal_embeddings", return_value=model),
            patch.object(search_module, "get_db_context", side_effect=AssertionError("unused")),
        ):
            await search_module.embed_journal_lookup("x" * 5000)

        sent = model.aembed_query.await_args.args[0]
        assert len(sent) == USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH

    async def test_a_blank_subject_embeds_nothing(self) -> None:
        model = _embeddings(_VECTOR)
        with patch.object(search_module, "get_journal_embeddings", return_value=model):
            assert await search_module.embed_journal_lookup("   ") is None

        model.aembed_query.assert_not_awaited()


class TestThePersonsPreference:
    @pytest.mark.parametrize(("stored", "expected"), [(True, True), (False, False), (None, False)])
    async def test_is_read_from_their_row(self, stored: bool | None, expected: bool) -> None:
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=stored)
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)

        @asynccontextmanager
        async def session() -> AsyncIterator[MagicMock]:
            yield db

        with patch.object(search_module, "get_db_context", session):
            assert await search_module.journal_enabled_for(uuid4()) is expected

        statement = str(db.execute.await_args.args[0])
        assert "journals_enabled" in statement
