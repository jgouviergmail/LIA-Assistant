"""Open Loops repository — atomic status transitions + hot-path listings.

Status transitions are server-side conditional UPDATEs (never SELECT →
mutate → flush): a loop leaves OPEN exactly once, whatever the concurrency
(extractor closure vs API close vs lazy expiry). Same doctrine as
``scheduled_actions/repository.py``.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus

logger = structlog.get_logger(__name__)


class OpenLoopRepository(BaseRepository[OpenLoop]):
    """Repository for open-loop CRUD and atomic lifecycle transitions."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, OpenLoop)

    async def list_open_for_user(
        self,
        user_id: UUID,
        limit: int = 30,
    ) -> list[OpenLoop]:
        """List a user's OPEN loops, earliest deadline first (NULLs last).

        Args:
            user_id: Owner.
            limit: Cap on returned rows.

        Returns:
            OPEN loops ordered by due_hint (nulls last), then creation time.
        """
        stmt = (
            select(OpenLoop)
            .where(
                OpenLoop.user_id == user_id,
                OpenLoop.status == OpenLoopStatus.OPEN.value,
            )
            .order_by(OpenLoop.due_hint.asc().nulls_last(), OpenLoop.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user(
        self,
        user_id: UUID,
        status: str | None = None,
        limit: int = 100,
    ) -> list[OpenLoop]:
        """List a user's loops, optionally filtered by status (API listing).

        Args:
            user_id: Owner.
            status: Optional OpenLoopStatus value filter.
            limit: Cap on returned rows.

        Returns:
            Loops newest-first.
        """
        stmt = select(OpenLoop).where(OpenLoop.user_id == user_id)
        if status is not None:
            stmt = stmt.where(OpenLoop.status == status)
        stmt = stmt.order_by(OpenLoop.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def close_loop(
        self,
        loop_id: UUID,
        user_id: UUID,
        *,
        reason: str,
    ) -> bool:
        """Atomically close an OPEN loop (conditional UPDATE claim).

        Args:
            loop_id: Loop to close.
            user_id: Owner (ownership enforced in the WHERE clause).
            reason: closed_reason value (conversational | api).

        Returns:
            True when this call performed the OPEN→CLOSED transition,
            False when the loop was not found, not owned, or already left OPEN.
        """
        stmt = (
            update(OpenLoop)
            .where(
                OpenLoop.id == loop_id,
                OpenLoop.user_id == user_id,
                OpenLoop.status == OpenLoopStatus.OPEN.value,
            )
            .values(
                status=OpenLoopStatus.CLOSED.value,
                closed_reason=reason,
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.db.execute(stmt)
        claimed = bool(getattr(result, "rowcount", 0))
        if claimed:
            logger.info(
                "open_loop_closed",
                loop_id=str(loop_id),
                user_id=str(user_id),
                reason=reason,
            )
        return claimed

    async def expire_stale(
        self,
        user_id: UUID,
        *,
        cutoff: datetime,
    ) -> int:
        """Soft-expire OPEN loops untouched since ``cutoff`` (lazy expiry).

        Called opportunistically by the heartbeat fetcher — no dedicated
        scheduler job (ADR-139).

        Args:
            user_id: Owner.
            cutoff: UTC datetime; loops with ``updated_at`` older expire.

        Returns:
            Number of loops flipped to EXPIRED.
        """
        stmt = (
            update(OpenLoop)
            .where(
                OpenLoop.user_id == user_id,
                OpenLoop.status == OpenLoopStatus.OPEN.value,
                OpenLoop.updated_at < cutoff,
            )
            .values(
                status=OpenLoopStatus.EXPIRED.value,
                closed_reason="expired",
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.db.execute(stmt)
        expired = int(getattr(result, "rowcount", 0) or 0)
        if expired:
            logger.info(
                "open_loops_expired",
                user_id=str(user_id),
                count=expired,
            )
        return expired

    async def bump_nudged(self, loop_ids: list[UUID], *, user_id: UUID) -> None:
        """Record that a heartbeat notification surfaced these loops.

        Updates the anti-nag cooldown fields. No-op on an empty list.
        Ownership is enforced in the WHERE clause (defense-in-depth, same
        doctrine as ``close_loop``): foreign ids silently no-op.

        Args:
            loop_ids: Loops surfaced by the delivered notification.
            user_id: Owner — only their loops are bumped.
        """
        if not loop_ids:
            return
        stmt = (
            update(OpenLoop)
            .where(OpenLoop.id.in_(loop_ids), OpenLoop.user_id == user_id)
            .values(
                last_nudged_at=datetime.now(UTC),
                nudge_count=OpenLoop.nudge_count + 1,
            )
        )
        await self.db.execute(stmt)
