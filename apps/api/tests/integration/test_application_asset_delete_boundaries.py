"""Deletion refuses mixed ownership, ambiguous paths and authority lost after consent."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.asset_delete import (
    execute_asset_deletion,
    prepare_asset_deletion,
)
from src.domains.agents.application.asset_delete_schemas import AssetDeleteInput
from src.domains.agents.application.command_service import CommandRejected
from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.attachments.test_gallery_queries_db import _user
from tests.integration.domains.attachments.test_keep_db import _file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "reason",
    [
        "foreign",
        "upload",
        "missing",
        "foreign_path",
        "shared_path",
        "oversized",
        "disabled",
        "revoked",
        "expired",
        "absent_file",
    ],
)
async def test_exact_generated_delete_boundaries(
    async_session, test_user, monkeypatch, tmp_path, reason
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    actor = test_user.id
    row = await _file(async_session, tmp_path, actor)
    identity, path = row.id, tmp_path / row.file_path
    ids = (identity,)
    if reason == "foreign":
        other = await _file(async_session, tmp_path, await _user(async_session))
        ids += (other.id,)
    elif reason == "upload":
        other = await _file(async_session, tmp_path, actor, origin=AttachmentOrigin.UPLOAD)
        ids += (other.id,)
    elif reason == "missing":
        ids += (uuid4(),)
    elif reason == "foreign_path":
        row.file_path = f"{uuid4()}/{row.stored_filename}"
    elif reason == "shared_path":
        other = await _file(async_session, tmp_path, actor)
        other.file_path = row.file_path
    elif reason == "oversized":
        monkeypatch.setattr(
            "src.domains.agents.application.asset_delete_scope.ASSET_DELETE_MAX_BYTES", 1
        )
    elif reason == "absent_file":
        path.unlink()
    await async_session.commit()
    if reason in {"foreign", "upload", "missing", "foreign_path", "shared_path", "oversized"}:
        with pytest.raises((CommandRejected, ValueError)):
            await prepare_asset_deletion(async_session, actor, AssetDeleteInput(ids=ids))
        assert path.exists()
        assert (
            await async_session.scalar(select(Attachment.id).where(Attachment.id == identity))
            == identity
        )
        return
    draft = await prepare_asset_deletion(async_session, actor, AssetDeleteInput(ids=ids))
    await async_session.commit()
    if reason == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif reason == "revoked":
        test_user.is_active = False
        await async_session.commit()
    elif reason == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    receipt = PreferenceWriteReceipt()
    if reason == "absent_file":
        await execute_asset_deletion(async_session, actor, draft, receipt)
        assert receipt.committed and not receipt.values["assets_to_delete"]["file_cleanup_pending"]
    else:
        with pytest.raises((CommandRejected, AuthorizationError)):
            await execute_asset_deletion(async_session, actor, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and path.exists()
