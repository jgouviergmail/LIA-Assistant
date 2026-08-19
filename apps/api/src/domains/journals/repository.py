"""
Repository for Journals domain database operations.

Provides optimized queries for:
- Journal entry CRUD operations
- Semantic relevance search via pgvector cosine distance
- Temporal recency queries for continuity injection
- Size tracking (total chars)
- Theme-based filtering and counting
- GDPR export and bulk delete
"""

from contextlib import suppress
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.domains.journals.models import JournalEntry, JournalEntryStatus
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import journal_entries_total

logger = get_logger(__name__)


def consolidation_eligible_user_conditions() -> list[ColumnElement[bool]]:
    """Return the conditions selecting users whose journal can be consolidated.

    Single source of truth for "the scheduler may still process this user",
    shared by the eligibility query in
    ``infrastructure/scheduler/journal_consolidation.py`` and by the
    portrait-age gauge. The cooldown predicate is deliberately NOT part of it:
    it is the scheduler's pacing concern, not a property of the user.

    Keeping the two in one place is not cosmetic. A gauge that counts users the
    scheduler will never pick up reports a staleness nobody can act on, and pins
    the alert high forever.

    Returns:
        Conditions to splice into a ``select(...).where(and_(*conditions))``.
    """
    from src.domains.users.models import User

    return [
        User.journals_enabled.is_(True),
        User.journal_consolidation_enabled.is_(True),
        User.is_active.is_(True),
        User.deleted_at.is_(None),
    ]


