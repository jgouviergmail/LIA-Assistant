"""
RAG Spaces repositories.

Provides data access for RAG spaces, documents, and vector chunks.
Inherits from BaseRepository for standard CRUD operations.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.rag_spaces.models import (
    RAGChunk,
    RAGDocument,
    RAGDocumentStatus,
    RAGDriveSource,
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
        """
        if not space_ids:
            return []

        cosine_distance = RAGChunk.embedding.cosine_distance(query_embedding)
        user_filter = RAGChunk.user_id.is_(None) if user_id is None else RAGChunk.user_id == user_id
        stmt = (
            select(RAGChunk, cosine_distance.label("distance"))
            .where(user_filter, RAGChunk.space_id.in_(space_ids))
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

    async def get_corpus_for_spaces(
        self, user_id: UUID | None, space_ids: list[UUID]
    ) -> list[tuple[UUID, str]]:
        """
        Get all chunk IDs and content for BM25 indexing.

        Args:
            user_id: User ID for user-owned chunks, or None for system chunks.
            space_ids: Space IDs to retrieve corpus from.

        Returns:
            List of (chunk_id, content) tuples.
        """
        if not space_ids:
            return []

        user_filter = RAGChunk.user_id.is_(None) if user_id is None else RAGChunk.user_id == user_id
        stmt = (
            select(RAGChunk.id, RAGChunk.content)
            .where(user_filter, RAGChunk.space_id.in_(space_ids))
            .order_by(RAGChunk.id)
        )
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
