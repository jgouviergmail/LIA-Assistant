"""Shared harness for RAG retrieval unit tests.

``retrieve_rag_context`` needs ten collaborators patched to run: two
repositories, the query embedder, Redis, the BM25 manager, the tokenizer, the
embedding-tracking context and four Prometheus metrics. Every test in
``test_retrieval*.py`` was rebuilding that stack by hand, which buried the one
line that actually differed between them.

This module builds the whole stack from a declarative corpus so a test reads as
"these chunks, these scores, this threshold — what comes back?".
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

_RETRIEVAL = "src.domains.rag_spaces.retrieval"


@dataclass
class FakeChunk:
    """One indexed chunk with the two scores the fusion combines.

    Attributes:
        content: Chunk text, also used as the BM25 corpus document.
        semantic: Cosine similarity the repository reports for this chunk.
        bm25: Raw (un-normalised) BM25 score the index reports for the query.
        filename: Source document name carried through to the result.
    """

    content: str
    semantic: float
    bm25: float = 0.0
    filename: str = "doc.txt"
    chunk_id: UUID = field(default_factory=uuid4)


@contextlib.contextmanager
def retrieval_stack(
    chunks: list[FakeChunk],
    *,
    space_id: UUID,
    space_name: str = "Docs",
    system: bool = False,
    corpus_extra: list[tuple[UUID, str]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Patch every collaborator of ``retrieve_rag_context`` for one corpus.

    Args:
        chunks: Chunks the semantic search returns, in the order it returns them.
        space_id: Space the chunks belong to.
        space_name: Display name carried into the results.
        system: Patch the system-space lookup instead of the user-space one.
        corpus_extra: Extra ``(id, content)`` rows present in the BM25 corpus but
            absent from the semantic candidates — the real asymmetry, since the
            corpus spans the whole space while candidates are the top ``limit*3``.

    Yields:
        Dict of the mocks a test may want to assert on (``chunk_repo``,
        ``space_repo``, ``bm25``).
    """
    space = MagicMock(id=space_id, name=space_name, serving_embedding_model=None)

    space_repo = AsyncMock()
    if system:
        space_repo.get_active_system_spaces.return_value = [space]
    else:
        space_repo.get_active_for_user.return_value = [space]

    mock_chunks = []
    for c in chunks:
        m = MagicMock()
        m.id = c.chunk_id
        m.content = c.content
        m.space_id = space_id
        m.chunk_index = len(mock_chunks)
        m.metadata_ = {"original_filename": c.filename}
        mock_chunks.append(m)

    chunk_repo = AsyncMock()
    chunk_repo.search_by_similarity.return_value = [
        (m, c.semantic) for m, c in zip(mock_chunks, chunks, strict=True)
    ]
    corpus = [(c.chunk_id, c.content) for c in chunks] + list(corpus_extra or [])
    chunk_repo.get_corpus_for_spaces.return_value = corpus

    # BM25 scores follow the corpus order the repository just returned; extra
    # rows score 0 unless the test gave them a score through `corpus_extra`.
    bm25 = MagicMock()
    bm25.get_scores.return_value = [c.bm25 for c in chunks] + [0.0] * len(corpus_extra or [])
    bm25_manager = MagicMock()
    bm25_manager.get_or_build_index.return_value = (bm25, [str(cid) for cid, _ in corpus])

    redis = AsyncMock()
    redis.get.return_value = None

    with (
        patch(f"{_RETRIEVAL}.RAGSpaceRepository", return_value=space_repo),
        patch(f"{_RETRIEVAL}.RAGChunkRepository", return_value=chunk_repo),
        patch(f"{_RETRIEVAL}.embed_rag_query_cached", AsyncMock(return_value=[0.1] * 8)),
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new_callable=AsyncMock,
            return_value=redis,
        ),
        patch(f"{_RETRIEVAL}.get_bm25_manager", return_value=bm25_manager),
        patch(f"{_RETRIEVAL}.tokenize_text", return_value=["query", "tokens"]),
        patch(f"{_RETRIEVAL}.set_embedding_context"),
        patch(f"{_RETRIEVAL}.clear_embedding_context"),
        patch(f"{_RETRIEVAL}.rag_retrieval_requests_total"),
        patch(f"{_RETRIEVAL}.rag_system_retrieval_total"),
        patch(f"{_RETRIEVAL}.rag_retrieval_duration_seconds"),
        patch(f"{_RETRIEVAL}.rag_retrieval_chunks_returned"),
        patch(f"{_RETRIEVAL}.rag_retrieval_skipped_total"),
    ):
        yield {"space_repo": space_repo, "chunk_repo": chunk_repo, "bm25": bm25}


@contextlib.contextmanager
def retrieval_settings(
    *,
    min_score: float,
    bm25_bonus_weight: float = 0.05,
    limit: int = 5,
    max_context_tokens: int = 2000,
) -> Iterator[MagicMock]:
    """Patch the retrieval settings a test depends on, and only those."""
    with patch(f"{_RETRIEVAL}.settings") as s:
        s.rag_spaces_retrieval_limit = limit
        s.rag_spaces_retrieval_min_score = min_score
        s.rag_spaces_max_context_tokens = max_context_tokens
        s.rag_spaces_bm25_bonus_weight = bm25_bonus_weight
        yield s
