"""The person's attention, read on real rows: a recent alert holds an opening back only on request."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.heartbeat.models import HeartbeatNotification
from src.infrastructure.proactive.discussion_attention import attention_available

pytestmark = pytest.mark.integration


async def _alert(async_engine: AsyncEngine, owner: UUID, *, at: datetime) -> None:
    async with AsyncSession(async_engine) as db:
        db.add(
            HeartbeatNotification(
                user_id=owner,
                run_id="fictional-heartbeat-run",
                content="A fictional proactive notification",
                content_hash="0" * 64,
                sources_used="calendar",
                created_at=at,
            )
        )
        await db.commit()


async def test_a_recent_alert_no_longer_holds_an_opening_back_by_default(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    # Owner decision 2026-10-21: « no alert in the last 30 minutes » kept discussions
    # silent on every account LIA notifies often.
    now = datetime.now(UTC)
    await _alert(async_engine, discussion_owner, at=now - timedelta(minutes=1))
    async with AsyncSession(async_engine) as db:
        assert await attention_available(db, discussion_owner, now=now)


async def test_an_operator_gap_makes_a_recent_alert_hold_it_back(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    gap = 30
    monkeypatch.setattr(settings, "discussion_attention_alert_gap_minutes", gap)
    now = datetime.now(UTC)
    await _alert(async_engine, discussion_owner, at=now - timedelta(minutes=gap - 1))
    async with AsyncSession(async_engine) as db:
        assert not await attention_available(db, discussion_owner, now=now)
    # Past the gap, the same alert no longer counts.
    async with AsyncSession(async_engine) as db:
        assert await attention_available(db, discussion_owner, now=now + timedelta(minutes=gap))
