"""Persistence for the integrity register (ADR-263, lot 8).

Deliberately small. This table must read as EMPTY in production: a non-zero
count is the signal, not the norm, so there is no paging machinery, no
aggregate and no filter vocabulary to maintain — one write, two reads.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.integrity import IntegrityKind
from src.domains.agents.effects.models import AgentIntegrityEvent
from src.infrastructure.database.export_stream import stream_all


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

    @staticmethod
    def export_query(
        *,
        since: datetime | None,
        until: datetime | None,
        user_ids: list[uuid.UUID] | None,
    ) -> Select[tuple[AgentIntegrityEvent]]:
        """The filtered SELECT an extraction reads, without order or ceiling.

        Args:
            since: Inclusive lower bound on ``occurred_at``.
            until: Exclusive upper bound.
            user_ids: One, several, or (None) every account — including the
                rows that name none, which are exactly the ones an operator
                must not lose.

        Returns:
            The statement.
        """
        filters = []
        if since is not None:
            filters.append(AgentIntegrityEvent.occurred_at >= since)
        if until is not None:
            filters.append(AgentIntegrityEvent.occurred_at < until)
        if user_ids:
            filters.append(AgentIntegrityEvent.user_id.in_(user_ids))
        return select(AgentIntegrityEvent).where(*filters)

    def stream_for_export(
        self, query: Select[tuple[AgentIntegrityEvent]], *, batch: int
    ) -> AsyncIterator[AgentIntegrityEvent]:
        """Every gap the filters match, oldest first, at constant memory.

        The record that says the record itself is incomplete is the last one
        that may arrive incomplete, so it is never capped (ADR-273).

        Args:
            query: What :meth:`export_query` built.
            batch: How many rows the cursor buffers at a time.

        Yields:
            The rows, oldest first.
        """
        return stream_all(
            self.db,
            query,
            oldest_first=(
                AgentIntegrityEvent.occurred_at.asc(),
                AgentIntegrityEvent.id.asc(),
            ),
            batch=batch,
        )


__all__ = ["IntegrityRepository"]
