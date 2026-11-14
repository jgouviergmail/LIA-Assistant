"""Account deletion cannot race the actual meeting-audio disk thread."""

import asyncio
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.service import MeetingService
from src.domains.users.account_cleanup import refuse_account_writers
from src.domains.users.file_writer_models import AccountFileWriter
from src.domains.users.models import User
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


async def test_cancelled_audio_upload_keeps_account_writer_until_disk_stops(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await commit_owner(async_engine, committed_user_ids)
    meeting_id = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            Meeting(
                id=meeting_id,
                user_id=owner,
                status=MeetingStatus.RECORDING,
                audio_format=MeetingAudioFormat.PCM_S16LE_16,
                started_at=datetime.now(UTC),
                client_timezone="UTC",
            )
        )
        await db.commit()
    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path))
    started, release = threading.Event(), threading.Event()
    original = Path.write_bytes

    def delayed(path: Path, body: bytes) -> int:
        started.set()
        assert release.wait(15)
        return original(path, body)

    monkeypatch.setattr(Path, "write_bytes", delayed)

    async def upload() -> None:
        async with AsyncSession(async_engine) as db:
            await MeetingService(db).accept_segment(owner, meeting_id, sequence=0, body=b"\x00\x00")
            await db.commit()

    task = asyncio.create_task(upload())
    try:
        assert await asyncio.to_thread(started.wait, 10)
        async with AsyncSession(async_engine) as observer:
            await observer.execute(update(User).where(User.id == owner).values(is_active=False))
            await observer.commit()
            with pytest.raises(BaseAPIException):
                await refuse_account_writers(observer, owner)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with AsyncSession(async_engine) as observer:
            assert (
                await observer.scalar(
                    select(AccountFileWriter.id).where(AccountFileWriter.user_id == owner)
                )
                is None
            )
            await refuse_account_writers(observer, owner)
            # An in-flight authenticated request cannot recreate the retired tree.
            with pytest.raises(BaseAPIException):
                await MeetingService(observer).accept_segment(
                    owner, meeting_id, sequence=1, body=b"\x00\x00"
                )
        assert len(list(tmp_path.rglob("*.bin"))) == 1
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
