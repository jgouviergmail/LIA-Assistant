"""A refused meeting deletion must retain its document and files atomically."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.service import MeetingService
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["valid", "transition_refused", "foreign_projection", "upload_projection"]
)
async def test_meeting_and_projection_share_one_delete_commit(
    async_session: AsyncSession,
    test_user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path / "rag"))
    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path / "audio"))
    owner = test_user.id
    refused = scenario != "valid"
    space = RAGSpace(user_id=owner, name="Meeting projection", kind="meetings")
    async_session.add(space)
    await async_session.flush()
    document = RAGDocument(
        user_id=owner,
        space_id=space.id,
        filename="minutes.md",
        original_filename="Minutes",
        file_size=4,
        content_type="text/markdown",
        status="ready",
        source_type="meeting",
    )
    if scenario == "foreign_projection":
        from tests.integration.domains.skills.test_per_account_skill_names import _user

        document.user_id = await _user(async_session)
    if scenario == "upload_projection":
        document.source_type = "upload"
    async_session.add(document)
    await async_session.flush()
    row = Meeting(
        user_id=owner,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        rag_document_id=document.id,
    )
    async_session.add(row)
    await async_session.commit()
    identity, projection = row.id, document.id
    file = tmp_path / "rag" / str(owner) / str(space.id) / "minutes.md"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"kept")
    if refused:
        if scenario == "transition_refused":
            monkeypatch.setattr(
                MeetingRepository, "delete_unless_leased", AsyncMock(return_value=False)
            )
        with pytest.raises(BaseAPIException):
            await MeetingService(async_session).delete(owner, identity)
        await async_session.rollback()
    else:
        await MeetingService(async_session).delete(owner, identity)
    assert (
        await async_session.get(Meeting, identity, populate_existing=True) is not None
    ) is refused
    assert (
        await async_session.get(RAGDocument, projection, populate_existing=True) is not None
    ) is refused
    assert file.exists() is refused
