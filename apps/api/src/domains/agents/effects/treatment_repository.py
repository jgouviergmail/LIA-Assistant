"""Writing the consultation register, one batch per turn (ADR-263, lot 4).

Deliberately the shortest repository in the domain. A treatment row is an
observation: there is nothing to claim, nothing to own, nothing to close, and
therefore no conditional statement to write. One ``INSERT`` of everything the
turn consulted, and the reads the two surfaces need.

The insert is chunked because a runaway ReAct loop is the one case that would
otherwise build a statement bounded only by how long the loop ran.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import AgentTreatment
from src.domains.agents.effects.period import period_conditions
from src.domains.agents.effects.treatments import Treatment
from src.infrastructure.database.export_window import newest_window

logger = structlog.get_logger(__name__)

#: Rows per statement. Large enough that an ordinary turn is one round trip,
#: small enough that a runaway turn cannot build an unbounded statement.
BATCH_SIZE: Final[int] = 500


class TreatmentRepository:
    """Persistence for what the assistant consulted."""

    def __init__(self, db: AsyncSession) -> None:
        """Store the session this repository writes through.

        Args:
            db: The session, owned by the caller.
        """
        self.db = db

    async def record_batch(self, rows: list[Treatment]) -> int:
        """Insert one turn's consultations.

        Args:
            rows: What the turn consulted, in the order it consulted it.

        Returns:
            How many rows were written.
        """
        if not rows:
            return 0
        payload = [self._as_row(row) for row in rows]
        for start in range(0, len(payload), BATCH_SIZE):
            await self.db.execute(insert(AgentTreatment), payload[start : start + BATCH_SIZE])
        return len(payload)

    @staticmethod
    def _as_row(treatment: Treatment) -> dict[str, Any]:
        """Render one collected consultation as a database row.

        Args:
            treatment: The collected observation.

        Returns:
            The column mapping. ``id`` is left to the model's own default.
        """
        return {
            "user_id": treatment.user_id,
            "thread_id": treatment.thread_id,
            "run_id": treatment.run_id,
            "source": treatment.source,
            "execution_mode": treatment.execution_mode,
            "tool_name": treatment.tool_name,
            "mutation_policy": treatment.mutation_policy,
            "outcome": treatment.outcome,
            "duration_ms": treatment.duration_ms,
            "occurred_at": treatment.occurred_at,
        }

    async def list_for_run(self, run_id: str) -> list[AgentTreatment]:
        """Everything one turn consulted, in the order it consulted it.

        Args:
            run_id: The turn.

        Returns:
            The rows, oldest first.
        """
        rows = await self.db.execute(
            select(AgentTreatment)
            .where(AgentTreatment.run_id == run_id)
            .order_by(AgentTreatment.occurred_at.asc())
        )
        return list(rows.scalars().all())

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int,
        offset: int,
        tool_name: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[list[AgentTreatment], int]:
        """One page of a user's consultations, newest first, with the EXACT total.

        Every filter is applied to the COUNT as well as to the page: a total
        computed over everything and displayed above a filtered list describes
        a set the reader cannot see (ADR-185).

        Args:
            user_id: Whose register.
            limit: Page size.
            offset: Page offset.
            tool_name: One capability, when the reader is filtering.
            since: Inclusive lower bound.
            until: Exclusive upper bound.

        Returns:
            The page and the exact total.
        """
        conditions = [AgentTreatment.user_id == user_id]
        if tool_name:
            conditions.append(AgentTreatment.tool_name == tool_name)
        conditions.extend(period_conditions(AgentTreatment.occurred_at, since, until))

        total = (
            await self.db.execute(
                select(func.count()).select_from(AgentTreatment).where(*conditions)
            )
        ).scalar_one()
        rows = await self.db.execute(
            select(AgentTreatment)
            .where(*conditions)
            .order_by(AgentTreatment.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(total)

    async def list_for_export(
        self,
        *,
        user_id: uuid.UUID | None = None,
        user_ids: Sequence[uuid.UUID] | None = None,
        tool_name: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int,
    ) -> list[AgentTreatment]:
        """Rows for an extraction, OLDEST first, capped.

        Same shape and same doctrine as the ledger's own export read: an
        export is read forwards where a journal page is read backwards, and
        the cap travels into the document so a truncation is stated.

        Args:
            user_id: One account.
            user_ids: Several accounts. Given both, the narrower wins.
            tool_name: One capability.
            since: Inclusive lower bound.
            until: Exclusive upper bound.
            limit: Row ceiling.

        Returns:
            The matching rows, oldest first.
        """
        conditions: list[Any] = []
        if user_id is not None:
            conditions.append(AgentTreatment.user_id == user_id)
        elif user_ids is not None:
            conditions.append(AgentTreatment.user_id.in_(list(user_ids)))
        if tool_name:
            conditions.append(AgentTreatment.tool_name == tool_name)
        conditions.extend(period_conditions(AgentTreatment.occurred_at, since, until))

        # The most RECENT rows, returned oldest first (``export_window``).
        return await newest_window(
            self.db,
            select(AgentTreatment).where(*conditions),
            newest_first=(AgentTreatment.occurred_at.desc(), AgentTreatment.id.desc()),
            limit=limit,
        )
