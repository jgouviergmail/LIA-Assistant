"""The one writer of JEV's daily statistics: sorted, chunked, atomic UPSERTs (ADR-374).

Several workers flush the same keys at once. Each statement carries every key once
(PostgreSQL refuses ``ON CONFLICT DO UPDATE`` touching a row twice in one statement)
and in ONE global order — tables in a fixed order, keys sorted — so two concurrent
flushes take their row locks in the same order and cannot deadlock. The arithmetic is
the server's (``count = count + EXCLUDED.count``): never read, add, write.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.time_utils import now_utc
from src.domains.llm_config.jev_statistics_models import (
    JevJudgementDaily,
    JevObserverAgreementDaily,
    JevOutcomeDaily,
)
from src.infrastructure.database.models import BaseModel

#: (day, usage, gate key, bucket)
JudgementKey = tuple[date, str, str, int]
#: (day, usage, outcome)
OutcomeKey = tuple[date, str, str]
#: (day, usage, verdict, bucket, proposed)
AgreementKey = tuple[date, str, str, int, bool]

_JUDGEMENT_COLUMNS = ("day", "usage", "gate_key", "bucket")
_OUTCOME_COLUMNS = ("day", "usage", "outcome")
_AGREEMENT_COLUMNS = ("day", "usage", "verdict", "bucket", "proposed")
#: Rows per statement: 9 bound values per row at most, far under asyncpg's 32 767.
_ROWS_PER_STATEMENT = 1_000


@dataclass
class JevStatisticsBatch:
    """Counts waiting to be written, one entry per natural key."""

    judgements: Counter[JudgementKey] = field(default_factory=Counter)
    outcomes: Counter[OutcomeKey] = field(default_factory=Counter)
    agreement: Counter[AgreementKey] = field(default_factory=Counter)

    @property
    def rows(self) -> int:
        """How many rows the batch writes (one per key)."""
        return len(self.judgements) + len(self.outcomes) + len(self.agreement)

    def merge(self, other: JevStatisticsBatch) -> None:
        """Add ``other``'s counts to this batch; counts are additive, so nothing is lost."""
        self.judgements.update(other.judgements)
        self.outcomes.update(other.outcomes)
        self.agreement.update(other.agreement)


class JevStatisticsRepository:
    """Reads and writes the three daily counters; the caller owns the transaction.

    Three tables, so not a ``BaseRepository[T]`` (one model's CRUD): the same shape as
    ``DecisionRepository``.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session the caller commits.

        Args:
            db: The session every statement runs on.
        """
        self.db = db

    async def upsert(self, batch: JevStatisticsBatch) -> int:
        """Add every count of ``batch`` to its row, creating the rows that do not exist.

        Args:
            batch: The counts to add.

        Returns:
            How many rows were written (inserted or incremented).
        """
        written = await self._upsert(JevJudgementDaily, _JUDGEMENT_COLUMNS, batch.judgements)
        written += await self._upsert(JevOutcomeDaily, _OUTCOME_COLUMNS, batch.outcomes)
        written += await self._upsert(
            JevObserverAgreementDaily, _AGREEMENT_COLUMNS, batch.agreement
        )
        return written

    async def _upsert[K: tuple[date | str | int | bool, ...]](
        self,
        model: type[BaseModel],
        columns: Sequence[str],
        counts: Mapping[K, int],
    ) -> int:
        stamp = now_utc()
        rows = [
            {
                "id": uuid4(),
                "created_at": stamp,
                "updated_at": stamp,
                **dict(zip(columns, key, strict=True)),
                "count": count,
            }
            for key, count in sorted(counts.items())
            if count > 0
        ]
        for start in range(0, len(rows), _ROWS_PER_STATEMENT):
            statement = pg_insert(model).values(rows[start : start + _ROWS_PER_STATEMENT])
            statement = statement.on_conflict_do_update(
                index_elements=list(columns),
                set_={
                    "count": model.__table__.c["count"] + statement.excluded["count"],
                    "updated_at": statement.excluded["updated_at"],
                },
            )
            await self.db.execute(statement)
        return len(rows)
