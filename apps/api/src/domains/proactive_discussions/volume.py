"""What the proactive discussions' execution tables occupy on disk (audit AC-034a).

Their runs, openings, outbox, spend reservations and budget buckets leave only with
the account. No retention ships with them: it is decided on this measurement
(AC-034b), the way the transparency registers' was (ADR-263), and read the same way
(:mod:`src.infrastructure.database.table_volume`).
"""

from __future__ import annotations

from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.table_volume import TableVolume, table_volume

#: The execution tables, one row per run, opening, delivery, reservation or budget
#: bucket of an account, purged with the account alone. The context tables are not
#: here: their items and observations expire and the maintenance sweep deletes them
#: (``context_store/maintenance.py``); what else they keep is the person's own act.
DISCUSSION_TABLES: Final[tuple[str, ...]] = (
    "discussion_runs",
    "discussion_openings",
    "discussion_outbox",
    "discussion_spend_reservations",
    "discussion_budget_buckets",
)


async def discussion_volume(db: AsyncSession) -> list[TableVolume]:
    """Read what each execution table occupies, in :data:`DISCUSSION_TABLES` order.

    Args:
        db: Session of the periodic sync.

    Returns:
        One entry per table; empty only when the reading itself failed.
    """
    return await table_volume(db, DISCUSSION_TABLES)
