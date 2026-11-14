"""Deferred generated-file deletion hides the row and retains its cleanup witness."""

from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.attachments.models import Attachment, AttachmentOrigin, AttachmentStatus
from src.domains.attachments.repository import AttachmentRepository
from src.domains.attachments.service import AttachmentService
from src.domains.users.models import User
from tests.helpers.committed_account_session import async_session as async_session
from tests.integration.domains.attachments.test_keep_db import _file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("stale_identity", [False, True])
async def test_generated_deletion_joins_the_approved_transaction_and_retains_bytes(
    async_session: AsyncSession,
    async_engine: AsyncEngine,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stale_identity: bool,
) -> None:
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    owner = test_user.id
    row = await _file(async_session, tmp_path, owner)
    if stale_identity:
        row.origin = AttachmentOrigin.UPLOAD.value
    await async_session.commit()
    identity, filename = row.id, row.file_path
    if stale_identity:
        await async_session.execute(
            update(Attachment)
            .where(Attachment.id == identity)
            .values(origin=AttachmentOrigin.GENERATED_IMAGE.value)
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
        assert row.origin == AttachmentOrigin.UPLOAD.value
    path = tmp_path / filename
    original = path.read_bytes()
    commits: list[bool] = []

    async def unexpected_commit() -> None:
        commits.append(True)

    monkeypatch.setattr(async_session, "commit", unexpected_commit)
    updated, skipped = await AttachmentService(async_session).delete_generated_batch(
        owner, [identity], commit=False
    )
    assert updated == [identity] and not skipped and not commits
    assert path.read_bytes() == original
    status = select(Attachment.status).where(Attachment.id == identity)
    assert await async_session.scalar(status) == AttachmentStatus.DELETING
    assert await AttachmentRepository(async_session).get_batch_for_user([identity], owner) == []
    async with AsyncSession(async_engine) as observer:
        assert await observer.scalar(status) == AttachmentStatus.READY

    await async_session.rollback()
    assert await async_session.scalar(status) == AttachmentStatus.READY
    assert path.read_bytes() == original
