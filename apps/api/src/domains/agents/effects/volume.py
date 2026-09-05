"""What the two registers cost on disk (ADR-263, lot 4).

No purge job ships with the registers: the owner's arbitration is to keep
everything until the account is deleted, and to build a purge the day a
measurement asks for one. This module is that measurement — the alternative
being a retention policy chosen from an intuition about a number nobody has.

Two readings, and the row count is the one that had to be corrected.

- **The size is real** (``pg_total_relation_size``, indexes included), because
  a disk fills with indexes as readily as with rows.
- **The row count prefers the O(1) estimate, and refuses to publish it when it
  is not one.** ``pg_class.reltuples`` is ``-1`` until the first ``ANALYZE``,
  so a young table reported ZERO while holding rows — measured on the dev
  instance 2026-09-04: five consultations recorded, ``lia_ledger_bytes`` up
  from 32 768 to 73 728, ``lia_ledger_rows`` at 0. A gauge saying "0 rows,
  73 KB" is not an approximation, it is a contradiction, and this codebase
  does not ship counts that are wrong (ADR-185). A non-positive estimate is
  therefore replaced by an exact ``COUNT(*)``.

That rule is self-balancing rather than a compromise: a table large enough for
a sequential scan to cost anything has long since been analysed and reports a
positive estimate, so the exact count only ever runs on a table where it is
cheap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

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

#: One statement for both readings. ``reltuples`` is -1 before the first
#: ANALYZE, which is not a row count — the caller counts exactly instead.
_VOLUME_SQL: Final[str] = """
    SELECT c.relname,
           c.reltuples::bigint AS estimated_rows,
           pg_total_relation_size(c.oid) AS total_bytes
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relname = ANY(:tables)
      AND n.nspname = current_schema()
"""


@dataclass(frozen=True)
class TableVolume:
    """What one register occupies.

    Attributes:
        table: The register's table name.
        rows: Row count — the planner's estimate when it has one, an exact
            count when it does not. Never a figure that contradicts the size.
        size_bytes: Bytes the table and its indexes actually occupy.
    """

    table: str
    rows: int
    size_bytes: int


async def _exact_count(db: AsyncSession, table: str) -> int:
    """Count one register exactly, best-effort.

    Only reached for a table whose estimate is unusable, which in practice
    means a table small enough for the scan to be free.

    Args:
        db: Session of the periodic sync.
        table: One of :data:`LEDGER_TABLES` — never caller input, so the name
            is safe to inline (a bound parameter cannot name a relation).

    Returns:
        The exact number of rows, or 0 when the count itself failed. Zero is
        the honest degradation here: the SIZE, which is the figure an operator
        acts on, survives either way.
    """
    try:
        result = await db.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
        return int(result.scalar_one() or 0)
    except Exception as exc:  # noqa: BLE001 - supervision never breaks its host
        logger.warning("ledger_row_count_unavailable", table=table, error_type=type(exc).__name__)
        return 0


async def ledger_volume(db: AsyncSession) -> list[TableVolume]:
    """Read what both registers occupy.

    Best-effort: the periodic loop that calls this syncs many other metrics,
    and a register that cannot be measured must not take them down with it.

    Args:
        db: Session of the periodic sync.

    Returns:
        One entry per watched table, in :data:`LEDGER_TABLES` order — including
        a zero for a table PostgreSQL has no statistics on yet. A gauge that
        stops being published reads as "no data" on a panel, which an operator
        cannot tell apart from a broken exporter.
        Empty only when the reading itself failed.
    """
    try:
        result = await db.execute(text(_VOLUME_SQL), {"tables": list(LEDGER_TABLES)})
        measured = {
            str(name): (int(rows if rows is not None else -1), int(size or 0))
            for name, rows, size in result.all()
        }
    except Exception as exc:  # noqa: BLE001 - supervision never breaks its host
        logger.warning("ledger_volume_unavailable", error_type=type(exc).__name__, exc_info=True)
        return []

    volumes: list[TableVolume] = []
    for table in LEDGER_TABLES:
        seen = measured.get(table)
        if seen is None:
            # PostgreSQL has no catalogue entry for it: counting would only
            # produce a failing statement to log. Zero, and the gauge keeps
            # being published so the panel reads 0 rather than "no data".
            volumes.append(TableVolume(table=table, rows=0, size_bytes=0))
            continue
        estimate, size_bytes = seen
        rows = estimate if estimate > 0 else await _exact_count(db, table)
        volumes.append(TableVolume(table=table, rows=rows, size_bytes=size_bytes))
    return volumes
