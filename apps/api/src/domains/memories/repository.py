"""
Repository for Memories domain database operations.

Provides optimized queries for:
- Memory CRUD operations

- Semantic relevance search via pgvector cosine distance
- Temporal recency queries for fallback injection
- Category-based filtering (relationships for name enrichment)
- Phase 6 usage tracking (bulk increment)
- Retention-based cleanup (scheduled purge)
- GDPR export and bulk delete

Replaces LangGraph AsyncPostgresStore operations for the memories namespace.
Same pgvector search pattern as JournalEntryRepository.

Phase: v1.14.0 — Memory migration to PostgreSQL custom
Created: 2026-03-30
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, delete, distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.memories.models import Memory, MemoryCategory
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class MemoryRepository:
    """Repository for Memory database operations.

    Provides CRUD operations and specialized queries for:
    - Semantic relevance search (pgvector cosine distance)
    - Category-based filtering (relationships for name enrichment)
    - Phase 6 usage tracking (bulk UPDATE)
    - Retention scoring for automatic cleanup
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            db: AsyncSession for database operations.
        """
        self.db = db

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create(self, memory: Memory) -> Memory:
        """Persist a new memory.

        Args:
            memory: Memory instance (pre-populated with all fields).

        Returns:
            Created Memory with generated ID.
        """
        self.db.add(memory)
        await self.db.flush()
        return memory

    async def update(self, memory: Memory) -> Memory:
        """Update an existing memory.

        The caller should modify the memory fields before calling this.
        TimestampMixin handles updated_at automatically on commit.

        Args:
            memory: Memory instance with updated fields.

        Returns:
            Updated Memory.
        """
        await self.db.flush()
        return memory

    async def delete(self, memory: Memory) -> None:
        """Delete a memory.

        Args:
            memory: Memory instance to delete.
        """
        await self.db.delete(memory)
        await self.db.flush()

    async def get_by_id(self, memory_id: UUID) -> Memory | None:
        """Get a memory by its UUID.

        Args:
            memory_id: Memory UUID.

        Returns:
            Memory instance or None if not found.
        """
        result = await self.db.execute(select(Memory).where(Memory.id == memory_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, memory_id: UUID, user_id: UUID) -> Memory | None:
        """Get a memory by ID with ownership check.

        Args:
            memory_id: Memory UUID.
            user_id: Owner user UUID.

        Returns:
            Memory instance or None if not found or wrong owner.
        """
        result = await self.db.execute(
            select(Memory).where(
                and_(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # Semantic Search (pgvector cosine distance)
    # =========================================================================

    async def search_by_relevance(
        self,
        user_id: UUID,
        query_embedding: list[float],
        limit: int = 10,
        min_score: float = 0.5,
    ) -> list[tuple[Memory, float]]:
        """Search memories by multi-vector semantic relevance.

        Uses dual-vector strategy: computes cosine distance against both
        the content embedding and the keyword embedding, taking the best
        match (minimum distance). This restores the multi-field search
        behavior from the old LangGraph store.

        Falls back to content-only distance when keyword_embedding is NULL.

        Args:
            user_id: User UUID.
            query_embedding: Pre-computed query embedding vector (1536 dims).
            limit: Max results to return.
            min_score: Minimum similarity score to include (0.0-1.0).

        Returns:
            List of (memory, score) tuples sorted by score descending,
            filtered by min_score.
        """
        if not query_embedding:
            return []

        dist_content = Memory.embedding.cosine_distance(query_embedding)
        dist_keyword = Memory.keyword_embedding.cosine_distance(query_embedding)

        # Best match = minimum distance across both vectors.
        # COALESCE handles NULL keyword_embedding (fallback to content distance).
        best_distance = func.least(
            dist_content,
            func.coalesce(dist_keyword, dist_content),
        )

        stmt = (
            select(Memory, best_distance.label("distance"))
            .where(
                and_(
                    Memory.user_id == user_id,
                    Memory.embedding.isnot(None),
                )
            )
            .order_by(best_distance)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        all_rows = result.all()

        scored: list[tuple[Memory, float]] = []
        for row in all_rows:
            similarity = max(0.0, 1.0 - float(row[1]))
            memory: Memory = row[0]
            if similarity >= min_score:
                scored.append((memory, similarity))

        logger.info(
            "memory_semantic_search_results",
            user_id=str(user_id),
            total_candidates=len(all_rows),
            passed_filter=len(scored),
            min_score=min_score,
        )

        return scored

    async def get_relationships_for_user(
        self,
        user_id: UUID,
        query_embedding: list[float],
        limit: int = 20,
        min_score: float = 0.3,
    ) -> list[tuple[Memory, float]]:
        """Search relationship memories for name enrichment.

        Combines multi-vector semantic search with category filter for
        'relationship'. Used by memory extraction to enrich "my son"
        with "My son John Smith".

        Args:
            user_id: User UUID.
            query_embedding: Pre-computed query embedding vector.
            limit: Max results to return.
            min_score: Minimum similarity score.

        Returns:
            List of (memory, score) tuples for relationship category only.
        """
        if not query_embedding:
            return []

        dist_content = Memory.embedding.cosine_distance(query_embedding)
        dist_keyword = Memory.keyword_embedding.cosine_distance(query_embedding)
        best_distance = func.least(
            dist_content,
            func.coalesce(dist_keyword, dist_content),
        )

        stmt = (
            select(Memory, best_distance.label("distance"))
            .where(
                and_(
                    Memory.user_id == user_id,
                    Memory.category == MemoryCategory.RELATIONSHIP.value,
                    Memory.embedding.isnot(None),
                )
            )
            .order_by(best_distance)
            .limit(limit)
        )
        result = await self.db.execute(stmt)

        scored: list[tuple[Memory, float]] = []
        for row in result.all():
            similarity = max(0.0, 1.0 - float(row[1]))
            memory: Memory = row[0]
            if similarity >= min_score:
                scored.append((memory, similarity))

        return scored

    # =========================================================================
    # List & Filter Queries
    # =========================================================================

    async def get_all_for_user(
        self,
        user_id: UUID,
        limit: int = 1000,
    ) -> list[Memory]:
        """Get all memories for a user.

        Used by export, cleanup, and delete-all operations.

        Args:
            user_id: User UUID.
            limit: Max results.

        Returns:
            List of memories ordered by created_at descending.
        """
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_for_user(
        self,
        user_id: UUID,
        limit: int = 5,
    ) -> list[Memory]:
        """Get most recent memories for fallback injection.

        Used when embedding is None (trivial message or embedding failure)
        to still provide some memory context.

        Args:
            user_id: User UUID.
            limit: Number of recent memories.

        Returns:
            List of memories ordered by created_at descending.
        """
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_category(
        self,
        user_id: UUID,
        category: str,
        limit: int = 200,
    ) -> list[Memory]:
        """Get memories filtered by category.

        Args:
            user_id: User UUID.
            category: Category string value.
            limit: Max results.

        Returns:
            List of memories in the given category.
        """
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.user_id == user_id,
                    Memory.category == category,
                )
            )
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Aggregation & Stats
    # =========================================================================

    async def get_count_for_user(self, user_id: UUID) -> int:
        """Get total memory count for a user.

        Used by admin dashboard and user stats views.

        Args:
            user_id: User UUID.

        Returns:
            Number of memories.
        """
        stmt = select(func.count(Memory.id)).where(Memory.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def get_count_by_category(self, user_id: UUID) -> dict[str, int]:
        """Get memory count grouped by category.

        Args:
            user_id: User UUID.

        Returns:
            Dict of category name to count.
        """
        stmt = (
            select(Memory.category, func.count(Memory.id))
            .where(Memory.user_id == user_id)
            .group_by(Memory.category)
        )
        result = await self.db.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    # =========================================================================
    # Phase 6: Usage Tracking
    # =========================================================================

    async def increment_usage(self, memory_ids: list[UUID]) -> None:
        """Bulk increment usage_count and update last_accessed_at.

        Called by memory injection's usage tracking (fire-and-forget)
        for memories retrieved with high relevance score.

        Replaces the store.aput() pattern that rewrote the full value dict.

        Args:
            memory_ids: UUIDs of memories to update.
        """
        if not memory_ids:
            return

        now = datetime.now(UTC)
        stmt = (
            update(Memory)
            .where(Memory.id.in_(memory_ids))
            .values(
                usage_count=Memory.usage_count + 1,
                last_accessed_at=now,
            )
        )
        await self.db.execute(stmt)
        await self.db.flush()

        logger.debug(
            "memory_usage_incremented",
            count=len(memory_ids),
        )

    # =========================================================================
    # Cleanup (Scheduled Purge)
    # =========================================================================

    async def get_for_cleanup(
        self,
        user_id: UUID,
        max_age_days: int,
    ) -> list[Memory]:
        """Get memories eligible for cleanup evaluation.

        Returns all non-pinned memories for a user for retention scoring.
        The caller applies the retention algorithm (usage + importance + recency).

        Args:
            user_id: User UUID.
            max_age_days: Not used for filtering (caller handles age check),
                kept for API consistency.

        Returns:
            All non-pinned memories for the user.
        """
        stmt = (
            select(Memory)
            .where(
                and_(
                    Memory.user_id == user_id,
                    Memory.pinned.is_(False),
                )
            )
            .order_by(Memory.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_ids_with_memories(self) -> list[UUID]:
        """Get all distinct user IDs that have at least one memory.

        Used by the cleanup scheduler to iterate over users.

        Returns:
            List of unique user UUIDs.
        """
        stmt = select(distinct(Memory.user_id))
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    # =========================================================================
    # GDPR / Bulk Operations
    # =========================================================================

    async def delete_all_for_user(
        self,
        user_id: UUID,
        preserve_pinned: bool = False,
    ) -> int:
        """Delete all memories for a user (GDPR right to erasure).

        Args:
            user_id: User UUID.
            preserve_pinned: If True, keep pinned memories.

        Returns:
            Number of memories deleted.
        """
        conditions = [Memory.user_id == user_id]
        if preserve_pinned:
            conditions.append(Memory.pinned.is_(False))

        stmt = delete(Memory).where(and_(*conditions))
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount or 0  # type: ignore[attr-defined]
