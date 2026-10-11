"""Deferred generated-file deletion removes rows without early file cleanup or commit."""

import pytest
from sqlalchemy import select, update

from src.core.config import settings
from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.attachments.service import AttachmentService
from tests.integration.domains.attachments.test_keep_db import _file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("stale_identity", [False, True])
async def test_generated_deletion_joins_the_approved_transaction_and_retains_bytes(
    async_session, test_user, monkeypatch, tmp_path, stale_identity
):
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
    commits = []

    async def unexpected_commit():
        commits.append(True)

    monkeypatch.setattr(async_session, "commit", unexpected_commit)
    updated, skipped = await AttachmentService(async_session).delete_generated_batch(
        owner, [identity], commit=False
    )
    assert updated == [identity] and not skipped and not commits
    assert path.read_bytes() == original
    assert (
        await async_session.scalar(select(Attachment.id).where(Attachment.id == identity)) is None
    )
    await async_session.rollback()
    assert (
        await async_session.scalar(select(Attachment.id).where(Attachment.id == identity))
        == identity
    )
    assert path.read_bytes() == original
