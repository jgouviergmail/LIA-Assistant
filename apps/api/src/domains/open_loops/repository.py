"""Open Loops repository — atomic status transitions + hot-path listings.

Status transitions are server-side conditional UPDATEs (never SELECT →
mutate → flush): a loop leaves OPEN exactly once, whatever the concurrency
(extractor closure vs API close vs lazy expiry). Same doctrine as
``scheduled_actions/repository.py``.
"""

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.shared.aggregates import NameActivity

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

    async def aggregate_open_by_counterparty(self, user_id: UUID) -> list[NameActivity]:
        """Exact per-counterparty activity over ALL of a user's OPEN loops.

        The personal CRM used to count from a capped page of rows, so a busy
        user's card could under-report. An aggregate answers the question the
        card actually asks — how many, how recently — over the whole set, and
        returns one row per DISTINCT SPELLING rather than per loop, so the
        payload is bounded by the address book, not by the backlog.

        Rides the partial index ``ix_open_loops_user_open`` (user_id WHERE
        status = 'open').

        Args:
            user_id: Owner.

        Returns:
            One entry per non-blank counterparty spelling.
        """
        stmt = (
            select(
                OpenLoop.counterparty,
                func.count().label("total"),
                func.max(OpenLoop.created_at).label("last_at"),
            )
            .where(
                OpenLoop.user_id == user_id,
                OpenLoop.status == OpenLoopStatus.OPEN.value,
                OpenLoop.counterparty.is_not(None),
                func.btrim(OpenLoop.counterparty) != "",
            )
            .group_by(OpenLoop.counterparty)
        )
        rows = (await self.db.execute(stmt)).all()
        return [
            NameActivity(raw_name=row.counterparty, count=row.total, last_at=row.last_at)
            for row in rows
        ]

    async def list_open_for_counterparties(
        self,
        user_id: UUID,
        counterparties: list[str],
        limit: int,
    ) -> list[OpenLoop]:
        """OPEN loops whose counterparty is EXACTLY one of the given spellings.

        Identity folding stays in Python: the caller resolved the spellings
        with :func:`fold_name` from the aggregate above, so this query matches
        raw strings and introduces no second, silently diverging notion of
        "same person" in SQL.

        Args:
            user_id: Owner.
            counterparties: Raw spellings, as stored.
            limit: Cap on returned rows.

        Returns:
            Matching OPEN loops, earliest deadline first (NULLs last).
        """
        if not counterparties:
            return []
        stmt = (
            select(OpenLoop)
            .where(
                OpenLoop.user_id == user_id,
                OpenLoop.status == OpenLoopStatus.OPEN.value,
                OpenLoop.counterparty.in_(counterparties),
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
            reason: closed_reason value (conversational | api | dismissed).

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
            # UXR Lot 7 (B5): closure counters — this chokepoint covers the
            # API (api/dismissed) and the conversational extractor alike.
            # Metrics emission must never fail a persistence path.
            with suppress(Exception):
                from src.infrastructure.observability.metrics_registry import (
                    track_open_loop_closure,
                )

                track_open_loop_closure(reason)
        return claimed

    async def update_loop(
        self,
        loop_id: UUID,
        user_id: UUID,
        *,
        subject: str | None = None,
        due_hint: datetime | None = None,
        clear_due_hint: bool = False,
    ) -> bool:
        """Correct what the extractor got wrong, on an OPEN loop.

        The ledger fills itself from conversation, and conversation is
        approximate: a subject can come out garbled and a deadline can be read
        from "d'ici vendredi" as the wrong Friday. Only those two are editable —
        changing the direction or the counterparty would not be a correction but
        a different commitment.

        Same claim shape as :meth:`close_loop`: ownership AND status live in the
        WHERE clause, so a closed, expired or foreign loop is never touched and
        the caller learns it from the return value.

        Args:
            loop_id: Loop to edit.
            user_id: Owner (enforced in the WHERE clause).
            subject: New wording, when the caller sends one.
            due_hint: New advisory deadline (UTC), when the caller sends one.
            clear_due_hint: Explicitly drop the deadline. Distinguishes "leave it
                alone" (the default) from "there is no deadline after all", which
                a nullable field cannot express with ``None`` alone.

        Returns:
            True when the row was claimed and updated, False when nothing
            matched — or when the patch was empty, which is a no-op rather than
            an UPDATE that would only bump ``updated_at``.
        """
        values: dict[str, Any] = {}
        if subject is not None:
            values["subject"] = subject
        if clear_due_hint:
            values["due_hint"] = None
        elif due_hint is not None:
            values["due_hint"] = due_hint
        if not values:
            return False

        values["updated_at"] = datetime.now(UTC)
        stmt = (
            update(OpenLoop)
            .where(
                OpenLoop.id == loop_id,
                OpenLoop.user_id == user_id,
                OpenLoop.status == OpenLoopStatus.OPEN.value,
            )
            .values(**values)
        )
        result = await self.db.execute(stmt)
        claimed = bool(getattr(result, "rowcount", 0))
        if claimed:
            # Field NAMES only: a subject quotes what the user said out loud.
            logger.info(
                "open_loop_updated",
                loop_id=str(loop_id),
                user_id=str(user_id),
                fields=sorted(k for k in values if k != "updated_at"),
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
            # Metrics emission must never fail a persistence path.
            with suppress(Exception):
                from src.infrastructure.observability.metrics_registry import (
                    track_open_loop_closure,
                )

                track_open_loop_closure("expired", count=expired)
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
