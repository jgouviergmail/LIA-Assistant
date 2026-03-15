"""
RAG Spaces reindexation service.

Handles full reindexation of all RAG documents when the admin changes
the embedding model. Uses Redis for progress tracking and mutual exclusion.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces.embedding import reset_rag_embeddings
from src.domains.rag_spaces.models import RAGDocument
from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.repository import RAGChunkRepository, RAGDocumentRepository
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_documents_total_count,
    rag_reindex_documents_total,
    rag_reindex_runs_total,
)

logger = get_logger(__name__)

# Redis keys
REINDEX_FLAG_KEY = "rag_reindex_in_progress"
REINDEX_STATUS_KEY = "rag_reindex_status"
REINDEX_TTL_SECONDS = 3600 * 6  # 6 hour TTL safety net


async def _get_redis():  # type: ignore[no-untyped-def]
    """Get Redis client (returns None if unavailable)."""
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        return await get_redis_cache()
    except Exception as e:
        logger.debug("rag_redis_unavailable", error=str(e))
        return None


async def _alter_vector_dimensions_if_needed(db: AsyncSession, new_dims: int) -> None:
    """ALTER the rag_chunks embedding column and recreate HNSW index if dimensions changed."""
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

    # ALTER column type (new_dims is validated by Pydantic: 256 <= int <= 4096)
    if not isinstance(new_dims, int) or not (256 <= new_dims <= 4096):
        raise ValueError(f"Invalid embedding dimensions: {new_dims}")
    await db.execute(text(f"ALTER TABLE rag_chunks ALTER COLUMN embedding TYPE vector({new_dims})"))

    # Drop and recreate HNSW index
    await db.execute(text("DROP INDEX IF EXISTS ix_rag_chunks_embedding"))
    await db.execute(
        text(
            "CREATE INDEX ix_rag_chunks_embedding ON rag_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    )

    await db.commit()
    logger.info("rag_reindex_vector_dimensions_altered", new_dims=new_dims)


async def start_reindexation(db: AsyncSession) -> dict:
    """
    Start full reindexation of all RAG documents.

    1. Check no reindex already in progress
    2. Set Redis flag
    3. Delete all existing chunks
    4. Reset embedding singleton
    5. Launch background re-processing for each document

    Returns summary dict for API response.
    """
    redis = await _get_redis()

    # Check if already in progress (atomic SET-if-Not-eXists to prevent race condition)
    if redis:
        acquired = await redis.set(REINDEX_FLAG_KEY, "1", ex=REINDEX_TTL_SECONDS, nx=True)
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
    if redis:
        status_data = {
            "in_progress": True,
            "started_at": datetime.now(UTC).isoformat(),
            "model_from": model_from,
            "model_to": model_to,
            "total_documents": total_docs,
            "processed_documents": 0,
            "failed_documents": 0,
        }
        await redis.set(REINDEX_STATUS_KEY, json.dumps(status_data), ex=REINDEX_TTL_SECONDS)

    # Reset embedding singleton to pick up new model
    reset_rag_embeddings()

    # Handle dimension change: ALTER vector column + recreate HNSW index
    # Wrapped in try/except to release Redis flag on failure
    new_dims = settings.rag_spaces_embedding_dimensions
    try:
        await _alter_vector_dimensions_if_needed(db, new_dims)
    except Exception as e:
        logger.error("rag_reindex_alter_dimensions_failed", error=str(e), exc_info=True)
        rag_reindex_runs_total.labels(status="failed").inc()
        if redis:
            await redis.delete(REINDEX_FLAG_KEY)
            await redis.delete(REINDEX_STATUS_KEY)
        raise

    logger.info(
        "rag_reindexation_started",
        total_documents=total_docs,
        model_from=model_from,
        model_to=model_to,
        dimensions=new_dims,
    )

    rag_reindex_runs_total.labels(status="started").inc()

    # Launch background reindexation
    safe_fire_and_forget(
        _reindex_all_documents(documents, model_to),
        name="rag_reindex_all",
    )

    return {
        "message": f"Reindexation started for {total_docs} documents",
        "total_documents": total_docs,
        "model_from": model_from,
        "model_to": model_to,
    }


async def _reindex_all_documents(documents: list[RAGDocument], model_to: str) -> None:
    """Background task: reindex all documents sequentially."""
    from src.domains.rag_spaces.models import RAGDocumentStatus
    from src.infrastructure.database.session import get_db_context

    redis = await _get_redis()
    processed = 0
    failed = 0

    for document in documents:
        try:
            # Delete existing chunks for this document
            async with get_db_context() as db:
                chunk_repo = RAGChunkRepository(db)
                await chunk_repo.delete_by_document(document.id)

                # Mark as reindexing
                doc_repo = RAGDocumentRepository(db)
                doc = await doc_repo.get_by_id(document.id)
                if doc:
                    old_status = doc.status
                    await doc_repo.update(doc, {"status": RAGDocumentStatus.REINDEXING})
                    rag_documents_total_count.labels(status=old_status).dec()
                    rag_documents_total_count.labels(status="reindexing").inc()
                await db.commit()

            # Re-process the document
            await process_document(
                document_id=document.id,
                space_id=document.space_id,
                user_id=document.user_id,
                filename=document.filename,
                original_filename=document.original_filename,
                content_type=document.content_type,
            )
            processed += 1
            rag_reindex_documents_total.labels(status="success").inc()

        except Exception as e:
            failed += 1
            rag_reindex_documents_total.labels(status="error").inc()
            logger.error(
                "rag_reindex_document_failed",
                document_id=str(document.id),
                error=str(e),
            )

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
                        ex=REINDEX_TTL_SECONDS,
                    )
            except Exception as exc:
                logger.warning("rag_reindex_progress_update_failed", error=str(exc))

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
                await redis.set(REINDEX_STATUS_KEY, json.dumps(data), ex=3600)
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
