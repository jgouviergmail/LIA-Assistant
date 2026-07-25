"""Tests for RAG Spaces reindexation orchestration (start_reindexation).

Covers the ``run_in_background`` branch (v1.23.5): the in-container CLI
(``scripts/reindex_rag_spaces.py``) awaits the work to completion, while HTTP
callers keep the detached fire-and-forget behaviour. Also pins the durable
requeue (audit F001): the READY/ERROR → PENDING flip is committed BEFORE any
processing is launched, so a crash at any later point leaves recoverable rows.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.rag_spaces import reindex


@pytest.fixture
def fake_document():
    """Return a single fake RAG document to reindex."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.status = "ready"
    doc.embedding_model = "text-embedding-old"
    return doc


def _close_coroutine(coro, *_args, **_kwargs):
    """Close the fire-and-forget coroutine so it is not reported as un-awaited."""
    close = getattr(coro, "close", None)
    if close is not None:
        close()


async def _drive_start_reindexation(run_in_background, document, events=None):
    """Run start_reindexation with every I/O dependency mocked out."""
    repo = MagicMock()
    repo.get_all_for_reindex = AsyncMock(return_value=[document])

    async def _record_requeue(ids):
        if events is not None:
            events.append(("requeued", list(ids)))
        return len(ids)

    jobs = MagicMock()
    jobs.requeue_documents_for_reindex = AsyncMock(side_effect=_record_requeue)

    def _record_launch(coro, *args, **kwargs):
        if events is not None:
            events.append(("launched", None))
        _close_coroutine(coro)

    async def _record_commit():
        if events is not None:
            events.append(("committed", None))

    # The session must be an AsyncMock: _persist_reindex_intent awaits
    # db.commit() (the single atomic commit — audit F001/V8).
    db = AsyncMock()
    db.commit = AsyncMock(side_effect=_record_commit)

    with (
        patch.object(reindex, "_get_redis", AsyncMock(return_value=None)),
        patch.object(reindex, "RAGDocumentRepository", return_value=repo),
        patch.object(reindex, "RAGJobsRepository", return_value=jobs),
        patch.object(reindex, "reset_rag_embeddings"),
        patch.object(reindex, "_alter_vector_dimensions_if_needed", AsyncMock()),
        # Isolate the run_in_background orchestration from AC-001 continuity
        # detection: None dims => no generational split (pin/flip covered by the
        # real-PostgreSQL integration tests, not these pure orchestration mocks).
        patch.object(reindex, "_current_vector_dims", AsyncMock(return_value=None)),
        patch.object(reindex, "_reindex_all_documents", AsyncMock()) as reindex_all,
        patch.object(
            reindex, "safe_fire_and_forget", side_effect=_record_launch
        ) as fire_and_forget,
    ):
        result = await reindex.start_reindexation(db, run_in_background=run_in_background)
    return result, reindex_all, fire_and_forget, jobs


async def test_cli_mode_awaits_reindex_to_completion(fake_document):
    """run_in_background=False awaits the work inline and never detaches it."""
    result, reindex_all, fire_and_forget, _jobs = await _drive_start_reindexation(
        run_in_background=False, document=fake_document
    )

    reindex_all.assert_awaited_once()
    fire_and_forget.assert_not_called()
    assert result["total_documents"] == 1


async def test_http_mode_detaches_reindex(fake_document):
    """run_in_background=True (default) detaches the work and never awaits inline."""
    result, reindex_all, fire_and_forget, _jobs = await _drive_start_reindexation(
        run_in_background=True, document=fake_document
    )

    fire_and_forget.assert_called_once()
    reindex_all.assert_not_awaited()
    assert result["total_documents"] == 1


async def test_documents_are_durably_requeued_and_committed_before_launch(fake_document):
    """Requeue then ONE commit, both strictly BEFORE the drain starts.

    The committed requeue is the persistent reindex job state (audit F001):
    if the process dies right after the launch, the reaper recovers every
    remaining document. The V8 hardening pins the commit itself in the order —
    the destructive DDL and the requeue share that single commit, so no crash
    point can separate destroyed chunks from recorded work.
    """
    events: list = []
    _result, _reindex_all, _faf, jobs = await _drive_start_reindexation(
        run_in_background=True, document=fake_document, events=events
    )

    jobs.requeue_documents_for_reindex.assert_awaited_once_with([fake_document.id])
    assert events == [
        ("requeued", [fake_document.id]),
        ("committed", None),
        ("launched", None),
    ]
