"""
RAG Spaces repositories.

Provides data access for RAG spaces, documents, and vector chunks.
Inherits from BaseRepository for standard CRUD operations.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from uuid import UUID

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDocumentStatus,
    RAGDriveSource,
    RAGMailSource,
    RAGSpace,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class RAGSpaceRepository(BaseRepository[RAGSpace]):
    """Repository for RAG Space model with user-scoped queries.

    Note: RAGSpace.is_active is a business toggle (not soft-delete), so we
    override get_by_id to always include inactive spaces. Use
    get_active_for_user() when only active spaces are needed.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, RAGSpace)

    async def get_by_id(self, id: UUID, include_inactive: bool = True) -> RAGSpace | None:
        """Get space by ID, including inactive spaces by default."""
        return await super().get_by_id(id, include_inactive=include_inactive)

    async def get_all(
        self,
        include_inactive: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RAGSpace]:
        """Get all spaces, including inactive by default (is_active is a business toggle)."""
        return await super().get_all(include_inactive=include_inactive, limit=limit, offset=offset)

    async def count(self, include_inactive: bool = True) -> int:
        """Count all spaces, including inactive by default."""
        return await super().count(include_inactive=include_inactive)

    async def get_all_for_user(self, user_id: UUID) -> list[RAGSpace]:
        """Get all spaces for a user, ordered by creation date."""
        stmt = (
            select(RAGSpace).where(RAGSpace.user_id == user_id).order_by(RAGSpace.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        """Count total spaces for a user."""
        stmt = select(func.count(RAGSpace.id)).where(RAGSpace.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_active_for_user(self, user_id: UUID) -> list[RAGSpace]:
        """Get all active spaces for a user."""
        stmt = (
            select(RAGSpace)
            .where(RAGSpace.user_id == user_id, RAGSpace.is_active.is_(True))
            .order_by(RAGSpace.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_space_ids_for_user(self, user_id: UUID) -> list[UUID]:
        """Get IDs of all active spaces for a user (lightweight query)."""
        stmt = select(RAGSpace.id).where(RAGSpace.user_id == user_id, RAGSpace.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name_for_user(self, user_id: UUID, name: str) -> RAGSpace | None:
        """Get a space by name for a user (unique constraint check)."""
        stmt = select(RAGSpace).where(
            RAGSpace.user_id == user_id,
            RAGSpace.name == name,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_kind_for_user(self, user_id: UUID, kind: str) -> RAGSpace | None:
        """The space another domain manages by ROLE (``kind``), whatever its name (ADR-258)."""
        stmt = select(RAGSpace).where(RAGSpace.user_id == user_id, RAGSpace.kind == kind)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # System Spaces
    # ========================================================================

    async def get_system_spaces(self) -> list[RAGSpace]:
        """Get all system spaces, ordered by name."""
        stmt = select(RAGSpace).where(RAGSpace.is_system.is_(True)).order_by(RAGSpace.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_system_spaces(self) -> list[RAGSpace]:
        """Get all active system spaces."""
        stmt = (
            select(RAGSpace)
            .where(RAGSpace.is_system.is_(True), RAGSpace.is_active.is_(True))
            .order_by(RAGSpace.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_system_space_by_name(self, name: str) -> RAGSpace | None:
        """Get a system space by name."""
        stmt = select(RAGSpace).where(
            RAGSpace.is_system.is_(True),
            RAGSpace.name == name,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def claim_system_space_for_reindex(self, space_id: UUID) -> RAGSpace | None:
        """Take the exclusive right to re-index a system space, or decline.

        ``FOR UPDATE SKIP LOCKED`` on the space row makes the re-indexation
        single-writer without a distributed lock, and without any waiting: the
        first caller holds the row until it commits, every concurrent caller gets
        None immediately and returns "skipped". Production ran four uvicorn
        workers that each executed the whole startup indexation because the
        staleness check was a read with no claim — 269 chunks were embedded and
        inserted four times, and the surviving rows piled up (measured
        2026-07-27: 807 chunks for 269 distinct contents).

        ``populate_existing`` is what makes this correct rather than merely
        exclusive: the caller has already read this row, so without it SQLAlchemy
        would hand back the identity-mapped instance and its *stale*
        ``content_hash``, and a loser of the race would re-index over the
        winner's fresh work.

        Args:
            space_id: System space to claim.

        Returns:
            The locked space with freshly loaded columns, or None when another
            transaction holds it.
        """
        stmt = (
            select(RAGSpace)
            .where(RAGSpace.id == space_id, RAGSpace.is_system.is_(True))
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # Generational continuity (AC-001)
    # ========================================================================

    async def get_serving_model(self, space_id: UUID) -> str | None:
        """Return a space's served embedding generation (NULL in steady state).

        Lightweight scalar read used by ``process_document`` to decide whether a
        reprocess must keep the stable generation side by side (reindex) or
        replace every chunk (normal upload).
        """
        stmt = select(RAGSpace.serving_embedding_model).where(RAGSpace.id == space_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def pin_serving_for_spaces(self, space_ids: list[UUID], model: str) -> int:
        """Pin ``serving_embedding_model`` for the given spaces (reindex start).

        Only pins spaces that are NOT already pinned to some generation, so a
        crash/restart mid-reindex re-run never clobbers an in-flight pin. Runs in
        the CALLER's transaction (committed with the reindex-intent setup).
        Returns the number of rows pinned.
        """
        if not space_ids:
            return 0
        stmt = (
            update(RAGSpace)
            .where(
                RAGSpace.id.in_(space_ids),
                RAGSpace.serving_embedding_model.is_(None),
            )
            .values(serving_embedding_model=model)
        )
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def set_serving_model(self, space_id: UUID, model: str | None) -> None:
        """Set (or clear, with None) a single space's served generation.

        Used by the atomic per-space flip: the caller sets the NEW generation and
        deletes the OLD chunks in the SAME transaction.
        """
        stmt = update(RAGSpace).where(RAGSpace.id == space_id).values(serving_embedding_model=model)
        await self.db.execute(stmt)

    async def get_pinned_space_ids(self) -> list[tuple[UUID, str]]:
        """Return ``(space_id, serving_model)`` for every currently-pinned space.

        Drives the post-build flip pass and lets a restart resume flipping spaces
        pinned by an earlier reindex run.
        """
        stmt = select(RAGSpace.id, RAGSpace.serving_embedding_model).where(
            RAGSpace.serving_embedding_model.is_not(None)
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]


class RAGDriveSourceRepository(BaseRepository[RAGDriveSource]):
    """Repository for RAG Drive Source model with space-scoped queries."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, RAGDriveSource)

    async def get_all_for_space(self, space_id: UUID) -> list[RAGDriveSource]:
        """Get all Drive sources for a space, ordered by creation date descending."""
        stmt = (
            select(RAGDriveSource)
            .where(RAGDriveSource.space_id == space_id)
            .order_by(RAGDriveSource.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_for_user(self, user_id: UUID) -> list[RAGDriveSource]:
        """Every Drive source the user linked, across spaces (ADR-261 push reindex)."""
        stmt = select(RAGDriveSource).where(RAGDriveSource.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_space(self, source_id: UUID, space_id: UUID) -> RAGDriveSource | None:
        """Get a Drive source by ID scoped to a specific space."""
        stmt = select(RAGDriveSource).where(
            RAGDriveSource.id == source_id,
            RAGDriveSource.space_id == space_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_space(self, space_id: UUID) -> int:
        """Count Drive sources in a space."""
        stmt = select(func.count(RAGDriveSource.id)).where(RAGDriveSource.space_id == space_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def exists_for_space_and_folder(self, space_id: UUID, folder_id: str) -> bool:
        """Check whether a Drive folder is already linked to a space."""
        stmt = select(func.count(RAGDriveSource.id)).where(
            RAGDriveSource.space_id == space_id,
            RAGDriveSource.folder_id == folder_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one() > 0


class RAGMailSourceRepository(BaseRepository[RAGMailSource]):
    """Repository for the Gmail label sources of a space (ADR-262)."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, RAGMailSource)

    async def get_all_for_space(self, space_id: UUID) -> list[RAGMailSource]:
        """Every label source of a space, newest first."""
        stmt = (
            select(RAGMailSource)
            .where(RAGMailSource.space_id == space_id)
            .order_by(RAGMailSource.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_for_user(self, user_id: UUID) -> list[RAGMailSource]:
        """Every label source the user linked, across spaces (push-driven indexing)."""
        stmt = select(RAGMailSource).where(RAGMailSource.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_and_space(self, source_id: UUID, space_id: UUID) -> RAGMailSource | None:
        """A label source by id, scoped to its space (ownership is the space's)."""
        stmt = select(RAGMailSource).where(
            RAGMailSource.id == source_id,
            RAGMailSource.space_id == space_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_space(self, space_id: UUID) -> int:
        """Number of label sources in a space."""
        stmt = select(func.count(RAGMailSource.id)).where(RAGMailSource.space_id == space_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def exists_for_space_and_label(self, space_id: UUID, label_id: str) -> bool:
        """Whether a label is already linked to a space."""
        stmt = select(func.count(RAGMailSource.id)).where(
            RAGMailSource.space_id == space_id,
            RAGMailSource.label_id == label_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one() > 0


class RAGDocumentRepository(BaseRepository[RAGDocument]):
    """Repository for RAG Document model with space-scoped queries."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, RAGDocument)

    async def get_all_for_space(self, space_id: UUID) -> list[RAGDocument]:
        """Get all documents in a space, ordered by creation date."""
        stmt = (
            select(RAGDocument)
            .where(RAGDocument.space_id == space_id)
            .order_by(RAGDocument.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_for_space(self, space_id: UUID) -> int:
        """Count documents in a space."""
        stmt = select(func.count(RAGDocument.id)).where(RAGDocument.space_id == space_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_total_size_for_space(self, space_id: UUID) -> int:
        """Get total file size in bytes for all documents in a space."""
        stmt = select(func.coalesce(func.sum(RAGDocument.file_size), 0)).where(
            RAGDocument.space_id == space_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def count_ready_for_space(self, space_id: UUID) -> int:
        """Count documents with status 'ready' in a space."""
        stmt = select(func.count(RAGDocument.id)).where(
            RAGDocument.space_id == space_id,
            RAGDocument.status == RAGDocumentStatus.READY,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_all_for_reindex(self) -> list[RAGDocument]:
        """Get all user documents that need reindexing.

        Excludes system space documents (managed by SystemSpaceIndexer).
        """
        stmt = (
            select(RAGDocument)
            .join(RAGSpace, RAGDocument.space_id == RAGSpace.id)
            .where(
                RAGDocument.status.in_([RAGDocumentStatus.READY, RAGDocumentStatus.ERROR]),
                RAGSpace.is_system.is_(False),
            )
            .order_by(RAGDocument.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_space_docs_not_on_generation(self, space_id: UUID, target_model: str) -> int:
        """Count a space's documents NOT fully rebuilt onto ``target_model`` (AC-001).

        A space is ready for the generational flip only when this returns 0 —
        every document is READY and stamped with the target embedding model. A
        non-zero count means at least one document is still mid-rebuild
        (PENDING/PROCESSING) or failed (kept on the old generation), so the space
        stays pinned on the stable generation until the reaper finishes it.
        """
        stmt = select(func.count(RAGDocument.id)).where(
            RAGDocument.space_id == space_id,
            or_(
                RAGDocument.status != RAGDocumentStatus.READY,
                RAGDocument.embedding_model.is_(None),
                RAGDocument.embedding_model != target_model,
            ),
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def get_space_stats(self, space_id: UUID) -> dict:
        """Get aggregated stats for a space (document_count, total_size, ready_count)."""
        stmt = select(
            func.count(RAGDocument.id).label("document_count"),
            func.coalesce(func.sum(RAGDocument.file_size), 0).label("total_size"),
            func.coalesce(
                func.sum(
                    case(
                        (RAGDocument.status == RAGDocumentStatus.READY, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("ready_document_count"),
        ).where(RAGDocument.space_id == space_id)
        result = await self.db.execute(stmt)
        row = result.one()
        return {
            "document_count": row.document_count,
            "total_size": row.total_size,
            "ready_document_count": row.ready_document_count,
        }

    async def get_drive_documents_for_source(self, drive_source_id: UUID) -> list[RAGDocument]:
        """Get all documents originating from a specific Drive source."""
        stmt = (
            select(RAGDocument)
            .where(RAGDocument.drive_source_id == drive_source_id)
            .order_by(RAGDocument.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_drive_file_id(self, space_id: UUID, drive_file_id: str) -> RAGDocument | None:
        """Get a document by its Google Drive file ID within a space."""
        stmt = select(RAGDocument).where(
            RAGDocument.space_id == space_id,
            RAGDocument.drive_file_id == drive_file_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_drive_file_ids_for_source(self, drive_source_id: UUID) -> set[str]:
        """Get all Drive file IDs already ingested for a given source."""
        stmt = select(RAGDocument.drive_file_id).where(
            RAGDocument.drive_source_id == drive_source_id,
            RAGDocument.drive_file_id.is_not(None),
        )
        result = await self.db.execute(stmt)
        return {row[0] for row in result.all()}

    async def get_mail_documents_for_source(self, mail_source_id: UUID) -> list[RAGDocument]:
        """Every document a label source rendered (ADR-262)."""
        stmt = (
            select(RAGDocument)
            .where(RAGDocument.mail_source_id == mail_source_id)
            .order_by(RAGDocument.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_mail_thread_id(self, space_id: UUID, thread_id: str) -> RAGDocument | None:
        """The document rendering a Gmail thread within a space, if any."""
        stmt = select(RAGDocument).where(
            RAGDocument.space_id == space_id,
            RAGDocument.mail_thread_id == thread_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_ready_mail_documents(self, mail_source_id: UUID) -> int:
        """Exact number of READY documents a label source holds (the count it shows)."""
        stmt = select(func.count(RAGDocument.id)).where(
            RAGDocument.mail_source_id == mail_source_id,
            RAGDocument.status == RAGDocumentStatus.READY,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_mail_thread_ids_for_source(self, mail_source_id: UUID) -> set[str]:
        """Every thread id a label source already rendered."""
        stmt = select(RAGDocument.mail_thread_id).where(
            RAGDocument.mail_source_id == mail_source_id,
            RAGDocument.mail_thread_id.is_not(None),
        )
        result = await self.db.execute(stmt)
        return {row[0] for row in result.all()}


class RAGChunkRepository(BaseRepository[RAGChunk]):
    """Repository for RAG Chunk model with vector search capabilities."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, RAGChunk)

    async def search_by_similarity(
        self,
        user_id: UUID | None,
        space_ids: list[UUID],
        query_embedding: list[float],
        limit: int = 10,
        embedding_model: str | None = None,
    ) -> list[tuple[RAGChunk, float]]:
        """
        Search chunks by cosine similarity via pgvector.

        Returns chunks with their similarity score (higher = more similar, range [0, 1]).
        Internally converts cosine distance (lower = closer) to similarity (1 - distance).

        Args:
            user_id: User ID for user-owned chunks, or None for system chunks.
            space_ids: Space IDs to search within.
            query_embedding: Query vector.
            limit: Maximum results to return.
            embedding_model: When set, restrict to chunks of this embedding
                generation (AC-001 generational continuity). The caller MUST have
                produced ``query_embedding`` with the SAME model — comparing a
                query vector of one generation against chunks of another is
                cosine-meaningless. None searches every generation (steady state).
        """
        if not space_ids:
            return []

        cosine_distance = RAGChunk.embedding.cosine_distance(query_embedding)
        user_filter = RAGChunk.user_id.is_(None) if user_id is None else RAGChunk.user_id == user_id
        conditions = [user_filter, RAGChunk.space_id.in_(space_ids)]
        if embedding_model is not None:
            conditions.append(RAGChunk.embedding_model == embedding_model)
        stmt = (
            select(RAGChunk, cosine_distance.label("distance"))
            .where(*conditions)
            .order_by(cosine_distance)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        # Convert distance to similarity score: 1 - distance (clamped to [0, 1])
        return [(row[0], max(0.0, 1.0 - float(row[1]))) for row in result.all()]

    async def delete_by_document(self, document_id: UUID) -> int:
        """Bulk delete all chunks for a document. Returns count deleted."""
        stmt = delete(RAGChunk).where(RAGChunk.document_id == document_id)
        result = await self.db.execute(stmt)
        count = getattr(result, "rowcount", 0) or 0
        logger.debug(
            "rag_chunks_deleted_by_document",
            document_id=str(document_id),
            count=count,
        )
        return int(count)

    async def move_to_space(self, document_id: UUID, space_id: UUID) -> int:
        """Point every chunk of a document at another space (ADR-259).

        The chunk carries ``space_id`` denormalized for retrieval, so a moved
        document must carry its chunks along or retrieval keeps answering from
        the old space.

        Args:
            document_id: The document whose chunks move.
            space_id: The destination space.

        Returns:
            The number of chunks updated.
        """
        result = await self.db.execute(
            update(RAGChunk).where(RAGChunk.document_id == document_id).values(space_id=space_id)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_by_space(self, space_id: UUID) -> int:
        """Bulk delete all chunks for a space. Returns count deleted."""
        stmt = delete(RAGChunk).where(RAGChunk.space_id == space_id)
        result = await self.db.execute(stmt)
        count = getattr(result, "rowcount", 0) or 0
        logger.debug(
            "rag_chunks_deleted_by_space",
            space_id=str(space_id),
            count=count,
        )
        return int(count)

    async def delete_by_document_and_model(self, document_id: UUID, embedding_model: str) -> int:
        """Delete only one generation's chunks for a document (AC-001 side-by-side).

        During a same-dimension reindex the document keeps its stable (serving)
        generation while the target generation is (re)built. Replacing only the
        TARGET generation makes the rebuild idempotent — a retried document does
        not accumulate duplicate new-generation chunks — without ever touching
        the still-served old generation. Returns the count deleted.
        """
        stmt = delete(RAGChunk).where(
            RAGChunk.document_id == document_id,
            RAGChunk.embedding_model == embedding_model,
        )
        result = await self.db.execute(stmt)
        count = getattr(result, "rowcount", 0) or 0
        logger.debug(
            "rag_chunks_deleted_by_document_and_model",
            document_id=str(document_id),
            embedding_model=embedding_model,
            count=count,
        )
        return int(count)

    async def delete_by_space_and_model(self, space_id: UUID, embedding_model: str) -> int:
        """Delete one generation's chunks for a space (AC-001 post-flip cleanup).

        Called AFTER the space's serving pointer has flipped to the new
        generation, so the old-generation chunks are no longer served and can be
        reclaimed. Returns the count deleted.
        """
        stmt = delete(RAGChunk).where(
            RAGChunk.space_id == space_id,
            RAGChunk.embedding_model == embedding_model,
        )
        result = await self.db.execute(stmt)
        count = getattr(result, "rowcount", 0) or 0
        logger.debug(
            "rag_chunks_deleted_by_space_and_model",
            space_id=str(space_id),
            embedding_model=embedding_model,
            count=count,
        )
        return int(count)

    async def count_by_space_and_model(self, space_id: UUID, embedding_model: str) -> int:
        """Count a space's chunks that belong to one embedding generation."""
        stmt = select(func.count(RAGChunk.id)).where(
            RAGChunk.space_id == space_id,
            RAGChunk.embedding_model == embedding_model,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def get_corpus_for_spaces(
        self,
        user_id: UUID | None,
        space_ids: list[UUID],
        embedding_model: str | None = None,
    ) -> list[tuple[UUID, str]]:
        """
        Get all chunk IDs and content for BM25 indexing.

        Args:
            user_id: User ID for user-owned chunks, or None for system chunks.
            space_ids: Space IDs to retrieve corpus from.
            embedding_model: When set, restrict to chunks of this embedding
                generation so the BM25 corpus stays aligned with the semantic
                candidates (AC-001) — a chunk_id that never appears among the
                semantic results would score nothing anyway, but keeping both
                sides on the same generation avoids building a corpus over
                soon-to-be-deleted chunks. None = every generation (steady state).

        Returns:
            List of (chunk_id, content) tuples.
        """
        if not space_ids:
            return []

        user_filter = RAGChunk.user_id.is_(None) if user_id is None else RAGChunk.user_id == user_id
        conditions = [user_filter, RAGChunk.space_id.in_(space_ids)]
        if embedding_model is not None:
            conditions.append(RAGChunk.embedding_model == embedding_model)
        stmt = select(RAGChunk.id, RAGChunk.content).where(*conditions).order_by(RAGChunk.id)
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def count_for_space(self, space_id: UUID) -> int:
        """Count total chunks in a space."""
        stmt = select(func.count(RAGChunk.id)).where(RAGChunk.space_id == space_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def bulk_create_chunks(self, chunks: list[RAGChunk]) -> int:
        """Bulk insert chunks. Returns count inserted."""
        if not chunks:
            return 0

        self.db.add_all(chunks)
        await self.db.flush()

        logger.debug(
            "rag_chunks_bulk_created",
            count=len(chunks),
        )
        return len(chunks)
