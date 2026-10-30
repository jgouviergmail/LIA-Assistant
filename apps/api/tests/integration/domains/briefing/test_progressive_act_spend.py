"""The sections of one dashboard act bill under ONE run, and their flushes add up (PostgreSQL).

Each section request of a progressive act opens its own accounting on the act's
run id (``out_of_turn_spend``). Two requests of the same act therefore flush
twice into the same ``message_token_summary`` row: the second flush must ADD to
the first, never replace it, or a dashboard reading two billed sources reports
one (spec 2026-10-21 §5.8, D2).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import src.domains.chat.service as tracking
from src.domains.briefing.progressive import act_section, initial_cards
from src.domains.briefing.service import BriefingService
from src.domains.chat.models import MessageTokenSummary
from src.domains.chat.service import TrackingContext
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.google_api.models import GoogleApiUsageLog
from src.domains.google_api.pricing_service import GoogleApiPricingService
from src.domains.users.models import User
from tests.helpers.committed_users import commit_owner
from tests.unit.domains.briefing.page_load_harness import Rig
from tests.unit.domains.briefing.progressive_harness import MORNING

pytestmark = pytest.mark.integration

UNIT_EUR = Decimal("0.004")


@asynccontextmanager
async def _nothing_collected(_run_id: str) -> AsyncIterator[list[Any]]:
    yield []


async def test_act_spend_flushes_add_up(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session
            await session.commit()

    monkeypatch.setattr(tracking, "get_db_context", context)
    monkeypatch.setattr(
        GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal("0.005"), UNIT_EUR, Decimal("0.8")),
    )
    owner = await commit_owner(async_engine, committed_user_ids)
    async with context() as session:
        user = await session.get(User, owner)
    assert user is not None

    rig = Rig()

    def billed(name: str, api: str) -> AsyncMock:
        async def fetch(*_args: object, **_kwargs: object) -> Any:
            track_google_api_call(api, f"/{name}")
            await asyncio.sleep(rig.latency_s)
            return rig.payloads[name]

        return AsyncMock(side_effect=fetch)

    with (
        rig.installed(),
        patch("src.domains.briefing.service.fetch_weather", billed("weather", "weather")),
        patch("src.domains.briefing.service.fetch_agenda", billed("agenda", "geocoding")),
        patch("src.domains.briefing.progressive.consultation_collector", _nothing_collected),
        patch("src.domains.briefing.progressive.file_briefing_act", AsyncMock()),
    ):
        initial = await initial_cards(BriefingService(user), now=MORNING)
        runs: list[str] = []
        real_spend = tracking.TrackingContext

        def spy(run_id: str, *args: Any, **kwargs: Any) -> TrackingContext:
            runs.append(run_id)
            return real_spend(run_id, *args, **kwargs)

        with patch.object(tracking, "TrackingContext", spy):
            await asyncio.gather(
                act_section(BriefingService(user), "weather", act=initial.act, now=MORNING),
                act_section(BriefingService(user), "agenda", act=initial.act, now=MORNING),
            )

    assert len(runs) == 2 and runs[0] == runs[1]
    act_id = runs[0]
    try:
        async with context() as session:
            summary = await session.scalar(
                select(MessageTokenSummary).where(MessageTokenSummary.run_id == act_id)
            )
            logged = await session.scalar(
                select(func.count())
                .select_from(GoogleApiUsageLog)
                .where(GoogleApiUsageLog.run_id == act_id)
            )
        assert summary is not None
        assert summary.user_id == owner
        assert summary.google_api_requests == 2
        assert summary.google_api_cost_eur == 2 * UNIT_EUR
        assert logged == 2
    finally:
        TrackingContext.cleanup_run_records(act_id)
