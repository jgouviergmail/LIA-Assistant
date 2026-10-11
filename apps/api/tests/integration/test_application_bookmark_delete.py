"""Confirmed removal binds the copied answer/projection and cleans only after known commit."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.bookmark_delete import (
    execute_bookmark_deletion,
    prepare_bookmark_deletion,
)
from src.domains.agents.application.bookmark_delete_schemas import BookmarkDeleteInput
from src.domains.agents.application.command_service import CommandRejected
from src.domains.bookmarks.models import MessageBookmark
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDocumentStatus
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.bookmarks.test_bookmarks_db import (
    _bookmark,
    _document,
    _space,
    _user,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_projection",
        "changed",
        "file_changed",
        "disabled",
        "revoked",
        "expired",
        "ack_lost",
        "cancelled",
        "projection_changed",
        "chunk_changed",
        "foreign_projection",
        "shared_projection",
        "cleanup_failed",
        "post_ack_replaced",
        "large_copy",
    ],
)
async def test_saved_answer_deletion_requires_unchanged_consent_and_known_ack(
    async_session, test_user, monkeypatch, tmp_path, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", False)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    actor = test_user.id
    space = await _space(async_session, test_user)
    document = await _document(async_session, test_user, space, RAGDocumentStatus.READY)
    row = await _bookmark(async_session, test_user, None)
    if scenario == "large_copy":
        row.content = "Long saved answer " * 10_000
    if scenario != "no_projection":
        row.rag_document_id = document.id
    chunks = []
    if scenario in {"large_copy", "chunk_changed"}:
        texts = [row.content[index : index + 2_000] for index in range(0, len(row.content), 2_000)]
        chunks = [
            RAGChunk(
                document_id=document.id,
                space_id=space.id,
                user_id=actor,
                chunk_index=index,
                content=content,
                embedding=[0.0] * RAG_SPACES_EMBEDDING_DIMENSIONS_DEFAULT,
                embedding_model="controlled",
            )
            for index, content in enumerate(texts)
        ]
        async_session.add_all(chunks)
    identity, doc_id = row.id, document.id
    path = tmp_path / str(actor) / str(space.id) / document.filename
    path.parent.mkdir(parents=True)
    path.write_bytes(b"approved saved-answer projection")
    await async_session.commit()
    draft = await prepare_bookmark_deletion(
        async_session, actor, BookmarkDeleteInput(bookmark_id=identity)
    )
    assert len(draft.model_dump_json()) < 10_000
    await async_session.commit()
    if scenario == "changed":
        row.content = "Changed copied answer"
        await async_session.commit()
    elif scenario == "file_changed":
        path.write_bytes(b"different projection")
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "revoked":
        test_user.is_active = False
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "projection_changed":
        document.original_filename = "Changed projection filename.md"
        await async_session.commit()
    elif scenario == "chunk_changed":
        chunks[0].content = "Changed indexed copy"
        await async_session.commit()
    elif scenario == "foreign_projection":
        document.user_id = (await _user(async_session)).id
        await async_session.commit()
    elif scenario == "shared_projection":
        shared = await _bookmark(async_session, test_user, None)
        shared.rag_document_id = doc_id
        await async_session.commit()
    elif scenario == "cleanup_failed":

        async def failed_cleanup(*args):
            raise OSError("Controlled cleanup failure")

        monkeypatch.setattr(
            "src.domains.agents.application.bookmark_delete.cleanup_deleted_document_file",
            failed_cleanup,
        )
    original = async_session.commit

    async def commit():
        assert path.exists()
        await original()
        if scenario == "post_ack_replaced":
            path.write_bytes(b"replacement after known commit")
        if scenario == "ack_lost":
            raise OSError("Controlled lost acknowledgement")
        if scenario == "cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr(async_session, "commit", commit)
    receipt = PreferenceWriteReceipt()
    if scenario in {"valid", "no_projection", "large_copy", "cleanup_failed", "post_ack_replaced"}:
        await execute_bookmark_deletion(async_session, actor, draft, receipt)
        assert receipt.committed
        assert path.exists() == (
            scenario in {"no_projection", "cleanup_failed", "post_ack_replaced"}
        )
        assert receipt.values["saved_answer_to_delete"]["file_cleanup_pending"] == (
            scenario in {"cleanup_failed", "post_ack_replaced"}
        )
    else:
        with pytest.raises((CommandRejected, BaseAPIException)):
            await execute_bookmark_deletion(async_session, actor, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and path.exists()
    present = await async_session.scalar(
        select(MessageBookmark.id).where(MessageBookmark.id == identity)
    )
    removed = scenario in {
        "valid",
        "no_projection",
        "ack_lost",
        "cancelled",
        "large_copy",
        "cleanup_failed",
        "post_ack_replaced",
    }
    assert (present is None) == removed
    projection = await async_session.scalar(select(RAGDocument.id).where(RAGDocument.id == doc_id))
    assert (projection is None) == (removed and scenario != "no_projection")
