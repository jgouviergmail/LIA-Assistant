"""Unit tests for the RAG query embedding cache (TTL + single-flight).

The cache deduplicates the user-RAG and system-RAG query embeds within a
turn (they run concurrently since the parallel context injections) and
avoids re-embedding on retries/repeated queries.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.rag_spaces import embedding as embedding_module
from src.domains.rag_spaces.embedding import embed_rag_query_cached


@pytest.fixture(autouse=True)
def _clean_query_cache():
    """Isolate each test from cached vectors and in-flight tasks."""
    embedding_module._query_cache.clear()
    embedding_module._query_inflight.clear()
    yield
    embedding_module._query_cache.clear()
    embedding_module._query_inflight.clear()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sequential_identical_queries_hit_cache():
    """A second identical query returns the cached vector without an API call."""
    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_query.return_value = [0.1, 0.2, 0.3]

    with patch(
        "src.domains.rag_spaces.embedding.get_rag_embeddings",
        return_value=mock_embeddings,
    ):
        first = await embed_rag_query_cached("quantum physics")
        second = await embed_rag_query_cached("quantum physics")

    assert first == [0.1, 0.2, 0.3]
    assert second == [0.1, 0.2, 0.3]
    assert mock_embeddings.aembed_query.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_identical_queries_single_flight():
    """Concurrent identical queries share ONE in-flight embed (no duplicate API call).

    This is the user-RAG + system-RAG scenario: both retrievals embed the same
    user message at the same time once context injections run in parallel.
    """
    release = asyncio.Event()

    async def _slow_embed(query: str) -> list[float]:
        await release.wait()
        return [0.5] * 4

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_query.side_effect = _slow_embed

    with patch(
        "src.domains.rag_spaces.embedding.get_rag_embeddings",
        return_value=mock_embeddings,
    ):
        task_a = asyncio.create_task(embed_rag_query_cached("same question"))
        task_b = asyncio.create_task(embed_rag_query_cached("same question"))
        # Let both callers reach the embed/join point before releasing
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        vec_a, vec_b = await asyncio.gather(task_a, task_b)

    assert vec_a == vec_b == [0.5] * 4
    assert mock_embeddings.aembed_query.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_different_queries_are_not_deduplicated():
    """Different texts each get their own embedding call."""
    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_query.side_effect = [[0.1], [0.2]]

    with patch(
        "src.domains.rag_spaces.embedding.get_rag_embeddings",
        return_value=mock_embeddings,
    ):
        first = await embed_rag_query_cached("question A")
        second = await embed_rag_query_cached("question B")

    assert first == [0.1]
    assert second == [0.2]
    assert mock_embeddings.aembed_query.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_failure_is_not_cached():
    """A failed embed propagates and does NOT poison the cache: the next call retries."""
    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_query.side_effect = [RuntimeError("API down"), [0.9]]

    with patch(
        "src.domains.rag_spaces.embedding.get_rag_embeddings",
        return_value=mock_embeddings,
    ):
        with pytest.raises(RuntimeError):
            await embed_rag_query_cached("flaky question")
        # In-flight entry must be cleaned up so the retry can proceed
        assert embedding_module._query_inflight == {}
        retry = await embed_rag_query_cached("flaky question")

    assert retry == [0.9]
    assert mock_embeddings.aembed_query.await_count == 2
