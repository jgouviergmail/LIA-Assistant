"""Tests for RAG Spaces reindexation orchestration (start_reindexation).

Covers the ``run_in_background`` branch (v1.23.5): the in-container CLI
(``scripts/reindex_rag_spaces.py``) awaits the work to completion, while HTTP
callers keep the detached fire-and-forget behaviour.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.rag_spaces import reindex


@pytest.fixture
def fake_document():
    """Return a single fake RAG document to reindex."""
    doc = MagicMock()
    doc.embedding_model = "text-embedding-old"
    return doc


def _close_coroutine(coro, *_args, **_kwargs):
    """Close the fire-and-forget coroutine so it is not reported as un-awaited."""
    close = getattr(coro, "close", None)
    if close is not None:
        close()


async def _drive_start_reindexation(run_in_background, document):
    """Run start_reindexation with every I/O dependency mocked out."""
    repo = MagicMock()
    repo.get_all_for_reindex = AsyncMock(return_value=[document])

    with (
        patch.object(reindex, "_get_redis", AsyncMock(return_value=None)),
        patch.object(reindex, "RAGDocumentRepository", return_value=repo),
        patch.object(reindex, "reset_rag_embeddings"),
        patch.object(reindex, "_alter_vector_dimensions_if_needed", AsyncMock()),
        patch.object(reindex, "_reindex_all_documents", AsyncMock()) as reindex_all,
        patch.object(
            reindex, "safe_fire_and_forget", side_effect=_close_coroutine
        ) as fire_and_forget,
    ):
        result = await reindex.start_reindexation(MagicMock(), run_in_background=run_in_background)
    return result, reindex_all, fire_and_forget


async def test_cli_mode_awaits_reindex_to_completion(fake_document):
    """run_in_background=False awaits the work inline and never detaches it."""
    result, reindex_all, fire_and_forget = await _drive_start_reindexation(
        run_in_background=False, document=fake_document
    )

    reindex_all.assert_awaited_once()
    fire_and_forget.assert_not_called()
    assert result["total_documents"] == 1


async def test_http_mode_detaches_reindex(fake_document):
    """run_in_background=True (default) detaches the work and never awaits inline."""
    result, reindex_all, fire_and_forget = await _drive_start_reindexation(
        run_in_background=True, document=fake_document
    )

    fire_and_forget.assert_called_once()
    reindex_all.assert_not_awaited()
    assert result["total_documents"] == 1
