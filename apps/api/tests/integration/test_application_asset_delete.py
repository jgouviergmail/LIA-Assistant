"""Generated-file deletion preserves bytes until known exact approved SQL effects."""

import asyncio

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.asset_delete import (
    execute_asset_deletion,
    prepare_asset_deletion,
)
from src.domains.agents.application.asset_delete_schemas import AssetDeleteInput
from src.domains.agents.application.command_service import CommandRejected
from src.domains.attachments.models import Attachment
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.attachments.test_keep_db import _file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "metadata_changed",
        "file_changed",
        "ack_lost",
        "cancelled",
        "before_commit_failed",
        "cleanup_pending",
        "post_ack_replaced",
    ],
)
async def test_generated_deletion_exact_file_identity_and_acknowledgement(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    actor = test_user.id
    row = await _file(async_session, tmp_path, actor)
    neighbor = await _file(async_session, tmp_path, actor)
    await async_session.commit()
    identity, neighbor_id = row.id, neighbor.id
    path, other_path = tmp_path / row.file_path, tmp_path / neighbor.file_path
    original, other_bytes = path.read_bytes(), other_path.read_bytes()
    draft = await prepare_asset_deletion(async_session, actor, AssetDeleteInput(ids=(identity,)))
    await async_session.commit()
    if scenario == "metadata_changed":
        row.title = "Changed after approval"
        await async_session.commit()
    elif scenario == "file_changed":
        path.write_bytes(b"changed")
        original = b"changed"
    elif scenario == "cleanup_pending":

        async def refuse_cleanup(*args):
            return False

        monkeypatch.setattr(
            "src.domains.agents.application.asset_delete.cleanup_asset_file", refuse_cleanup
        )
    commit_original = async_session.commit

    async def commit():
        assert path.read_bytes() == original
        if scenario == "before_commit_failed":
            raise OSError("controlled failure")
        await commit_original()
        if scenario == "post_ack_replaced":
            path.write_bytes(b"replacement")
        if scenario == "ack_lost":
            raise OSError("controlled acknowledgement loss")
        if scenario == "cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr(async_session, "commit", commit)
    receipt = PreferenceWriteReceipt()
    if scenario in {"valid", "cleanup_pending", "post_ack_replaced"}:
        await execute_asset_deletion(async_session, actor, draft, receipt)
        assert receipt.committed and path.exists() is (scenario != "valid")
        assert receipt.values["assets_to_delete"]["file_cleanup_pending"] is (scenario != "valid")
        if scenario == "post_ack_replaced":
            assert path.read_bytes() == b"replacement"
    else:
        with pytest.raises(CommandRejected):
            await execute_asset_deletion(async_session, actor, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and path.read_bytes() == original
    committed = scenario in {
        "valid",
        "ack_lost",
        "cancelled",
        "cleanup_pending",
        "post_ack_replaced",
    }
    assert (
        await async_session.scalar(select(Attachment.id).where(Attachment.id == identity)) is None
    ) is committed
    assert (
        await async_session.scalar(select(Attachment.id).where(Attachment.id == neighbor_id))
        == neighbor_id
    )
    assert other_path.read_bytes() == other_bytes
