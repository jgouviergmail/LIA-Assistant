"""Persistence for the decision register (ADR-263, lot 6).

One statement, and the whole lot's semantics live in it: a HITL resumption
reuses the turn's ``run_id``, so the write is an UPSERT that MERGES rather than
replaces.

- ``started_at`` keeps the EARLIEST — the turn began when it began, not when it
  was resumed.
- ``ended_at`` takes the LATEST.
- ``duration_ms`` ACCUMULATES, because the wall clock between the two would
  count the time the turn spent waiting for a human as time it ran.
- ``segments`` increments, so an interrupted turn is legible as one.
- ``route``, ``plan_step_count`` and the two pointers are filled by
  ``COALESCE(new, existing)``: a later segment that learned nothing new must
  not blank what an earlier one established.

The arithmetic is server-side (``GREATEST``, ``LEAST``, ``+``), never
SELECT-then-write in Python: two concurrent segments of the same turn are rare
but possible, and a lost update here would silently understate a turn.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import AGENT_EFFECT_SCHEMA_VERSION
from src.domains.agents.effects.decisions import TurnDecision
from src.domains.agents.effects.models import AgentDecision
from src.infrastructure.database.export_window import newest_window


class DecisionRepository:
    """Reads and the single write of the decision register."""

    def __init__(self, db: AsyncSession) -> None:
        """Store the session this repository works through.

        Args:
            db: The session, owned by the caller.
        """
        self.db = db

    async def record(self, decision: TurnDecision, *, ended_at: datetime) -> None:
        """Write the turn, merging with an earlier segment if there was one.

        Args:
            decision: The live record the turn produced.
            ended_at: When this segment ended.
        """
        duration_ms = max(0, int((ended_at - decision.started_at).total_seconds() * 1000))
        statement = pg_insert(AgentDecision).values(
            id=uuid.uuid4(),
            user_id=decision.user_id,
            thread_id=decision.thread_id,
            run_id=decision.run_id,
            source=decision.source,
            execution_mode=decision.execution_mode,
            route=decision.route,
            plan_step_count=decision.plan_step_count,
            request_message_id=decision.request_message_id,
            response_message_id=decision.response_message_id,
            outcome=decision.outcome.value,
            stop_reason=decision.stop_reason,
            segments=1,
            started_at=decision.started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            schema_version=AGENT_EFFECT_SCHEMA_VERSION,
        )
        existing = statement.excluded
        current = AgentDecision.__table__.c
        await self.db.execute(
            statement.on_conflict_do_update(
                constraint="uq_agent_decisions_run",
                set_={
                    # The turn began when it began.
                    "started_at": func.least(current.started_at, existing.started_at),
                    "ended_at": func.greatest(current.ended_at, existing.ended_at),
                    # Accumulated, never re-measured from the wall clock: the
                    # gap between two segments is a human thinking, not the
                    # turn running.
                    "duration_ms": current.duration_ms + existing.duration_ms,
                    "segments": current.segments + 1,
                    # The latest segment's verdict wins — it is the one that saw
                    # how the turn actually ended.
                    "outcome": existing.outcome,
                    # But a segment that learned nothing new must not blank what
                    # an earlier one established.
                    "route": func.coalesce(existing.route, current.route),
                    # A resumption that ended normally must CLEAR the reason its
                    # first segment stopped for: the turn no longer stopped
                    # short. Hence the newest value wins, unlike the pointers.
                    "stop_reason": existing.stop_reason,
                    "plan_step_count": func.coalesce(
                        existing.plan_step_count, current.plan_step_count
                    ),
                    "request_message_id": func.coalesce(
                        existing.request_message_id, current.request_message_id
                    ),
                    "response_message_id": func.coalesce(
                        existing.response_message_id, current.response_message_id
                    ),
                },
            )
        )

    async def get_for_run(self, run_id: str) -> AgentDecision | None:
        """The turn with this identifier.

        Args:
            run_id: The turn.

        Returns:
            Its row, or None. The caller checks ownership: a register must not
            confirm that someone else's turn exists.
        """
        return (
            await self.db.execute(select(AgentDecision).where(AgentDecision.run_id == run_id))
        ).scalar_one_or_none()

    async def list_for_export(
        self,
        *,
        since: datetime | None,
        until: datetime | None,
        user_ids: list[uuid.UUID] | None,
        limit: int,
    ) -> list[AgentDecision]:
        """Rows for a technical export, oldest first.

        Oldest first, unlike the journal: an export is read forward, as a
        history, and a reader stitching two capped exports together needs the
        boundary to be the same one the period filter names.

        Args:
            since: Inclusive lower bound on ``started_at``.
            until: Exclusive upper bound.
            user_ids: One, several, or (None) every account.
            limit: Row ceiling, published in the file's header by the caller.

        Returns:
            The matching rows.
        """
        filters = []
        if since is not None:
            filters.append(AgentDecision.started_at >= since)
        if until is not None:
            filters.append(AgentDecision.started_at < until)
        if user_ids:
            filters.append(AgentDecision.user_id.in_(user_ids))

        # The most RECENT rows, returned oldest first (``export_window``).
        return await newest_window(
            self.db,
            select(AgentDecision).where(*filters),
            newest_first=(AgentDecision.started_at.desc(), AgentDecision.id.desc()),
            limit=limit,
        )

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[AgentDecision], int]:
        """One page of an account's turns, newest first, with the EXACT total.

        Args:
            user_id: Whose turns.
            limit: Page size.
            offset: Page offset.
            since: Inclusive lower bound on ``started_at``.
            until: Exclusive upper bound.

        Returns:
            ``(rows, total)`` — the total is an aggregate over the FILTERED set,
            never the page length (ADR-185).
        """
        filters = [AgentDecision.user_id == user_id]
        if since is not None:
            filters.append(AgentDecision.started_at >= since)
        if until is not None:
            filters.append(AgentDecision.started_at < until)

        total = (
            await self.db.execute(select(func.count()).select_from(AgentDecision).where(*filters))
        ).scalar_one()
        rows = await self.db.execute(
            select(AgentDecision)
            .where(*filters)
            .order_by(AgentDecision.started_at.desc(), AgentDecision.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(total)


__all__ = ["DecisionRepository"]
