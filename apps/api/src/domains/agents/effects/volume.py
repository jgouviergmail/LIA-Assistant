"""What the two registers cost on disk (ADR-263, lot 4).

No purge job ships with the registers: the owner's arbitration is to keep
everything until the account is deleted, and to build a purge the day a
measurement asks for one. This module is that measurement — the alternative
being a retention policy chosen from an intuition about a number nobody has.
It declares the tables; how a table is read — the planner's estimate, an exact
count where it has none, the real size — is
:mod:`src.infrastructure.database.table_volume`, shared with every watched table.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.table_volume import TableVolume, table_volume

#: The transparency tables, and nothing else: this gauge answers "what does
#: the transparency cost", not "how big is the database". The chain is one of
#: them because it is a cost the same arbitration created — notarising adds
#: ~387 bytes per register row, and that is a figure to watch rather than to
#: estimate (ADR-263, lot 5).
LEDGER_TABLES: Final[tuple[str, ...]] = (
    "agent_effects",
    "agent_treatments",
    "ledger_chain",
)

__all__ = ["LEDGER_TABLES", "TableVolume", "ledger_volume"]


async def ledger_volume(db: AsyncSession) -> list[TableVolume]:
    """Read what both registers occupy, in :data:`LEDGER_TABLES` order.

    Args:
        db: Session of the periodic sync.

    Returns:
        One entry per register table; empty only when the reading itself failed.
    """
    return await table_volume(db, LEDGER_TABLES)
