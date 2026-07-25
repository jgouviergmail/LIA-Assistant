"""Generational RAG continuity — same-dimension reindex keeps N readable (AC-001).

Real-PostgreSQL proof that a same-dimension embedding-model change never blocks
reads and never mixes generations:

* while a space is pinned to the OLD generation, the OLD chunks stay fully
  searchable and the NEW chunks built side by side are invisible (no empty
  window, no mix);
* the per-space flip is atomic — serving pointer cleared AND old chunks
  reclaimed in one commit, so a reader sees only the OLD generation or only the
  NEW one;
* a space with a still-unfinished document is NOT flipped — it stays on the
  stable OLD generation ("keep N on failure").

These exercise the repository generational primitives and ``_flip_completed_spaces``
against a live database (the durable pointer + chunk filtering are meaningless
under mocks).
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.rag_spaces import reindex
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDocumentStatus, RAGSpace
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
    RAGSpaceRepository,
)

pytestmark = pytest.mark.integration

OLD_MODEL = "embed-gen-old"
NEW_MODEL = "embed-gen-new"


async def _dims(db: AsyncSession) -> int:
    res = await db.execute(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'rag_chunks'::regclass AND attname = 'embedding'"
        )
    )
    return int(res.scalar_one())


async def _make_space(db: AsyncSession, *, serving: str | None = None) -> RAGSpace:
    space = RAGSpace(name=f"gen-space-{uuid.uuid4().hex[:8]}", serving_embedding_model=serving)
    db.add(space)
    await db.flush()
    return space


async def _make_ready_doc(db: AsyncSession, space_id: uuid.UUID, model: str) -> RAGDocument:
    doc = RAGDocument(
        space_id=space_id,
        filename="f.txt",
        original_filename="f.txt",
        file_size=10,
        content_type="text/plain",
        status=RAGDocumentStatus.READY,
        chunk_count=1,
        embedding_model=model,
    )
    db.add(doc)
    await db.flush()
    return doc


async def _add_chunk(
    db: AsyncSession, *, doc: RAGDocument, space_id: uuid.UUID, model: str, seed: float
) -> None:
    dims = await _dims(db)
    vec = [seed] * dims
    db.add(
        RAGChunk(
            document_id=doc.id,
            space_id=space_id,
            chunk_index=0,
            content=f"content-{model}",
            embedding=vec,
            embedding_model=model,
        )
    )
    await db.flush()


@contextlib.asynccontextmanager
async def _session_ctx(session: AsyncSession):
    """Yield the test session so _flip_completed_spaces runs on the test data.

    _flip_completed_spaces opens its own get_db_context session; under the
    savepoint fixture that separate connection would not see the test's
    uncommitted rows. Patching it to reuse this session lets the flip act on the
    fixture data; its commits release savepoints (rolled back at teardown).
    """
    yield session


class TestGenerationalFiltering:
    async def test_pinned_generation_isolates_search(self, async_session: AsyncSession) -> None:
        """OLD stays fully searchable while NEW is built side by side (no mix)."""
        space = await _make_space(async_session, serving=OLD_MODEL)
        doc = await _make_ready_doc(async_session, space.id, OLD_MODEL)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=OLD_MODEL, seed=0.1)
        # NEW generation built alongside (a reprocess under the pin).
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=NEW_MODEL, seed=0.2)

        chunk_repo = RAGChunkRepository(async_session)
        dims = await _dims(async_session)
        query = [0.1] * dims

        old_hits = await chunk_repo.search_by_similarity(
            user_id=None, space_ids=[space.id], query_embedding=query, embedding_model=OLD_MODEL
        )
        new_hits = await chunk_repo.search_by_similarity(
            user_id=None, space_ids=[space.id], query_embedding=query, embedding_model=NEW_MODEL
        )
        all_hits = await chunk_repo.search_by_similarity(
            user_id=None, space_ids=[space.id], query_embedding=query, embedding_model=None
        )

        assert {c.embedding_model for c, _ in old_hits} == {OLD_MODEL}
        assert {c.embedding_model for c, _ in new_hits} == {NEW_MODEL}
        # Unfiltered sees both — proving the filter is what isolates a generation.
        assert {c.embedding_model for c, _ in all_hits} == {OLD_MODEL, NEW_MODEL}

    async def test_corpus_is_generation_scoped(self, async_session: AsyncSession) -> None:
        """The BM25 corpus honours the generation filter."""
        space = await _make_space(async_session, serving=OLD_MODEL)
        doc = await _make_ready_doc(async_session, space.id, OLD_MODEL)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=OLD_MODEL, seed=0.1)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=NEW_MODEL, seed=0.2)

        chunk_repo = RAGChunkRepository(async_session)
        old_corpus = await chunk_repo.get_corpus_for_spaces(
            None, [space.id], embedding_model=OLD_MODEL
        )
        assert [text for _, text in old_corpus] == [f"content-{OLD_MODEL}"]


class TestFlip:
    async def test_flip_completed_space_switches_and_reclaims(
        self, async_session: AsyncSession
    ) -> None:
        """A fully-rebuilt space flips atomically: pointer cleared, OLD chunks gone."""
        space = await _make_space(async_session, serving=OLD_MODEL)
        doc = await _make_ready_doc(async_session, space.id, NEW_MODEL)  # rebuilt onto NEW
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=OLD_MODEL, seed=0.1)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=NEW_MODEL, seed=0.2)
        await async_session.commit()

        with patch.object(reindex, "get_db_context", lambda: _session_ctx(async_session)):
            await reindex._flip_completed_spaces(OLD_MODEL, NEW_MODEL)

        space_repo = RAGSpaceRepository(async_session)
        chunk_repo = RAGChunkRepository(async_session)
        await async_session.refresh(space)
        assert await space_repo.get_serving_model(space.id) is None  # back to single generation
        assert await chunk_repo.count_by_space_and_model(space.id, OLD_MODEL) == 0  # reclaimed
        assert await chunk_repo.count_by_space_and_model(space.id, NEW_MODEL) == 1  # served

    async def test_flip_deferred_when_document_incomplete(
        self, async_session: AsyncSession
    ) -> None:
        """A space with a document still on OLD keeps serving OLD (keep N on failure)."""
        space = await _make_space(async_session, serving=OLD_MODEL)
        # Document NOT rebuilt: still stamped OLD, only OLD chunks.
        doc = await _make_ready_doc(async_session, space.id, OLD_MODEL)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=OLD_MODEL, seed=0.1)
        await async_session.commit()

        with patch.object(reindex, "get_db_context", lambda: _session_ctx(async_session)):
            await reindex._flip_completed_spaces(OLD_MODEL, NEW_MODEL)

        space_repo = RAGSpaceRepository(async_session)
        chunk_repo = RAGChunkRepository(async_session)
        assert await space_repo.get_serving_model(space.id) == OLD_MODEL  # still pinned
        assert await chunk_repo.count_by_space_and_model(space.id, OLD_MODEL) == 1  # intact

    async def test_reaper_flip_resumes_after_crash(self, async_session: AsyncSession) -> None:
        """flip_pinned_spaces_if_ready activates a space rebuilt to the current model.

        Simulates crash-resume: the interrupted drain never flipped, the reaper
        rebuilt the document onto the current settings model, and the periodic
        pass now performs the atomic flip using each pin's serving pointer as the
        OLD generation and the current model as the target.
        """
        from src.core.config import settings

        target = settings.rag_spaces_embedding_model
        space = await _make_space(async_session, serving=OLD_MODEL)
        doc = await _make_ready_doc(async_session, space.id, target)  # rebuilt to current model
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=OLD_MODEL, seed=0.1)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=target, seed=0.2)
        await async_session.commit()

        with patch.object(reindex, "get_db_context", lambda: _session_ctx(async_session)):
            await reindex.flip_pinned_spaces_if_ready()

        space_repo = RAGSpaceRepository(async_session)
        chunk_repo = RAGChunkRepository(async_session)
        assert await space_repo.get_serving_model(space.id) is None
        assert await chunk_repo.count_by_space_and_model(space.id, OLD_MODEL) == 0
        assert await chunk_repo.count_by_space_and_model(space.id, target) == 1


class TestRepositoryPrimitives:
    async def test_pin_only_pins_unpinned_spaces(self, async_session: AsyncSession) -> None:
        """pin_serving_for_spaces never clobbers an already-pinned space."""
        fresh = await _make_space(async_session, serving=None)
        already = await _make_space(async_session, serving="some-other-gen")
        await async_session.flush()

        space_repo = RAGSpaceRepository(async_session)
        pinned = await space_repo.pin_serving_for_spaces([fresh.id, already.id], OLD_MODEL)

        assert pinned == 1  # only the unpinned one
        assert await space_repo.get_serving_model(fresh.id) == OLD_MODEL
        assert await space_repo.get_serving_model(already.id) == "some-other-gen"

    async def test_count_docs_not_on_generation(self, async_session: AsyncSession) -> None:
        """Completion signal: 0 only when every doc is READY on the target model."""
        space = await _make_space(async_session)
        await _make_ready_doc(async_session, space.id, NEW_MODEL)
        stale = await _make_ready_doc(async_session, space.id, OLD_MODEL)
        await async_session.flush()

        doc_repo = RAGDocumentRepository(async_session)
        assert await doc_repo.count_space_docs_not_on_generation(space.id, NEW_MODEL) == 1

        # Once the stale doc is rebuilt onto the target model, the space is complete.
        stale.embedding_model = NEW_MODEL
        await async_session.flush()
        assert await doc_repo.count_space_docs_not_on_generation(space.id, NEW_MODEL) == 0

    async def test_delete_by_document_and_model_keeps_other_generation(
        self, async_session: AsyncSession
    ) -> None:
        """The idempotent target-only delete never touches the served generation."""
        space = await _make_space(async_session, serving=OLD_MODEL)
        doc = await _make_ready_doc(async_session, space.id, OLD_MODEL)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=OLD_MODEL, seed=0.1)
        await _add_chunk(async_session, doc=doc, space_id=space.id, model=NEW_MODEL, seed=0.2)

        chunk_repo = RAGChunkRepository(async_session)
        deleted = await chunk_repo.delete_by_document_and_model(doc.id, NEW_MODEL)
        await async_session.flush()

        assert deleted == 1
        assert await chunk_repo.count_by_space_and_model(space.id, OLD_MODEL) == 1  # served, intact
        assert await chunk_repo.count_by_space_and_model(space.id, NEW_MODEL) == 0  # cleared
