"""A corrupted generated-file row cannot copy another account's disk content."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.attachments.models import Attachment, AttachmentOrigin, AttachmentStatus
from src.domains.attachments.owned_copies import copy_generated
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("escape", [False, True])
async def test_copy_refuses_a_corrupt_account_relative_source(
    async_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, escape: bool
) -> None:
    root = tmp_path / "files"
    root.mkdir()
    monkeypatch.setattr(settings, "attachments_storage_path", str(root))
    owner = UserFactory.create()
    async_session.add(owner)
    await async_session.flush()
    relative = "../private.png" if escape else f"{uuid4()}/private.png"
    victim = root / relative
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_bytes(b"private bytes")
    source = Attachment(
        user_id=owner.id,
        original_filename="visible.png",
        stored_filename="private.png",
        mime_type="image/png",
        file_size=13,
        file_path=relative,
        content_type="image",
        origin=AttachmentOrigin.GENERATED_IMAGE.value,
        status=AttachmentStatus.READY,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    async_session.add(source)
    await async_session.commit()
    with pytest.raises(BaseAPIException) as error:
        await copy_generated(async_session, user_id=owner.id, attachment_id=source.id)
    assert error.value.status_code == 404
    assert victim.read_bytes() == b"private bytes"
    assert (
        await async_session.scalar(
            select(func.count(Attachment.id)).where(Attachment.user_id == owner.id)
        )
        == 1
    )
