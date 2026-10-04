"""Concurrent browser reports share one durable load on real PostgreSQL."""

import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domains.chat.models import MessageTokenSummary
from src.domains.chat.service import TrackingContext
from src.domains.connectors import map_load_metering as metering
from src.domains.google_api.models import GoogleApiUsageLog
from src.domains.google_api.pricing_service import GoogleApiPricingService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_concurrent_reports_and_lost_ack_count_one_load(async_engine, monkeypatch):
    import src.domains.chat.service as tracking

    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def context():
        async with factory() as session:
            yield session
            await session.commit()

    monkeypatch.setattr(metering, "get_db_context", context)
    monkeypatch.setattr(tracking, "get_db_context", context)
    monkeypatch.setattr(
        GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal("0.007"), Decimal("0.006"), Decimal("0.857")),
    )
    user = User(email=f"map-load-{uuid4().hex}@test.local", hashed_password="x")
    grant_id = uuid4()
    run_id = f"map_{grant_id.hex}"
    async with context() as session:
        session.add(user)
    try:
        await asyncio.gather(*(metering.record_map_load(grant_id, user.id) for _ in range(5)))
        # An HTTP acknowledgement can be lost after the first commit.
        await metering.record_map_load(grant_id, user.id)
        async with context() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(GoogleApiUsageLog)
                .where(GoogleApiUsageLog.run_id == run_id)
            )
            summary = await session.scalar(
                select(MessageTokenSummary).where(MessageTokenSummary.run_id == run_id)
            )
            assert count == 1
            assert summary is not None
            assert summary.user_id == user.id
            assert summary.google_api_requests == 1
            assert summary.google_api_cost_eur == Decimal("0.006")
            assert summary.total_prompt_tokens == summary.total_completion_tokens == 0
    finally:
        TrackingContext.cleanup_run_records(run_id)
        async with context() as session:
            await session.execute(delete(User).where(User.id == user.id))
