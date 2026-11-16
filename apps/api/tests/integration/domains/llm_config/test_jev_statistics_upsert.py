"""JEV's statistics UPSERT on a real PostgreSQL: concurrent workers, exact sums (ADR-374).

Eight workers flush overlapping keys at once, each on its own connection and committing
for real, five times over. What must hold: no deadlock (every statement takes its row
locks in one global order), no lost update (the server adds, never Python), and no
« ON CONFLICT DO UPDATE command cannot affect row a second time » (a key is carried
once per statement).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import date
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.llm_config.jev_statistics_models import (
    JevJudgementDaily,
    JevObserverAgreementDaily,
    JevOutcomeDaily,
)
from src.domains.llm_config.jev_statistics_repository import (
    JevStatisticsBatch,
    JevStatisticsRepository,
)
from src.domains.llm_config.jev_statistics_sink import JevStatisticsSink, flush_jev_statistics

pytestmark = pytest.mark.integration

WORKERS = 8
ROUNDS = 5
DAY = date(2026, 11, 8)


@pytest_asyncio.fixture
async def committed(
    async_engine: Any, test_database_url: str
) -> AsyncIterator[tuple[async_sessionmaker[AsyncSession], str]]:
    """Sessions whose writes really commit — a race needs several connections."""
    engine = create_async_engine(test_database_url, echo=False, pool_size=WORKERS)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    usage = f"test_{uuid4().hex[:12]}"
    yield maker, usage
    async with maker() as session:
        for model in (JevJudgementDaily, JevOutcomeDaily, JevObserverAgreementDaily):
            await session.execute(delete(model).where(model.usage == usage))
        await session.commit()
    await engine.dispose()


def _batch(usage: str, worker: int) -> JevStatisticsBatch:
    batch = JevStatisticsBatch()
    # Half the workers count their buckets upward, half downward: without one global
    # order of row locks, two such transactions would wait on each other.
    buckets = range(101) if worker % 2 == 0 else range(100, -1, -1)
    for bucket in buckets:
        batch.judgements[(DAY, usage, "priority", bucket)] += worker + 1
        batch.judgements[(DAY, usage, "category", (bucket * 7) % 101)] += 1
    batch.outcomes[(DAY, usage, "classified")] += worker + 1
    batch.agreement[(DAY, usage, "empty", worker % 3, worker % 2 == 0)] += 1
    return batch


async def _sum(session: AsyncSession, column: Any, *where: Any) -> int:
    return int(await session.scalar(select(func.coalesce(func.sum(column), 0)).where(*where)))


async def test_eight_concurrent_flushes_sum_exactly_without_deadlock(
    committed: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    maker, usage = committed

    async def worker(index: int) -> None:
        for _ in range(ROUNDS):
            async with maker() as session:
                await JevStatisticsRepository(session).upsert(_batch(usage, index))
                await session.commit()

    await asyncio.wait_for(asyncio.gather(*(worker(i) for i in range(WORKERS))), timeout=60)

    weight = sum(index + 1 for index in range(WORKERS))
    async with maker() as session:
        priority = (JevJudgementDaily.usage == usage, JevJudgementDaily.gate_key == "priority")
        assert await _sum(session, JevJudgementDaily.count, *priority) == ROUNDS * weight * 101
        rows = await session.scalar(
            select(func.count()).select_from(JevJudgementDaily).where(*priority)
        )
        assert rows == 101
        category = await session.execute(
            select(JevJudgementDaily.count).where(
                JevJudgementDaily.usage == usage, JevJudgementDaily.gate_key == "category"
            )
        )
        assert sorted(category.scalars()) == [ROUNDS * WORKERS] * 101
        assert (
            await _sum(session, JevOutcomeDaily.count, JevOutcomeDaily.usage == usage)
            == ROUNDS * weight
        )
        agreement = await _sum(
            session, JevObserverAgreementDaily.count, JevObserverAgreementDaily.usage == usage
        )
        assert agreement == ROUNDS * WORKERS


async def test_a_batch_without_counts_writes_no_row(
    committed: tuple[async_sessionmaker[AsyncSession], str],
) -> None:
    maker, usage = committed
    batch = JevStatisticsBatch()
    batch.outcomes[(DAY, usage, "classified")] = 0
    async with maker() as session:
        assert await JevStatisticsRepository(session).upsert(batch) == 0
        await session.commit()
        assert await _sum(session, JevOutcomeDaily.count, JevOutcomeDaily.usage == usage) == 0


@pytest.mark.parametrize("after_commit", [False, True], ids=["uncommitted", "committed"])
async def test_cancellation_restores_only_a_batch_that_cannot_have_committed(
    committed: tuple[async_sessionmaker[AsyncSession], str], after_commit: bool
) -> None:
    """Cancel real SQL work, or lose the reply after a real commit, without double counting."""
    maker, usage = committed
    pending = JevStatisticsSink()
    batch = JevStatisticsBatch()
    batch.outcomes[(DAY, usage, "classified")] = 1
    pending.give_back(batch)
    reached = asyncio.Event()
    blocked = asyncio.Event()
    session = maker()
    upsert = JevStatisticsRepository.upsert
    commit = session.commit

    async def controlled_upsert(
        repository: JevStatisticsRepository, counts: JevStatisticsBatch
    ) -> int:
        written = await upsert(repository, counts)
        if not after_commit:
            reached.set()
            await blocked.wait()
        return written

    async def controlled_commit() -> None:
        await commit()
        reached.set()
        await blocked.wait()

    with (
        patch("src.infrastructure.database.session.AsyncSessionLocal", return_value=session),
        patch.object(JevStatisticsRepository, "upsert", controlled_upsert),
        patch.object(session, "commit", controlled_commit),
    ):
        task = asyncio.create_task(flush_jev_statistics(pending))
        try:
            await asyncio.wait_for(reached.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            # The test owns its task even when the SQL operation never reaches the pause.
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    assert pending.pending_rows == (0 if after_commit else 1)
    async with maker() as reader:
        assert await _sum(reader, JevOutcomeDaily.count, JevOutcomeDaily.usage == usage) == int(
            after_commit
        )

    # The next flush retries only a rolled-back batch; an acknowledged-lost commit stays once.
    with patch("src.infrastructure.database.session.AsyncSessionLocal", maker):
        assert await flush_jev_statistics(pending) == (0 if after_commit else 1)
    async with maker() as reader:
        assert await _sum(reader, JevOutcomeDaily.count, JevOutcomeDaily.usage == usage) == 1
