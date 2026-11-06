"""A cancelled turn's two doors write its spend once, on real PostgreSQL.

Production, 2026-11-04: the stream's commit and ``__aexit__`` ran 10 ms apart on the
same records, and the usage logs, the summary, the ledger and the statistics all
counted the turn twice.
"""

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domains.chat.models import MessageTokenSummary, TokenUsageLog, UserStatistics
from src.domains.chat.service import TrackingContext
from src.domains.chat.tracking_records import TokenUsageRecord
from src.domains.users.models import User

pytestmark = pytest.mark.integration


def _record() -> TokenUsageRecord:
    return TokenUsageRecord(
        node_name="response",
        model_name="a-model",
        prompt_tokens=100,
        completion_tokens=50,
        cached_tokens=0,
        cost_usd=0.02,
        cost_eur=0.01,
        usd_to_eur_rate=Decimal("0.5"),
    )


async def test_commit_and_exit_together_write_a_cancelled_turn_once(async_engine, monkeypatch):
    import src.domains.chat.service as tracking

    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def context():
        async with factory() as session:
            yield session
            await session.commit()

    monkeypatch.setattr(tracking, "get_db_context", context)
    user = User(email=f"doors-{uuid4().hex}@test.local", hashed_password="x", is_active=True)
    run_id = f"run_{uuid4().hex}"
    async with context() as session:
        session.add(user)
    tracker = TrackingContext(run_id, user.id, "session", None)
    tracker._node_records.extend(_record() for _ in range(6))
    try:
        await asyncio.gather(
            tracker.commit(),
            tracker.__aexit__(asyncio.CancelledError, asyncio.CancelledError(), None),
        )

        async with context() as session:
            rows = await session.scalar(
                select(func.count())
                .select_from(TokenUsageLog)
                .where(TokenUsageLog.run_id == run_id)
            )
            summary = await session.scalar(
                select(MessageTokenSummary).where(MessageTokenSummary.run_id == run_id)
            )
            statistics = await session.scalar(
                select(UserStatistics).where(UserStatistics.user_id == user.id)
            )
        assert rows == 6
        assert summary is not None
        assert summary.total_prompt_tokens == 600
        assert statistics is not None
        assert statistics.total_prompt_tokens == 600
    finally:
        TrackingContext.cleanup_run_records(run_id)
        async with context() as session:
            await session.execute(delete(User).where(User.id == user.id))
