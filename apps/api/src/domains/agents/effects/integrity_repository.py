"""Persistence for the integrity register (ADR-263, lot 8).

Deliberately small. This table must read as EMPTY in production: a non-zero
count is the signal, not the norm, so there is no paging machinery, no
aggregate and no filter vocabulary to maintain — one write, two reads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.integrity import IntegrityKind
from src.domains.agents.effects.models import AgentIntegrityEvent
from src.infrastructure.database.export_window import newest_window


class IntegrityRepository:
    """One write and the two reads the surfaces need."""

    def __init__(self, db: AsyncSession) -> None:
        """Store the session this repository works through.

        Args:
            db: The session, owned by the caller.
        """
        self.db = db

    async def record(
        self,
        *,
        kind: IntegrityKind,
        user_id: uuid.UUID | None,
        run_id: str | None,
        detail: str | None,
    ) -> None:
        """Persist one observed gap.

        Args:
            kind: Which gap.
            user_id: Whose account, when the detection knew.
            run_id: Which turn, when the detection knew.
            detail: A short bounded classification — never content. Truncated
                at the column's width rather than rejected: losing the whole
                row over a long reason code would be the wrong trade.
        """
        self.db.add(
            AgentIntegrityEvent(
                kind=kind.value,
                user_id=user_id,
                run_id=run_id,
                detail=(detail or None) and detail[:200],
                occurred_at=datetime.now(UTC),
            )
        )

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        """How many gaps this account's record carries.

        Args:
            user_id: Whose record.

        Returns:
            The EXACT count (ADR-185) — the surfaces state a number, so it is
            an aggregate and never a page length.
        """
        return int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(AgentIntegrityEvent)
                    .where(AgentIntegrityEvent.user_id == user_id)
                )
            ).scalar_one()
        )

    async def list_for_export(
        self,
        *,
        since: datetime | None,
        until: datetime | None,
        user_ids: list[uuid.UUID] | None,
        limit: int,
    ) -> list[AgentIntegrityEvent]:
        """Gaps for an extraction, oldest first.

        The same shape the other records offer, so one extraction reads five
        sources through one contract.

        Args:
            since: Inclusive lower bound on ``occurred_at``.
            until: Exclusive upper bound.
            user_ids: One, several, or (None) every account — including the
                rows that name none, which are exactly the ones an operator
                must not lose.
            limit: Row ceiling, published in the file's header by the caller.

        Returns:
            The matching rows.
        """
        filters = []
        if since is not None:
            filters.append(AgentIntegrityEvent.occurred_at >= since)
        if until is not None:
            filters.append(AgentIntegrityEvent.occurred_at < until)
        if user_ids:
            filters.append(AgentIntegrityEvent.user_id.in_(user_ids))

        # The most RECENT rows, returned oldest first (``export_window``).
        return await newest_window(
            self.db,
            select(AgentIntegrityEvent).where(*filters),
            newest_first=(
                AgentIntegrityEvent.occurred_at.desc(),
                AgentIntegrityEvent.id.desc(),
            ),
            limit=limit,
        )


__all__ = ["IntegrityRepository"]
