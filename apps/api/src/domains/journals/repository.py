"""
Repository for Journals domain database operations.

Provides optimized queries for:
- Journal entry CRUD operations
- Semantic relevance search via cosine similarity
- Size tracking (total chars)
- Theme-based filtering and counting
- GDPR export and bulk delete
"""

from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.models import JournalEntry, JournalEntryStatus
from src.infrastructure.llm.local_embeddings import cosine_similarity
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class JournalEntryRepository:
    """
    Repository for JournalEntry database operations.

    Provides CRUD operations and specialized queries for:
    - Semantic relevance search (cosine similarity in Python)
    - Size tracking for prompt-driven lifecycle management
    - Theme-based filtering for UI
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.db = db

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create(self, entry: JournalEntry) -> JournalEntry:
        """
        Persist a new journal entry.

        Args:
            entry: JournalEntry instance (pre-populated with all fields)

        Returns:
            Created JournalEntry with generated ID
        """
        self.db.add(entry)
        await self.db.flush()

        logger.info(
            "journal_entry_created",
            entry_id=str(entry.id),
            user_id=str(entry.user_id),
            theme=entry.theme,
            source=entry.source,
            char_count=entry.char_count,
        )

        return entry

    async def get_by_id(self, entry_id: UUID) -> JournalEntry | None:
        """Get entry by ID."""
        result = await self.db.execute(select(JournalEntry).where(JournalEntry.id == entry_id))
        return result.scalar_one_or_none()

    async def get_by_id_for_user(self, entry_id: UUID, user_id: UUID) -> JournalEntry | None:
        """Get entry by ID with ownership check."""
        result = await self.db.execute(
            select(JournalEntry).where(
                and_(
                    JournalEntry.id == entry_id,
                    JournalEntry.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def update(self, entry: JournalEntry) -> JournalEntry:
        """
        Persist changes to an existing entry.

        Args:
            entry: Modified JournalEntry instance

        Returns:
            Updated JournalEntry
        """
        await self.db.flush()

        logger.info(
            "journal_entry_updated",
            entry_id=str(entry.id),
            user_id=str(entry.user_id),
            theme=entry.theme,
            char_count=entry.char_count,
        )

        return entry

    async def delete_entry(self, entry: JournalEntry) -> None:
        """Delete a single entry."""
        await self.db.delete(entry)
        await self.db.flush()

        logger.info(
            "journal_entry_deleted",
            entry_id=str(entry.id),
            user_id=str(entry.user_id),
        )

    # =========================================================================
    # Specialized Queries
    # =========================================================================

    async def get_all_active_for_user(self, user_id: UUID) -> list[JournalEntry]:
        """
        Get all active entries for a user (for consolidation).

        Returns entries ordered by created_at descending.
        """
        result = await self.db.execute(
            select(JournalEntry)
            .where(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == JournalEntryStatus.ACTIVE.value,
                )
            )
            .order_by(JournalEntry.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(
        self,
        user_id: UUID,
        theme: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JournalEntry], int]:
        """
        Get filtered entries for a user with pagination.

        Args:
            user_id: User UUID
            theme: Optional theme filter
            status: Optional status filter
            limit: Max results
            offset: Pagination offset

        Returns:
            Tuple of (entries, total_count)
        """
        conditions = [JournalEntry.user_id == user_id]

        if theme:
            conditions.append(JournalEntry.theme == theme)
        if status:
            conditions.append(JournalEntry.status == status)

        # Count query
        count_stmt = select(func.count(JournalEntry.id)).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Data query
        data_stmt = (
            select(JournalEntry)
            .where(and_(*conditions))
            .order_by(JournalEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        data_result = await self.db.execute(data_stmt)
        entries = list(data_result.scalars().all())

        return entries, total

    async def search_by_relevance(
        self,
        user_id: UUID,
        query_embedding: list[float],
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[JournalEntry, float]]:
        """
        Search active entries by semantic relevance using cosine similarity.

        Loads all active entries with embeddings, computes cosine similarity
        in Python (same pattern as interests dedup), filters by min_score,
        and returns sorted by score descending.

        Args:
            user_id: User UUID
            query_embedding: Query embedding vector (384 dims E5-small)
            limit: Max results to return
            min_score: Minimum cosine similarity to include (prefilter before LLM)

        Returns:
            List of (entry, score) tuples sorted by score descending,
            filtered by min_score
        """
        # Load all active entries with embeddings
        result = await self.db.execute(
            select(JournalEntry).where(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == JournalEntryStatus.ACTIVE.value,
                    JournalEntry.embedding.isnot(None),
                )
            )
        )
        entries = list(result.scalars().all())

        if not entries or not query_embedding:
            return []

        # Compute cosine similarity in Python (volume ~80 entries max per user)
        scored: list[tuple[JournalEntry, float]] = []
        for entry in entries:
            if entry.embedding:
                score = cosine_similarity(query_embedding, entry.embedding)
                # Prefilter: discard entries below min_score threshold
                if score >= min_score:
                    scored.append((entry, score))

        # Sort by score descending, limit results
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    async def get_total_chars(self, user_id: UUID) -> int:
        """
        Get total character count across all active entries for a user.

        Used for size tracking and prompt-driven lifecycle management.
        """
        result = await self.db.execute(
            select(func.coalesce(func.sum(JournalEntry.char_count), 0)).where(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == JournalEntryStatus.ACTIVE.value,
                )
            )
        )
        return result.scalar() or 0

    async def count_by_theme(self, user_id: UUID) -> dict[str, int]:
        """
        Get entry counts grouped by theme (active entries only).

        Returns:
            Dict mapping theme code to count
        """
        result = await self.db.execute(
            select(JournalEntry.theme, func.count(JournalEntry.id))
            .where(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == JournalEntryStatus.ACTIVE.value,
                )
            )
            .group_by(JournalEntry.theme)
        )
        rows = result.all()
        return {str(row[0]): int(row[1]) for row in rows}

    async def count_active_for_user(self, user_id: UUID) -> int:
        """Count active entries for a user."""
        result = await self.db.execute(
            select(func.count(JournalEntry.id)).where(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == JournalEntryStatus.ACTIVE.value,
                )
            )
        )
        return result.scalar() or 0

    async def delete_all_for_user(self, user_id: UUID) -> int:
        """
        Delete all journal entries for a user (GDPR).

        Returns:
            Number of deleted entries
        """
        result = await self.db.execute(delete(JournalEntry).where(JournalEntry.user_id == user_id))
        await self.db.flush()

        count: int = result.rowcount or 0  # type: ignore[attr-defined]
        logger.info(
            "journal_entries_bulk_deleted",
            user_id=str(user_id),
            deleted_count=count,
        )
        return count
