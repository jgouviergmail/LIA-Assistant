"""
RAG Spaces reindexation service.

Handles full reindexation of all RAG documents when the admin changes the
embedding model. The durable job state lives in PostgreSQL (audit F001): the
destructive dimension-change DDL (chunk purge + column ALTER, when needed) and
the ``READY``/``ERROR`` → ``PENDING`` requeue are persisted in **one atomic
commit** (``_persist_reindex_intent``, audit V8) *before* any processing
starts — a crash can therefore leave either the old index fully intact or
durably-recorded work, never destroyed chunks without a recovery trail. The
PENDING documents are then drained through the same claim/lease/heartbeat
pipeline as uploads; whatever the in-process drain does not finish, the
regular document reaper resumes — no reindex-specific recovery machinery.
Each document's chunk swap is atomic inside ``process_document`` (old chunks
deleted and new ones inserted in one transaction), so retrieval never observes
a half-reindexed document. Redis carries the single-flight flag and the
progress snapshot only — it is a cache, never the source of truth.

Deliberate boundary (documented in ADR/RAG docs): an embedding-DIMENSION
change still drops all chunks up front (`_alter_vector_dimensions_if_needed`)
— a pgvector column has a fixed dimensionality, so old and new generations
cannot coexist in one column. That path is destructive but fully resumable:
chunks are regenerable from the stored documents, and every document is
already durably PENDING when the deletion happens. A true side-by-side
generation for dimension changes would require a parallel column/table and a
retrieval switch, and is out of scope here.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces.embedding import reset_rag_embeddings
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentStatus
from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
    RAGSpaceRepository,
)
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_documents_total_count,
    rag_reindex_documents_total,
    rag_reindex_runs_total,
    rag_reindex_space_flips_total,
)

logger = get_logger(__name__)

# Redis keys
REINDEX_FLAG_KEY = "rag_reindex_in_progress"
REINDEX_STATUS_KEY = "rag_reindex_status"
# Final-status retention after completion (informational, not a lock).
REINDEX_FINAL_STATUS_TTL_SECONDS = 3600
# Lock TTL is settings-driven (settings.rag_reindex_lock_ttl_seconds) and
# RENEWED after each document — see the heartbeat in _reindex_all_documents (F001).


async def _get_redis():  # type: ignore[no-untyped-def]
    """Get Redis client (returns None if unavailable)."""
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        return await get_redis_cache()
    except Exception as e:
        logger.debug("rag_redis_unavailable", error=str(e))
        return None


async def _alter_vector_dimensions_if_needed(db: AsyncSession, new_dims: int) -> None:
    """ALTER the rag_chunks embedding column and recreate HNSW index if dimensions changed.

    Runs entirely in the CALLER's transaction and never commits (audit F001,
    V8): the destructive DELETE/ALTER must land in the same commit as the
    durable READY/ERROR → PENDING requeue, otherwise a crash between the two
    leaves READY documents without chunks that no reaper can see. PostgreSQL
    DDL is transactional, so the whole reset rolls back cleanly on failure.
    """
    # Check current column dimensions from pg_attribute
    result = await db.execute(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'rag_chunks'::regclass AND attname = 'embedding'"
        )
    )
    row = result.scalar_one_or_none()
    current_dims = row if row and row > 0 else None

    if current_dims and current_dims == new_dims:
        return  # No change needed

    logger.info(
        "rag_reindex_altering_vector_dimensions",
        current_dims=current_dims,
        new_dims=new_dims,
    )

    # Delete all chunks (they'll be re-embedded with new dimensions)
    await db.execute(text("DELETE FROM rag_chunks"))

    # ALTER column type — DDL statements don't support bind parameters for type modifiers,
    # so we use strict whitelist validation before string formatting (defense in depth).
    if not isinstance(new_dims, int) or not (256 <= new_dims <= 4096):
        raise ValueError(f"Invalid embedding dimensions: {new_dims}")
    safe_dims = int(new_dims)  # Re-cast to guarantee pure int (no subclass override)
    await db.execute(
        text(f"ALTER TABLE rag_chunks ALTER COLUMN embedding TYPE vector({safe_dims})")
    )

    # Drop and recreate HNSW index
    await db.execute(text("DROP INDEX IF EXISTS ix_rag_chunks_embedding"))
    await db.execute(
        text(
            "CREATE INDEX ix_rag_chunks_embedding ON rag_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    )

    # NO commit here — the caller commits together with the durable requeue.
    logger.info("rag_reindex_vector_dimensions_altered", new_dims=new_dims)


async def _current_vector_dims(db: AsyncSession) -> int | None:
    """Read the rag_chunks.embedding column dimensionality (None if unknown)."""
    result = await db.execute(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'rag_chunks'::regclass AND attname = 'embedding'"
        )
    )
    row = result.scalar_one_or_none()
    return row if row and row > 0 else None


async def _write_initial_reindex_status(
    redis: object | None, model_from: str | None, model_to: str, total_docs: int
) -> None:
    """Publish the initial reindex status snapshot to Redis (informational cache)."""
    if redis is None:
        return
    status_data = {
        "in_progress": True,
        "started_at": datetime.now(UTC).isoformat(),
        "model_from": model_from,
        "model_to": model_to,
        "total_documents": total_docs,
        "processed_documents": 0,
        "failed_documents": 0,
    }
    await redis.set(  # type: ignore[attr-defined]
        REINDEX_STATUS_KEY,
        json.dumps(status_data),
        ex=settings.rag_reindex_lock_ttl_seconds,
    )


async def _plan_generational_continuity(
    db: AsyncSession,
    documents: list[RAGDocument],
    model_from: str | None,
    model_to: str,
    new_dims: int,
) -> tuple[list[UUID] | None, str | None]:
    """Decide whether this is a same-dimension generational reindex (AC-001).

    Continuity requires a REAL model change with UNCHANGED vector dimensions: a
    dimension change cannot keep both generations in one pgvector column and
    stays on the destructive rebuild path; a no-op re-run (model unchanged) is
    not a generational split. Returns ``(pin_space_ids, flip_from)`` — the
    distinct spaces to pin to the OLD generation and the OLD model to flip from,
    or ``(None, None)`` when there is no continuity.
    """
    current_dims = await _current_vector_dims(db)
    continuity = (
        model_from is not None
        and model_from != model_to
        and current_dims is not None
        and current_dims == new_dims
    )
    if not continuity:
        return None, None
    return sorted({doc.space_id for doc in documents}), model_from


async def _persist_reindex_intent(
    db: AsyncSession,
    document_ids: list[UUID],
    new_dims: int,
    pin_space_ids: list[UUID] | None = None,
    pin_model: str | None = None,
) -> int:
    """Atomically persist the reindex intent: destructive reset + durable requeue.

    ONE transaction, ONE commit (audit F001, V8): the dimension-change DDL
    (chunk purge + column ALTER + index rebuild — a no-op when dimensions are
    unchanged), the READY/ERROR → PENDING requeue AND, for a same-dimension
    generational reindex (AC-001), the per-space ``serving_embedding_model`` pin
    land together. Crash before the commit → full rollback, the old index stays
    intact and servable. Crash after → the chunks are gone (dimension change) or
    fully served under the pinned OLD generation (same dimension), and every
    target document is durably PENDING, so the drain loop and — after any
    restart — the document reaper rebuild the index through the standard claim
    pipeline. There is no intermediate state in which chunks are lost without
    recorded work, nor a window where the served generation is deleted before
    its replacement is ready.

    Returns the number of requeued documents.
    """
    try:
        await _alter_vector_dimensions_if_needed(db, new_dims)
        if pin_space_ids and pin_model:
            pinned = await RAGSpaceRepository(db).pin_serving_for_spaces(pin_space_ids, pin_model)
            logger.info("rag_reindex_spaces_pinned", pinned=pinned, serving_model=pin_model)
        requeued = await RAGJobsRepository(db).requeue_documents_for_reindex(document_ids)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return requeued


async def _flip_one_space_if_ready(
    db: AsyncSession,
    space_id: UUID,
    model_from: str,
    model_to: str,
) -> bool:
    """Flip ONE pinned space to the new generation if its rebuild finished.

    A space whose documents are all READY on ``model_to`` is flipped in ONE
    transaction — clear the serving pin (back to a single generation) AND delete
    the old-generation chunks together, so a concurrent reader sees either the
    OLD generation (fully served) or the NEW one, never a mix or an empty window.
    A space with a still-unfinished or failed document is left pinned on the
    stable OLD generation ("keep N on failure"). Returns True iff it flipped.
    """
    space_repo = RAGSpaceRepository(db)
    doc_repo = RAGDocumentRepository(db)
    chunk_repo = RAGChunkRepository(db)
    remaining = await doc_repo.count_space_docs_not_on_generation(space_id, model_to)
    if remaining > 0:
        rag_reindex_space_flips_total.labels(outcome="deferred").inc()
        logger.info(
            "rag_reindex_space_flip_deferred",
            space_id=str(space_id),
            remaining_documents=remaining,
        )
        return False
    try:
        await space_repo.set_serving_model(space_id, None)
        deleted = await chunk_repo.delete_by_space_and_model(space_id, model_from)
        await db.commit()
        rag_reindex_space_flips_total.labels(outcome="flipped").inc()
        logger.info(
            "rag_reindex_space_flipped",
            space_id=str(space_id),
            model_from=model_from,
            model_to=model_to,
            old_chunks_deleted=deleted,
        )
        return True
    except Exception as exc:
        await db.rollback()
        rag_reindex_space_flips_total.labels(outcome="failed").inc()
        logger.error(
            "rag_reindex_space_flip_failed",
            space_id=str(space_id),
            error=str(exc),
            exc_info=True,
        )
        return False


async def _flip_completed_spaces(model_from: str, model_to: str) -> None:
    """Flip every fully-rebuilt space pinned to ``model_from`` (end-of-drain pass).

    Per-space commit so one laggard never blocks the others; a deferred space is
    picked up later by the reaper's ``flip_pinned_spaces_if_ready`` pass.
    """
    async with get_db_context() as db:
        pinned = await RAGSpaceRepository(db).get_pinned_space_ids()
        for space_id, serving in pinned:
            if serving == model_from:
                await _flip_one_space_if_ready(db, space_id, model_from, model_to)


async def flip_pinned_spaces_if_ready() -> None:
    """Crash-resume flip pass (AC-001): activate any pinned space now fully rebuilt.

    Called every RAG reaper tick. After a crash the reaper rebuilds the requeued
    documents onto the current model while the space stays pinned on (and serving)
    the OLD generation; once every document is on the current model this pass
    performs the atomic flip the interrupted drain never reached. Idempotent —
    a space whose serving pointer already equals the current model has nothing to
    flip. The current settings model is the target generation for every pin.
    """
    target = settings.rag_spaces_embedding_model
    async with get_db_context() as db:
        pinned = await RAGSpaceRepository(db).get_pinned_space_ids()
        for space_id, serving in pinned:
            if serving == target:
                continue
            await _flip_one_space_if_ready(db, space_id, serving, target)


async def start_reindexation(db: AsyncSession, *, run_in_background: bool = True) -> dict:
    """
    Start full reindexation of all RAG documents.

    1. Check no reindex already in progress (Redis single-flight flag)
    2. Set Redis status snapshot
    3. Reset embedding singleton
    4. Persist the reindex intent ATOMICALLY (audit F001/V8): dimension-change
       DDL (if any) + READY/ERROR → PENDING requeue in one commit — the
       persistent job state; the reaper resumes any remainder after a crash
    5. Drain the PENDING documents through the claim pipeline

    Args:
        db: Async session used for the setup queries (document listing and
            vector-column DDL). Per-document work opens its own sessions.
        run_in_background: When True (HTTP callers), launch the re-processing as
            a detached fire-and-forget task and return immediately. When False
            (CLI/ops runners), await it to completion so the process stays alive
            until every document is re-embedded.

    Returns:
        Summary dict for the API response.
    """
    redis = await _get_redis()

    # Check if already in progress (atomic SET-if-Not-eXists to prevent race condition)
    if redis:
        acquired = await redis.set(
            REINDEX_FLAG_KEY, "1", ex=settings.rag_reindex_lock_ttl_seconds, nx=True
        )
        if not acquired:
            return {
                "message": "Reindexation already in progress",
                "total_documents": 0,
                "model_from": None,
                "model_to": settings.rag_spaces_embedding_model,
            }

    doc_repo = RAGDocumentRepository(db)

    # Get all documents to reindex
    documents = await doc_repo.get_all_for_reindex()
    total_docs = len(documents)

    if total_docs == 0:
        # No documents — release Redis flag immediately
        if redis:
            await redis.delete(REINDEX_FLAG_KEY)
        return {
            "message": "No documents to reindex",
            "total_documents": 0,
            "model_from": None,
            "model_to": settings.rag_spaces_embedding_model,
        }

    # Detect current model from first document
    model_from = documents[0].embedding_model if documents else None
    model_to = settings.rag_spaces_embedding_model

    # Set Redis status (flag already acquired atomically above)
    await _write_initial_reindex_status(redis, model_from, model_to, total_docs)

    # AC-001 generational continuity: a SAME-dimension model change keeps the OLD
    # generation fully readable while the NEW one is built side by side, pinning
    # every affected space to the OLD model inside the atomic intent commit. A
    # dimension change stays on the destructive rebuild path (documented
    # maintenance window); a no-op re-run is not a generational split.
    new_dims = settings.rag_spaces_embedding_dimensions
    pin_space_ids, flip_from = await _plan_generational_continuity(
        db, documents, model_from, model_to, new_dims
    )

    # Reset embedding singleton to pick up new model
    reset_rag_embeddings()

    # Persist the reindex intent atomically (audit F001, V8): the destructive
    # dimension-change DDL (if any), the READY/ERROR → PENDING requeue AND the
    # per-space serving pin (continuity) land in ONE commit — a crash at any
    # point leaves either the old index fully intact/served or durably-recorded
    # work the reaper resumes. Never both destroyed chunks and unrecorded work.
    try:
        previous_statuses = [doc.status for doc in documents]
        requeued = await _persist_reindex_intent(
            db,
            [doc.id for doc in documents],
            new_dims,
            pin_space_ids=pin_space_ids,
            pin_model=flip_from,
        )
        # Best-effort gauge transitions for the requeued rows (the per-document
        # completion transitions are handled inside process_document).
        for previous_status in previous_statuses:
            rag_documents_total_count.labels(status=previous_status).dec()
            rag_documents_total_count.labels(status=RAGDocumentStatus.PENDING).inc()
    except Exception as e:
        logger.error("rag_reindex_setup_failed", error=str(e), exc_info=True)
        rag_reindex_runs_total.labels(status="failed").inc()
        if redis:
            await redis.delete(REINDEX_FLAG_KEY)
            await redis.delete(REINDEX_STATUS_KEY)
        raise

    logger.info(
        "rag_reindexation_started",
        total_documents=total_docs,
        requeued=requeued,
        model_from=model_from,
        model_to=model_to,
        dimensions=new_dims,
        generational_continuity=flip_from is not None,
    )

    rag_reindex_runs_total.labels(status="started").inc()

    # Launch reindexation: detached for HTTP callers, awaited inline for CLI/ops
    # runners so the invoking process does not exit and kill the work mid-flight.
    if run_in_background:
        safe_fire_and_forget(
            _reindex_all_documents(documents, model_to, flip_from),
            name="rag_reindex_all",
        )
    else:
        await _reindex_all_documents(documents, model_to, flip_from)

    return {
        "message": f"Reindexation started for {total_docs} documents",
        "total_documents": total_docs,
        "model_from": model_from,
        "model_to": model_to,
    }


async def _renew_reindex_lock(redis: object | None) -> None:
    """Extend the reindex lock heartbeat by one TTL window (F001, best-effort).

    Called after each processed document: a live reindex keeps the lock while a
    hard crash lets it expire within one window. Failures are non-fatal.
    """
    if redis is None:
        return
    try:
        await redis.expire(REINDEX_FLAG_KEY, settings.rag_reindex_lock_ttl_seconds)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - renewal is best-effort
        logger.warning("rag_reindex_lock_renew_failed", error=str(exc))


async def _reprocess_one_document(document: RAGDocument) -> bool:
    """Re-embed one durably-requeued (PENDING) document through the claim pipeline.

    ``process_document`` claims the row (PENDING → PROCESSING + lease), embeds,
    and swaps the chunks atomically — the old chunks survive until the new ones
    are committed in the same transaction, so a crash mid-embed degrades
    nothing (the pre-durable flow deleted the chunks *before* re-embedding,
    leaving a chunkless document on crash — audit F001).

    Returns True only when process_document reached READY. A False also covers
    a lost claim: the document reaper may legitimately drain a requeued row
    before this loop reaches it (claim exclusivity keeps that safe) — the row
    still converges to READY, only this run's progress counter misses it.
    Errors are isolated so one failing document never aborts the whole reindex.
    """
    try:
        assert document.user_id is not None  # guaranteed by query filter
        return await process_document(
            document_id=document.id,
            space_id=document.space_id,
            user_id=document.user_id,
            filename=document.filename,
            original_filename=document.original_filename,
            content_type=document.content_type,
        )
    except Exception as e:
        logger.error("rag_reindex_document_failed", document_id=str(document.id), error=str(e))
        return False


async def _reindex_all_documents(
    documents: list[RAGDocument], model_to: str, flip_from: str | None = None
) -> None:
    """Background task: reindex all documents sequentially.

    When ``flip_from`` is set (AC-001 same-dimension continuity), each document
    is rebuilt with the NEW model alongside the still-served OLD generation
    (``process_document`` honours the space's serving pin), and once the drain
    finishes every fully-rebuilt space is flipped atomically to the new
    generation with its old chunks reclaimed.
    """
    redis = await _get_redis()
    processed = 0
    failed = 0

    for document in documents:
        if await _reprocess_one_document(document):
            processed += 1
            rag_reindex_documents_total.labels(status="success").inc()
        else:
            failed += 1
            rag_reindex_documents_total.labels(status="error").inc()

        # Renew the lock heartbeat (F001): each processed document extends the
        # flag's TTL, so a live reindex holds the lock while it makes progress,
        # while a hard crash frees it within one TTL window (not 6h).
        await _renew_reindex_lock(redis)

        # Update Redis progress
        if redis:
            try:
                status_data = await redis.get(REINDEX_STATUS_KEY)
                if status_data:
                    data = json.loads(status_data)
                    data["processed_documents"] = processed
                    data["failed_documents"] = failed
                    await redis.set(
                        REINDEX_STATUS_KEY,
                        json.dumps(data),
                        ex=settings.rag_reindex_lock_ttl_seconds,
                    )
            except Exception as exc:
                logger.warning("rag_reindex_progress_update_failed", error=str(exc))

    # AC-001: flip every fully-rebuilt space to the new generation (atomic per
    # space) and reclaim the old chunks. Spaces with a still-failed document stay
    # pinned on the stable OLD generation; the periodic RAG reaper reruns the
    # flip once it finishes them. Never raises into the drain result.
    if flip_from is not None:
        try:
            await _flip_completed_spaces(flip_from, model_to)
        except Exception as exc:
            logger.error("rag_reindex_flip_pass_failed", error=str(exc), exc_info=True)

    # Clear flag
    if redis:
        await redis.delete(REINDEX_FLAG_KEY)
        # Update final status (keep for 1 hour after completion)
        try:
            status_data = await redis.get(REINDEX_STATUS_KEY)
            if status_data:
                data = json.loads(status_data)
                data["in_progress"] = False
                data["processed_documents"] = processed
                data["failed_documents"] = failed
                await redis.set(
                    REINDEX_STATUS_KEY,
                    json.dumps(data),
                    ex=REINDEX_FINAL_STATUS_TTL_SECONDS,
                )
        except Exception as exc:
            logger.warning("rag_reindex_final_status_update_failed", error=str(exc))

    rag_reindex_runs_total.labels(status="completed" if failed == 0 else "failed").inc()

    logger.info(
        "rag_reindexation_complete",
        processed=processed,
        failed=failed,
        total=len(documents),
    )


async def get_reindex_status() -> dict[str, Any]:
    """Get current reindexation status from Redis."""
    redis = await _get_redis()
    if not redis:
        return {"in_progress": False}

    try:
        status_data = await redis.get(REINDEX_STATUS_KEY)
        if status_data:
            result: dict[str, Any] = json.loads(status_data)
            return result
    except Exception as e:
        logger.warning("rag_reindex_status_read_failed", error=str(e))

    return {"in_progress": False}
