"""Reindex holds its lock via a per-document heartbeat, not a fixed 6h TTL (F001).

The reindex distributed lock used a fixed 6-hour TTL: a crash mid-reindex
blocked every new reindex for 6h. The flag is now acquired with a short,
settings-driven TTL and RENEWED after each processed document, so a live
reindex keeps the lock while a crash frees it within one TTL window. This test
pins the renewal: ``redis.expire(REINDEX_FLAG_KEY, ttl)`` fires once per
document with the configured TTL, and the flag is cleared at the end.
"""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.rag_spaces import reindex


@contextlib.asynccontextmanager
async def _fake_db_context():
    db = AsyncMock()
    db.commit = AsyncMock()
    yield db


def _make_docs(n: int) -> list[MagicMock]:
    docs = []
    for _ in range(n):
        d = MagicMock()
        d.id = uuid4()
        d.space_id = uuid4()
        d.user_id = uuid4()
        d.filename = "stored.bin"
        d.original_filename = "orig.bin"
        d.content_type = "text/plain"
        d.status = "ready"
        docs.append(d)
    return docs


async def test_reindex_renews_lock_after_each_document():
    """The lock TTL is refreshed once per document with the configured value."""
    docs = _make_docs(3)

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.expire = AsyncMock()
    redis.delete = AsyncMock()

    with (
        patch.object(reindex, "_get_redis", AsyncMock(return_value=redis)),
        patch.object(reindex, "process_document", AsyncMock(return_value=True)),
    ):
        await reindex._reindex_all_documents(docs, "text-embedding-new")

    assert redis.expire.await_count == 3, "lock must be renewed once per document"
    for call in redis.expire.await_args_list:
        assert call.args == (
            reindex.REINDEX_FLAG_KEY,
            settings.rag_reindex_lock_ttl_seconds,
        )
    redis.delete.assert_any_await(reindex.REINDEX_FLAG_KEY)


async def test_reindex_never_deletes_chunks_before_reembedding():
    """The destructive pre-delete is gone (audit F001).

    The pre-durable flow deleted a document's chunks and marked it REINDEXING
    *before* re-embedding: a crash mid-embed left a chunkless document. The
    chunk swap now happens atomically inside process_document, so a plain drain
    never touches chunks itself. (AC-001 post-flip cleanup deletes old-generation
    chunks in a SEPARATE phase that runs only after the new generation is built
    and served — never during re-embedding, and never without ``flip_from``.)
    """
    docs = _make_docs(1)
    process = AsyncMock(return_value=True)
    with (
        patch.object(reindex, "_get_redis", AsyncMock(return_value=None)),
        patch.object(reindex, "process_document", process),
        patch.object(reindex, "RAGChunkRepository") as chunk_repo_cls,
    ):
        # Default flip_from=None -> a pure drain with no generational flip.
        await reindex._reindex_all_documents(docs, "text-embedding-new")

    process.assert_awaited_once()
    kwargs = process.await_args.kwargs
    assert kwargs["document_id"] == docs[0].id
    # A plain drain delegates ALL chunk mutation to process_document's atomic
    # swap and never constructs a chunk repository of its own.
    chunk_repo_cls.assert_not_called()


async def test_reindex_lock_ttl_is_bounded_and_not_six_hours():
    """The default lock TTL is short (renewed), not the old fixed 6h wait."""
    assert settings.rag_reindex_lock_ttl_seconds <= 3600
    assert not hasattr(reindex, "REINDEX_TTL_SECONDS")  # the fixed constant is gone


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
