"""Actual metadata/file guards refuse uploads, foreign rows, absent files and stale byte sizes."""

from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.application.asset_download_schemas import AssetDownloadInput
from src.domains.agents.application.asset_download_snapshot import open_asset_snapshot
from src.domains.agents.application.command_service import CommandRejected
from src.domains.attachments.models import AttachmentOrigin, AttachmentStatus
from tests.integration.domains.attachments.test_keep_db import _file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "reason",
    [
        "valid",
        "upload",
        "foreign",
        "missing",
        "not_ready",
        "wrong_size",
        "foreign_path",
        "metadata_changed",
    ],
)
async def test_generated_browser_snapshot_is_owned_ready_exact_and_closed(
    async_session, test_user, monkeypatch, tmp_path, reason
):
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    actor = test_user.id
    row = await _file(async_session, tmp_path, actor)
    path = tmp_path / row.file_path
    if reason == "upload":
        row.origin = AttachmentOrigin.UPLOAD.value
    elif reason == "foreign":
        actor = uuid4()
    elif reason == "missing":
        path.unlink()
    elif reason == "not_ready":
        row.status = AttachmentStatus.UPLOADED
    elif reason == "wrong_size":
        path.write_bytes(b"new size")
    elif reason == "foreign_path":
        row.file_path = f"{uuid4()}/{row.stored_filename}"
    await async_session.commit()
    request = AssetDownloadInput(asset_id=row.id)
    if reason not in {"valid", "metadata_changed"}:
        with pytest.raises(CommandRejected):
            await open_asset_snapshot(async_session, actor, request)
        return
    selected, reader = await open_asset_snapshot(async_session, actor, request)
    await reader.close()
    assert reader.closed and selected.item.file_size == len(path.read_bytes())
    if reason == "metadata_changed":
        row.title = "Different approved identity"
        await async_session.commit()
        changed, reader = await open_asset_snapshot(async_session, actor, request)
        try:
            assert changed != selected and changed.state_digest != selected.state_digest
        finally:
            await reader.close()
