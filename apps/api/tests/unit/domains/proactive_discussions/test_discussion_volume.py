"""What the proactive discussions' execution tables occupy is published (audit AC-034a).

Their runs, openings, outbox, spend reservations and budget buckets leave only with the
account: no retention ships, and none is decided without a measurement (AC-034b). They are
measured the way the transparency registers are — the planner's row estimate, an exact
count where it has none, and the real size, indexes included — by the same reader.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.proactive_discussions.volume import DISCUSSION_TABLES, discussion_volume
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import Base
from src.infrastructure.database.table_volume import TableVolume
from src.infrastructure.observability import lifetime_metrics
from src.infrastructure.observability.metrics_proactive_discussions import (
    proactive_discussion_table_bytes,
    proactive_discussion_table_rows,
)

pytestmark = pytest.mark.unit

EXECUTION_TABLES = {
    "discussion_runs",
    "discussion_openings",
    "discussion_outbox",
    "discussion_spend_reservations",
    "discussion_budget_buckets",
}


class _Result:
    """Answers only what the reader asks: the catalogue rows, or one exact count."""

    def __init__(self, rows: list[tuple[str, int, int]], scalar: int = 0) -> None:
        self._rows, self._scalar = rows, scalar

    def all(self) -> list[tuple[str, int, int]]:
        return self._rows

    def scalar_one(self) -> int:
        return self._scalar


def _db(rows: list[tuple[str, int, int]]) -> AsyncMock:
    """A session whose every statement answers ``rows`` — the catalogue reading."""
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = _Result(rows)
    return session


def test_the_execution_tables_are_the_watched_set() -> None:
    assert set(DISCUSSION_TABLES) == EXECUTION_TABLES


def test_every_watched_table_is_one_the_application_declares() -> None:
    """A misspelt name would read as an empty table for ever: nothing would say so."""
    import_all_models()

    assert set(DISCUSSION_TABLES) <= set(Base.metadata.tables)


async def test_their_volume_is_read_like_the_registers() -> None:
    rows = [
        (table, 10 * index + 1, 8192 * (index + 1)) for index, table in enumerate(DISCUSSION_TABLES)
    ]

    volumes = await discussion_volume(_db(rows))

    assert volumes == [TableVolume(table, rows_, size) for table, rows_, size in rows]


async def test_the_periodic_sync_publishes_rows_and_bytes_per_table() -> None:
    rows = [(table, 7, 16_384) for table in DISCUSSION_TABLES]

    await lifetime_metrics._sync_discussion_volume_from_db(_db(rows))

    for table in DISCUSSION_TABLES:
        assert proactive_discussion_table_rows.labels(table=table)._value.get() == 7
        assert proactive_discussion_table_bytes.labels(table=table)._value.get() == 16_384
