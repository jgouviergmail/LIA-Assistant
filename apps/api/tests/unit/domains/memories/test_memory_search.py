"""The one door between a LOOKUP and the memory store (ADR-313).

A lookup — a subject someone asks about, a person's name — is embedded as a
key, never as a chat line (the triviality patterns collide with real names),
BEFORE any session opens; and « I could not look » (no vector) is never
flattened into « there is nothing ».
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.memories import search as search_module

_VECTOR = [0.1] * 8


def _repository(results: list) -> MagicMock:
    repo = MagicMock()
    repo.search_by_relevance = AsyncMock(return_value=results)
    return repo


@pytest.mark.unit
class TestSearchMemories:
    async def test_the_lookup_is_embedded_as_a_key_before_any_session(self) -> None:
        events: list[str] = []
        repo = _repository([(SimpleNamespace(content="likes tea"), 0.9)])

        async def embed(**kwargs: object) -> list[float]:
            events.append("embed")
            assert kwargs["is_conversational"] is False
            assert kwargs["message"] == "Fine"
            return _VECTOR

        @asynccontextmanager
        async def session():  # noqa: ANN202
            events.append("session")
            yield MagicMock()

        with (
            patch.object(search_module, "get_or_compute_embedding", side_effect=embed),
            patch.object(search_module, "get_db_context", session),
            patch.object(search_module, "MemoryRepository", return_value=repo),
        ):
            results = await search_module.search_memories(
                uuid4(), "Fine", limit=7, min_score=0.6, categories={"preference"}
            )

        assert events == ["embed", "session"]
        assert results == repo.search_by_relevance.return_value
        kwargs = repo.search_by_relevance.await_args.kwargs
        assert kwargs["query_embedding"] == _VECTOR
        assert kwargs["limit"] == 7 and kwargs["min_score"] == 0.6
        assert kwargs["categories"] == {"preference"}

    async def test_no_vector_means_could_not_look_and_opens_nothing(self) -> None:
        with (
            patch.object(search_module, "get_or_compute_embedding", AsyncMock(return_value=None)),
            patch.object(
                search_module, "get_db_context", side_effect=AssertionError("session opened")
            ),
        ):
            results = await search_module.search_memories(
                uuid4(), "my dentist", limit=5, min_score=0.5
            )

        assert results is None

    async def test_embed_lookup_never_skips_a_short_key(self) -> None:
        """« ok » as a chat line is trivial; as a lookup key it is searched."""
        embed = AsyncMock(return_value=_VECTOR)
        with patch.object(search_module, "get_or_compute_embedding", embed):
            assert await search_module.embed_lookup("ok", user_id="u") == _VECTOR

        assert embed.await_args.kwargs["is_conversational"] is False
