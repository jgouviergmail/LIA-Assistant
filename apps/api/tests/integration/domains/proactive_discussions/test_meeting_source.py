"""Only current ready minutes feed discussions; no audio, GPS or generated fallback."""

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.meetings.discussion_source import MeetingDiscussionSource
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def seed_minutes(engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(engine) as db:
        for status, current in [
            (MeetingStatus.READY, {"title": "Fictional orchestra"}),
            (MeetingStatus.PROCESSING, {"title": "Do not expose unfinished minutes"}),
            (MeetingStatus.READY, None),
        ]:
            db.add(
                Meeting(
                    user_id=owner,
                    status=status,
                    audio_format=MeetingAudioFormat.PCM_S16LE_16,
                    started_at=NOW - timedelta(days=1),
                    client_timezone="UTC",
                    report_current=current,
                    report_generated={"title": "Obsolete generated minutes"},
                    transcript_encrypted="PRIVATE_TRANSCRIPT",
                    location_label="PRIVATE_PLACE",
                )
            )
        await db.commit()


async def test_ready_current_minutes_are_inferred_not_human_activity_proof(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "meetings_enabled", True)
    await seed_minutes(async_engine, discussion_owner)
    result = await MeetingDiscussionSource().read(
        read_request(discussion_owner, SourceKey.MEETINGS)
    )
    assert result.total == 1 and result.complete and len(result.items) == 1
    assert "Fictional orchestra" in result.items[0].excerpt
    assert result.items[0].assertion == "inferred" and result.coverage_kind == "dated_synthesis"
    assert not any(
        value in result.model_dump_json() for value in ("PRIVATE_", "Obsolete", "unfinished")
    )


async def test_meeting_search_does_not_open_location_data(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "meetings_enabled", True)
    await seed_minutes(async_engine, discussion_owner)
    scope = read_request(discussion_owner, SourceKey.MEETINGS).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.MEETINGS, operation="search", query="PRIVATE_PLACE"
            )
        }
    )
    result = await MeetingDiscussionSource().read(scope)
    assert result.status == "empty" and result.total == 0


async def test_email_delivery_bookkeeping_does_not_change_report_version(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "meetings_enabled", True)
    await seed_minutes(async_engine, discussion_owner)
    source, scope = MeetingDiscussionSource(), read_request(discussion_owner, SourceKey.MEETINGS)
    before = await source.read(scope)
    async with AsyncSession(async_engine) as db:
        row = await db.scalar(
            select(Meeting).where(
                Meeting.user_id == discussion_owner,
                Meeting.status == MeetingStatus.READY,
                Meeting.report_current.is_not(None),
            )
        )
        assert row is not None
        row.email_sent_at = NOW
        await db.commit()
    after = await source.read(scope)
    assert before.items[0].version == after.items[0].version
