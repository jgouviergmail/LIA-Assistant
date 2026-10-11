"""An exact approved source unlink keeps document identity and treats lost ACK as unknown."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.source_unlink import (
    execute_source_unlink,
    prepare_source_unlink,
)
from src.domains.agents.application.source_unlink_schemas import SourceUnlinkInput
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.storage_paths import stored_file_path
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "stale",
        "syncing",
        "expired",
        "disabled",
        "ack_lost",
        "ack_cancel",
        "corrupt_reference",
    ],
)
async def test_exact_source_unlink_keeps_documents_and_never_guesses_commit(
    async_session, test_user, monkeypatch, tmp_path, kind, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination", is_active=False)
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    names = (
        {"folder_id": "folder", "folder_name": "Literal folder"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Literal label"}
    )
    source = model(space_id=space_id, user_id=owner, **names)
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    reference = RAGDocument.drive_source_id if kind == "drive" else RAGDocument.mail_source_id
    document = RAGDocument(
        space_id=space_id,
        user_id=owner,
        filename="f.txt",
        original_filename="f.txt",
        file_size=4,
        content_type="text/plain",
        source_type=kind,
        **{reference.key: source_id},
    )
    async_session.add(document)
    await async_session.commit()
    document_id = document.id
    file = stored_file_path(owner, space_id, "f.txt")
    file.parent.mkdir(parents=True)
    file.write_bytes(b"data")
    draft = await prepare_source_unlink(
        async_session, owner, SourceUnlinkInput(space_id=space_id, source_id=source_id, kind=kind)
    )
    assert "state_digest" not in str(draft.before) and "state_digest" not in str(draft.after)
    if scenario == "stale":
        name_column = model.folder_name if kind == "drive" else model.label_name
        await async_session.execute(
            update(model).where(model.id == source_id).values({name_column.key: "Changed"})
        )
        await async_session.commit()
    elif scenario == "syncing":
        await async_session.execute(
            update(model).where(model.id == source_id).values(sync_status="syncing")
        )
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "corrupt_reference":
        await async_session.execute(
            update(RAGDocument).where(RAGDocument.id == document_id).values(user_id=None)
        )
        await async_session.commit()
    elif scenario in {"ack_lost", "ack_cancel"}:
        original = async_session.commit

        async def lose_ack():
            await original()
            if scenario == "ack_cancel":
                raise asyncio.CancelledError()
            raise OSError("Controlled lost SQL acknowledgement")

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario == "valid":
        await execute_source_unlink(async_session, owner, draft, receipt)
        assert (
            receipt.committed and receipt.values["source_to_unlink"]["documents_retained"] is True
        )
    else:
        with pytest.raises((CommandRejected, BaseAPIException)) as error:
            await execute_source_unlink(async_session, owner, draft, receipt)
        assert not receipt.committed
        if scenario in {"ack_lost", "ack_cancel"}:
            assert error.value.code == "COMPLETION_UNKNOWN"
        await async_session.rollback()
    removed = scenario in {"valid", "ack_lost", "ack_cancel"}
    assert (
        await async_session.scalar(select(model.id).where(model.id == source_id)) is None
    ) == removed
    assert await async_session.scalar(select(reference).where(RAGDocument.id == document_id)) == (
        None if removed else source_id
    )
    assert (
        await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == document_id))
        == document_id
    )
    assert file.read_bytes() == b"data"