def build_consolidation_eligible_users_query(
    cooldown_threshold: datetime,
    min_entries: int,
) -> Any:
    """Build the delta-driven consolidation eligibility query (B-03, 2026-08-19).

    A user is eligible when there is WORK: at least ``min_entries`` ACTIVE
    entries AND (never consolidated OR an active entry touched since the last
    consolidation stamp). The historical absolute floor (3) starved every
    real user — consolidation prunes journals toward 2 entries, which made it
    permanently ineligible and stalled portraits for months.

    No churn loop by construction: ``journal_last_consolidated_at`` is
    stamped AFTER the run's actions commit (``consolidation_service``), so a
    consolidation's own edits always carry ``updated_at`` strictly below the
    stamp and never re-trigger the next cycle.

    Args:
        cooldown_threshold: Scheduler pacing bound (now - cooldown hours).
        min_entries: Minimum ACTIVE entries (env-overridable floor; the
            default must stay reachable by a post-prune journal — pinned at 1
            by test).

    Returns:
        A ``Select`` over ``User`` rows, ready for ``db.execute``.
    """
    from src.domains.users.models import User

    work_subq = (
        select(
            JournalEntry.user_id,
            func.count(JournalEntry.id).label("entry_count"),
            func.max(JournalEntry.updated_at).label("last_touched_at"),
        )
        .where(JournalEntry.status == JournalEntryStatus.ACTIVE.value)
        .group_by(JournalEntry.user_id)
        .having(func.count(JournalEntry.id) >= min_entries)
        .subquery()
    )

    return (
        select(User)
        .join(work_subq, User.id == work_subq.c.user_id)
        .where(
            and_(
                # Shared with the portrait-age gauge — see the helper's
                # docstring for why the two must not drift apart.
                *consolidation_eligible_user_conditions(),
                # Cooldown: never consolidated OR last > cooldown (pacing)
                (
                    User.journal_last_consolidated_at.is_(None)
                    | (User.journal_last_consolidated_at < cooldown_threshold)
                ),
                # Delta: never consolidated OR something changed since (work)
                (
                    User.journal_last_consolidated_at.is_(None)
                    | (work_subq.c.last_touched_at > User.journal_last_consolidated_at)
                ),
            )
        )
    )


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
        # metrics must never break writes
        with suppress(Exception):
            journal_entries_total.labels(
                action="create", theme=entry.theme, source=entry.source
            ).inc()

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
        # metrics must never break writes
        with suppress(Exception):
            journal_entries_total.labels(
                action="update", theme=entry.theme, source=entry.source
            ).inc()

        return entry

    async def delete_entry(self, entry: JournalEntry) -> None:
        """Delete a single entry."""
        theme = entry.theme  # capture before delete (entry becomes detached)
        source = entry.source
        await self.db.delete(entry)
        await self.db.flush()

        logger.info(
            "journal_entry_deleted",
            entry_id=str(entry.id),
            user_id=str(entry.user_id),
        )
        # metrics must never break writes
        with suppress(Exception):
            journal_entries_total.labels(action="delete", theme=theme, source=source).inc()

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
        exclude_levels: list[str] | None = None,
        observed_scores: list[float] | None = None,
    ) -> list[tuple[JournalEntry, float]]:
        """Search active entries by multi-vector semantic relevance.

        Uses dual-vector strategy: computes cosine distance against both
        the content embedding and the keyword embedding, taking the best
        match (minimum distance). Falls back to content-only distance
        when keyword_embedding is NULL.

        Args:
            user_id: User UUID.
            query_embedding: Query embedding vector (1536 dims Gemini).
            limit: Max results to return.
            min_score: Minimum similarity score to include (0.0-1.0).
            exclude_levels: Abstraction levels to filter OUT (e.g. ``["L0", "L3"]``
                for operational injection). ``None`` (default) returns all levels
                — used by extraction/consolidation which must see every level.
            observed_scores: Optional accumulator receiving EVERY candidate
                similarity (filtered ones included) — the adaptive threshold
                controller's observation channel (lot 7). Purely additive.

        Returns:
            List of (entry, score) tuples sorted by score descending,
            filtered by min_score.
        """
        if not query_embedding:
            return []

        dist_content = JournalEntry.embedding.cosine_distance(query_embedding)
        dist_keyword = JournalEntry.keyword_embedding.cosine_distance(query_embedding)

        best_distance = func.least(
            dist_content,
            func.coalesce(dist_keyword, dist_content),
        )

        conditions = [
            JournalEntry.user_id == user_id,
            JournalEntry.status == JournalEntryStatus.ACTIVE.value,
            JournalEntry.embedding.isnot(None),
        ]
        if exclude_levels:
            conditions.append(JournalEntry.level.not_in(exclude_levels))

        stmt = (
            select(JournalEntry, best_distance.label("distance"))
            .where(and_(*conditions))
            .order_by(best_distance)
            .limit(limit)
        )
        result = await self.db.execute(stmt)

        scored: list[tuple[JournalEntry, float]] = []
        all_scores: list[dict[str, str | float | bool]] = []
        for row in result.all():
            similarity = max(0.0, 1.0 - float(row[1]))
            entry: JournalEntry = row[0]
            all_scores.append(
                {
                    "title": entry.title[:40],
                    "score": round(similarity, 4),
                    "passed": similarity >= min_score,
                }
            )
            if observed_scores is not None:
                observed_scores.append(round(similarity, 4))
            if similarity >= min_score:
                scored.append((entry, similarity))

        logger.info(
            "journal_semantic_search_results",
            user_id=str(user_id),
            total_candidates=len(all_scores),
            passed_filter=len(scored),
            min_score=min_score,
            scores=all_scores,
        )

        return scored

    async def get_by_level_for_user(
        self,
        user_id: UUID,
        level: str,
        limit: int = 20,
    ) -> list[JournalEntry]:
        """Get all active entries at a given abstraction level (commit 3 prep).

        Used by the portrait builder to load L3 facets when compiling the user
        model that LIA carries everywhere it speaks.

        Args:
            user_id: User UUID
            level: Abstraction level (L0/L1/L2/L3)
            limit: Max entries to return

        Returns:
            List of active entries at the requested level, ordered by created_at desc
        """
        result = await self.db.execute(
            select(JournalEntry)
            .where(
                and_(
                    JournalEntry.user_id == user_id,
                    JournalEntry.status == JournalEntryStatus.ACTIVE.value,
                    JournalEntry.level == level,
                )
            )
            .order_by(JournalEntry.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_for_user(
        self,
        user_id: UUID,
        limit: int = 2,
        exclude_levels: list[str] | None = None,
    ) -> list[JournalEntry]:
        """
        Get most recent active entries for temporal continuity injection.

        Returns entries ordered by creation date descending, regardless of
        semantic score. Used to ensure the assistant always has access to
        its most recent reflections.

        Args:
            user_id: User UUID
            limit: Max entries to return
            exclude_levels: Abstraction levels to filter OUT (e.g. ``["L0", "L3"]``
                for operational injection). ``None`` (default) returns all levels
                — used by extraction which must see every level.

        Returns:
            List of entries sorted by created_at descending
        """
        conditions = [
            JournalEntry.user_id == user_id,
            JournalEntry.status == JournalEntryStatus.ACTIVE.value,
        ]
        if exclude_levels:
            conditions.append(JournalEntry.level.not_in(exclude_levels))

        result = await self.db.execute(
            select(JournalEntry)
            .where(and_(*conditions))
            .order_by(JournalEntry.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def increment_injection_counts(self, entry_ids: list[UUID]) -> None:
        """
        Bulk increment injection_count and set last_injected_at for injected entries.

        Called after journal context is built to track which entries are
        actually used in prompts. Non-blocking (called via safe_fire_and_forget).

        Args:
            entry_ids: UUIDs of entries that were injected into a prompt
        """
        if not entry_ids:
            return

        from datetime import UTC
        from datetime import datetime as dt

        from sqlalchemy import update

        await self.db.execute(
            update(JournalEntry)
            .where(JournalEntry.id.in_(entry_ids))
            .values(
                injection_count=JournalEntry.injection_count + 1,
                last_injected_at=dt.now(UTC),
            )
        )
        await self.db.commit()

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

    async def compute_zero_injection_age_days_avg(self) -> float:
        """Compute the global average age (in days) of active entries never injected.

        This is the central effectiveness signal of the journal:
        a high value means directives are accumulating without ever being used
        in prompts — likely ill-formulated or off-topic.

        Returns:
            Average age in days (float). Returns 0.0 if no such entries exist.
        """
        from sqlalchemy import Float, cast

        age_days_expr = cast(
            func.extract("epoch", func.now() - JournalEntry.created_at) / 86400.0,
            Float,
        )
        stmt = select(func.coalesce(func.avg(age_days_expr), 0.0)).where(
            and_(
                JournalEntry.status == JournalEntryStatus.ACTIVE.value,
                JournalEntry.injection_count == 0,
            )
        )
        result = await self.db.execute(stmt)
        return float(result.scalar() or 0.0)

    async def count_by_theme_global(self) -> dict[str, int]:
        """Get global counts of active entries grouped by theme.

        Used by the consolidation scheduler to refresh the
        ``journal_theme_distribution`` Prometheus gauge. A theme reported at 0
        across every user means the extraction/consolidation prompts have made
        it unreachable — the failure mode this gauge exists to surface.

        Returns:
            Dict mapping theme code to count.
        """
        result = await self.db.execute(
            select(JournalEntry.theme, func.count(JournalEntry.id))
            .where(JournalEntry.status == JournalEntryStatus.ACTIVE.value)
            .group_by(JournalEntry.theme)
        )
        return {str(row[0]): int(row[1]) for row in result.all()}

    async def compute_max_portrait_age_hours(self) -> float:
        """Compute the age in hours of the OLDEST portrait the scheduler still owns.

        Restricted to consolidation-eligible users
        (:func:`consolidation_eligible_user_conditions`). A user who opted out,
        was deactivated or soft-deleted will never be consolidated again, so
        counting them would pin this gauge high forever and make the staleness
        alert unactionable — the opposite of what it exists for.

        Users whose portrait was never compiled are ignored: they have no stale
        portrait, they have none at all (a different signal, already visible
        through the level distribution).

        Returns:
            Age in hours of the least recently compiled portrait, or 0.0 when no
            eligible user has a compiled portrait.
        """
        from sqlalchemy import Float, cast

        from src.domains.users.models import User

        age_hours_expr = cast(
            func.extract("epoch", func.now() - User.journal_portrait_compiled_at) / 3600.0,
            Float,
        )
        stmt = select(func.coalesce(func.max(age_hours_expr), 0.0)).where(
            and_(
                *consolidation_eligible_user_conditions(),
                User.journal_portrait_compiled_at.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        return float(result.scalar() or 0.0)

    async def count_by_level_global(self) -> dict[str, int]:
        """Get global counts of active entries grouped by abstraction level.

        Used by the consolidation scheduler to refresh the
        ``journal_level_distribution`` Prometheus gauge.

        Returns:
            Dict mapping level code (L0/L1/L2/L3) to count.
        """
        result = await self.db.execute(
            select(JournalEntry.level, func.count(JournalEntry.id))
            .where(JournalEntry.status == JournalEntryStatus.ACTIVE.value)
            .group_by(JournalEntry.level)
        )
        return {str(row[0]): int(row[1]) for row in result.all()}

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
