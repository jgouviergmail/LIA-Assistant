"""Approved destination CAS, local file consent and truthful pending-index receipt."""

from contextlib import asynccontextmanager
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_upload import read_document_upload_selection
from src.domains.agents.application.document_upload_execution import accept_document_upload
from src.domains.agents.application.document_upload_schemas import (
    DocumentUploadInput,
    DocumentUploadPatch,
)
from src.domains.agents.application.document_upload_spec import DOCUMENT_UPLOAD_OPERATION
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_file_consent",
        "space_changed",
        "two_files",
        "lost_ack",
        "cancelled_ack",
        "wrong_actor",
        "expired",
        "revoked_after_write",
        "expired_after_pick",
        "expired_after_write",
    ],
)
async def test_browser_upload_accepts_one_consented_file_into_exact_destination(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    import asyncio

    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Consented <destination>")
    async_session.add(space)
    await async_session.commit()
    space_id, command_id = space.id, uuid4()
    selected = await read_document_upload_selection(
        async_session, owner, DocumentUploadInput(space_id=space_id)
    )
    draft = build_action_content(
        owner,
        DOCUMENT_UPLOAD_OPERATION,
        DocumentUploadPatch(document_to_upload=selected),
        {"document_to_upload": None},
        {"document_to_upload": selected.public_scope()},
        command_id=command_id,
    )
    if scenario == "wrong_actor":
        draft = draft.model_copy(update={"actor_id": uuid4()})
    if scenario == "expired":
        from datetime import UTC, datetime, timedelta

        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "space_changed":
        space.name = "Changed destination"
        await async_session.commit()
    parsed = 0

    @asynccontextmanager
    async def form():
        nonlocal parsed
        parsed += 1
        assert not async_session.in_transaction(), "No SQL transaction waits for the upload body"
        if scenario == "expired_after_pick":
            from datetime import UTC, datetime, timedelta

            draft.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        from starlette.datastructures import FormData

        file = UploadFile(filename="controlled.txt", file=BytesIO(b"data"))
        values = [("file", file)]
        if scenario == "two_files":
            values.append(("file", UploadFile(filename="second.txt", file=BytesIO(b"extra"))))
        data = FormData(values)
        try:
            yield data
        finally:
            await data.close()

    receipt = PreferenceWriteReceipt()
    original_commit = async_session.commit
    if scenario in {"lost_ack", "cancelled_ack"}:

        async def lost():
            uploaded = await async_session.scalar(
                select(RAGDocument.id).where(RAGDocument.id == command_id)
            )
            await original_commit()
            if uploaded is None:
                return
            if scenario == "cancelled_ack":
                raise asyncio.CancelledError()
            raise OSError("Lost upload acknowledgement")

        monkeypatch.setattr(async_session, "commit", lost)
    check = AsyncMock()
    if scenario == "revoked_after_write":
        check.side_effect = [None, None, CommandRejected("FORBIDDEN")]
    if scenario == "expired_after_write":

        async def expire_after_write():
            from datetime import UTC, datetime, timedelta

            if check.await_count == 3:
                draft.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        check.side_effect = expire_after_write
    if scenario == "valid":
        values = await accept_document_upload(
            async_session, owner, draft, receipt, check, file_confirmed=True, parse_form=form
        )
        assert receipt.committed and values["document_id"] == str(command_id)
        assert values["indexing_completed"] is False and values["status"] == "pending"
        row = await async_session.get(RAGDocument, command_id)
        assert row is not None and row.user_id == owner and row.space_id == space_id
        assert (tmp_path / str(owner) / str(space_id) / row.filename).read_bytes() == b"data"
        assert "filename" not in values and "state_digest" not in values
    else:
        expected_error = (
            ContinuationCompletionUnknown
            if scenario in {"lost_ack", "cancelled_ack"}
            else ValueError if scenario == "two_files" else CommandRejected
        )
        with pytest.raises(expected_error):
            await accept_document_upload(
                async_session,
                owner,
                draft,
                receipt,
                check,
                file_confirmed=scenario != "no_file_consent",
                parse_form=form,
            )
        monkeypatch.setattr(async_session, "commit", original_commit)
        await async_session.rollback()
        row = await async_session.get(RAGDocument, command_id)
        if scenario in {"lost_ack", "cancelled_ack"}:
            assert row is not None and not receipt.committed
            assert (tmp_path / str(owner) / str(space_id) / row.filename).read_bytes() == b"data"
        else:
            assert row is None and not list(tmp_path.rglob("*.txt"))
    if scenario in {"no_file_consent", "wrong_actor", "expired", "space_changed"}:
        assert parsed == 0
    if scenario not in {"no_file_consent", "wrong_actor", "expired"}:
        check.assert_awaited()
