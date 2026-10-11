"""Expired regeneration workers cannot publish into a later confirmed rebuild."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStage, MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_regeneration_claim_and_expiry_fence_all_later_effects(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        stage=MeetingStage.SYNTHESIZING,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current={"title": "Original", "participants": [], "sections": []},
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    repo = MeetingRepository(async_session)
    assert await repo.claim_regeneration(identity, worker_id="first", ttl_seconds=30)
    assert not await repo.claim_regeneration(identity, worker_id="second", ttl_seconds=30)
    await async_session.execute(
        update(Meeting)
        .where(Meeting.id == identity)
        .values(heartbeat_at=datetime.now(UTC) - timedelta(seconds=90))
    )
    await async_session.commit()
    assert not await repo.heartbeat_regeneration(identity, worker_id="first", ttl_seconds=30)
    assert not await repo.finish_regenerate(
        identity,
        worker_id="first",
        ttl_seconds=30,
        values={"report_current": {"title": "Obsolete"}},
    )
    assert await repo.clear_stale_regenerations(30) == 1
    assert await repo.begin_regenerate(identity)
    assert await repo.claim_regeneration(identity, worker_id="second", ttl_seconds=30)
    assert not await repo.fail_regenerate(
        identity, code="old_failure", message="", worker_id="first", ttl_seconds=30
    )
    assert not await repo.finish_regenerate(
        identity,
        worker_id="first",
        ttl_seconds=30,
        values={"report_current": {"title": "Obsolete"}},
    )
    assert await repo.finish_regenerate(
        identity,
        worker_id="second",
        ttl_seconds=30,
        values={"report_current": {"title": "Current", "participants": [], "sections": []}},
    )
    await async_session.refresh(row)
    assert row.report_current["title"] == "Current"
    assert row.stage is None and row.worker_id is None and row.heartbeat_at is None
