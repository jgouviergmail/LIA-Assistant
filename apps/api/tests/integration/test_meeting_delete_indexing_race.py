"""An independent reindex cannot leave a new projection behind a deleted meeting."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.domains.meetings import indexing
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.service import MeetingService
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


async def test_reindex_and_delete_are_serialized_until_projection_reference_commit(
    async_engine: AsyncEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    committed_user_ids: list[UUID],
) -> None:
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path / "rag"))
    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path / "audio"))
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as seed:
        owner = await _user(seed)
        committed_user_ids.append(owner)
        space = RAGSpace(user_id=owner, name="Controlled meetings", kind="meetings")
        row = Meeting(
            user_id=owner,
            status=MeetingStatus.READY,
            started_at=datetime.now(UTC),
            audio_format=MeetingAudioFormat.WEBM_OPUS,
            client_timezone="UTC",
            report_current={"title": "Current", "participants": [], "sections": []},
        )
        seed.add_all([space, row])
        await seed.commit()
        identity = row.id

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        async with factory() as db:
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    monkeypatch.setattr(indexing, "get_db_context", database)
    monkeypatch.setattr(
        "src.domains.rag_spaces.processing.process_document", AsyncMock(return_value=False)
    )
    entered, release = asyncio.Event(), asyncio.Event()
    original_write = indexing._write_markdown

    async def write(path: Path, markdown: str) -> int:
        entered.set()
        await release.wait()
        return await original_write(path, markdown)

    monkeypatch.setattr(indexing, "_write_markdown", write)
    indexing_task = asyncio.create_task(indexing.index_minutes(identity))
    await asyncio.wait_for(entered.wait(), timeout=5)

    async def remove() -> None:
        async with database() as db:
            await MeetingService(db).delete(owner, identity)

    deletion_task = asyncio.create_task(remove())
    try:
        await asyncio.sleep(0.1)
        assert (
            not deletion_task.done()
        ), "Deletion must wait for the projection reference transaction"
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(indexing_task, deletion_task), timeout=10)
    async with factory() as check:
        assert await check.get(Meeting, identity) is None
        assert (
            list(
                (await check.scalars(select(RAGDocument).where(RAGDocument.user_id == owner))).all()
            )
            == []
        )
