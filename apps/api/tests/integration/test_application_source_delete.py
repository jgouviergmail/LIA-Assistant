"""One confirmed source removal atomically deletes only its exact indexed documents."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.source_delete import (
    execute_source_deletion,
    prepare_source_deletion,
)
from src.domains.agents.application.source_delete_schemas import SourceDeleteInput
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.storage_paths import stored_file_path
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "changed",
        "busy",
        "ack_lost",
        "ack_cancelled",
        "ack_failed",
        "disabled",
        "expired",
        "revoked",
        "source_busy",
        "cleanup_pending",
    ],
)
async def test_source_deletion_keeps_bytes_until_ack_and_preserves_unrelated_content(
    async_session, test_user, monkeypatch, tmp_path, kind, scenario
):
    for flag in ("application_tools_enabled", "rag_spaces_enabled"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    keys = (
        {"folder_id": "root", "folder_name": "Root"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Label"}
    )
    source = model(user_id=owner, space_id=space_id, sync_status="idle", **keys)
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    reference = "drive_source_id" if kind == "drive" else "mail_source_id"
    document = RAGDocument(
        user_id=owner,
        space_id=space_id,
        filename="removed.txt",
        original_filename="Literal document",
        content_type="text/plain",
        file_size=3,
        status="ready",
        **{reference: source_id},
    )
    unrelated = RAGDocument(
        user_id=owner,
        space_id=space_id,
        filename="retained.txt",
        original_filename="Unrelated document",
        content_type="text/plain",
        file_size=3,
        status="ready",
    )
    async_session.add_all([document, unrelated])
    await async_session.commit()
    removed_id, retained_id = document.id, unrelated.id
    removed = stored_file_path(owner, space_id, document.filename)
    retained = stored_file_path(owner, space_id, unrelated.filename)
    removed.parent.mkdir(parents=True)
    removed.write_bytes(b"old")
    retained.write_bytes(b"yes")
    draft = await prepare_source_deletion(
        async_session, owner, SourceDeleteInput(space_id=space_id, source_id=source_id, kind=kind)
    )
    await async_session.commit()
    if scenario == "changed":
        document.original_filename = "Changed"
        await async_session.commit()
    elif scenario == "busy":
        document.status = "processing"
        await async_session.commit()
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "revoked":
        test_user.is_active = False
        await async_session.commit()
    elif scenario == "source_busy":
        source.sync_status = "syncing"
        await async_session.commit()
    elif scenario == "cleanup_pending":

        async def refuse_cleanup(*args):
            return False

        monkeypatch.setattr(
            "src.domains.agents.application.document_delete.cleanup_deleted_document_file",
            refuse_cleanup,
        )
    original = async_session.commit

    async def commit():
        assert removed.read_bytes() == b"old"
        assert retained.read_bytes() == b"yes"
        if scenario == "ack_failed":
            raise OSError("controlled commit failure")
        await original()
        if scenario == "ack_lost":
            raise OSError("controlled acknowledgement loss")
        if scenario == "ack_cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr(async_session, "commit", commit)
    receipt = PreferenceWriteReceipt()
    if scenario in {"valid", "cleanup_pending"}:
        await execute_source_deletion(async_session, owner, draft, receipt)
        assert receipt.committed is True
        assert receipt.values["source_to_delete"]["documents_deleted"] == 1
        assert removed.exists() is (scenario == "cleanup_pending")
        assert receipt.values["source_to_delete"]["file_cleanup_pending"] is (
            scenario == "cleanup_pending"
        )
    else:
        with pytest.raises((CommandRejected, ValueError, AuthorizationError)):
            await execute_source_deletion(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert receipt.committed is False
        assert removed.read_bytes() == b"old"
    assert retained.read_bytes() == b"yes"
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == retained_id))
        == retained_id
    )
    remains = scenario in {
        "changed",
        "busy",
        "ack_failed",
        "disabled",
        "expired",
        "revoked",
        "source_busy",
    }
    assert (
        await async_session.scalar(select(model.id).where(model.id == source_id)) is not None
    ) is remains
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == removed_id))
        is not None
    ) is remains
