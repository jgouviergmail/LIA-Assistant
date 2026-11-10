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
from datetime import date
from typing import Any
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
