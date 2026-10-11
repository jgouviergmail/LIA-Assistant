"""A stop must wait for an accepted segment's disk and metadata transaction."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.domains.meetings.audio_store import MeetingAudioStore
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.schemas import MeetingStopRequest
from src.domains.meetings.service import MeetingService
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


async def test_stop_cannot_publish_while_an_accepted_segment_is_still_writing(
    async_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    committed_user_ids: list[UUID],
) -> None:
    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path))
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        owner = await _user(seed)
        committed_user_ids.append(owner)
        row = Meeting(
            user_id=owner,
            status=MeetingStatus.RECORDING,
            started_at=datetime.now(UTC),
            audio_format=MeetingAudioFormat.WEBM_OPUS,
            client_timezone="UTC",
        )
        seed.add(row)
        await seed.commit()
        identity = row.id
    storage = MeetingAudioStore(tmp_path)
    await storage.write_segment(owner, identity, 0, b"existing-audio")
    entered, release = asyncio.Event(), asyncio.Event()
    original = storage.write_segment

    async def writing(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    async with factory() as upload_db, factory() as stop_db:
        upload_service, stop_service = MeetingService(upload_db), MeetingService(stop_db)
        with patch.object(upload_service.store, "write_segment", writing):
            upload = asyncio.create_task(
                upload_service.accept_segment(owner, identity, sequence=0, body=b"last-audio")
            )
            await asyncio.wait_for(entered.wait(), 5)
            stopped = asyncio.create_task(
                stop_service.stop(owner, identity, MeetingStopRequest(segment_count=1))
            )
            try:
                await asyncio.sleep(0.1)
                assert not stopped.done(), "Stop committed before the accepted segment was stored"
            finally:
                release.set()
                results = await asyncio.wait_for(
                    asyncio.gather(upload, stopped, return_exceptions=True), 10
                )
            assert not any(isinstance(result, BaseException) for result in results)
    async with factory() as verify:
        actual = await MeetingService(verify).get(owner, identity)
        assert actual.status is MeetingStatus.STOPPED
        assert actual.segment_count == 1
    assert storage.segment_path(owner, identity, 0).read_bytes() == b"last-audio"
