"""A knowledge-space document becomes a message attachment — a COPY the person chose.

The person points the composer's « + » at a document already indexed in one
of their spaces (active or not): the stored file is copied into the
attachments store with a fresh UUID name, its text is extracted through the
knowledge spaces' own pipeline under the attachments' text cap (the cut is
stated), and the row is an UPLOAD (ADR-279): a reset removes it like anything
the person put in, the TTL sweep expires it, the knowledge document is never
touched. Only a `ready` document is offered (its extraction is proven); a
document of another account, or of a system space, does not exist.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from src.core.exceptions import BaseAPIException
from src.domains.attachments import knowledge_copy
from src.domains.attachments.models import AttachmentContentType, AttachmentOrigin, AttachmentStatus
from src.domains.rag_spaces.models import RAGDocumentStatus

pytestmark = pytest.mark.unit

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx(text: str) -> bytes:
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def _document(
    *, user_id: uuid.UUID, space_id: uuid.UUID, path: Path, status: str = RAGDocumentStatus.READY
) -> MagicMock:
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.user_id = user_id
    doc.space_id = space_id
    doc.filename = path.name
    doc.original_filename = "notes.docx"
    doc.content_type = DOCX
    doc.file_size = path.stat().st_size if path.exists() else 0
    doc.status = status
    return doc


@pytest.fixture
def storage(tmp_path: Path) -> dict[str, Path]:
    rag_root = tmp_path / "rag"
    att_root = tmp_path / "att"
    rag_root.mkdir()
    att_root.mkdir()
    return {"rag": rag_root, "att": att_root}


async def _copy(storage, doc, *, max_chars: int = 50_000):
    db = AsyncMock()
    created: list[dict] = []

    async def create(payload):
        created.append(payload)
        row = MagicMock(id=uuid.uuid4(), **payload)
        return row

    settings_mock = MagicMock(
        attachments_storage_path=str(storage["att"]),
        rag_spaces_storage_path=str(storage["rag"]),
        attachments_ttl_hours=24,
        attachments_max_pdf_text_chars=max_chars,
    )
    with (
        patch.object(knowledge_copy, "settings", settings_mock),
        patch("src.domains.rag_spaces.document_access.settings", settings_mock),
        patch.object(knowledge_copy, "owned_document", AsyncMock(return_value=doc)),
        patch.object(knowledge_copy, "AttachmentRepository") as repo_cls,
    ):
        repo_cls.return_value.create = AsyncMock(side_effect=create)
        row = await knowledge_copy.copy_knowledge_document(
            db, user_id=doc.user_id, space_id=doc.space_id, document_id=doc.id
        )
    return row, created, db


async def test_a_ready_document_becomes_an_upload_attachment_with_its_text(storage) -> None:
    user_id, space_id = uuid.uuid4(), uuid.uuid4()
    stored = storage["rag"] / str(user_id) / str(space_id) / "abc.docx"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(_docx("the agenda for monday"))
    doc = _document(user_id=user_id, space_id=space_id, path=stored)

    row, created, db = await _copy(storage, doc)

    payload = created[0]
    assert payload["user_id"] == user_id
    assert payload["original_filename"] == "notes.docx"
    assert payload["mime_type"] == DOCX
    assert payload["content_type"] == AttachmentContentType.DOCUMENT
    assert payload["origin"] == AttachmentOrigin.UPLOAD.value
    assert payload["status"] == AttachmentStatus.READY
    assert "the agenda for monday" in payload["extracted_text"]
    # A fresh UUID name under the account's directory — never the space's file.
    copied = storage["att"] / payload["file_path"]
    assert copied.exists() and copied != stored and stored.exists()
    assert payload["file_path"].startswith(f"{user_id}/")
    assert payload["file_size"] == stored.stat().st_size
    db.commit.assert_awaited_once()


async def test_the_text_is_capped_and_the_cut_is_stated(storage) -> None:
    user_id, space_id = uuid.uuid4(), uuid.uuid4()
    stored = storage["rag"] / str(user_id) / str(space_id) / "long.docx"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(_docx("word " * 2000))
    doc = _document(user_id=user_id, space_id=space_id, path=stored)

    _, created, _ = await _copy(storage, doc, max_chars=1000)

    text = created[0]["extracted_text"]
    assert len(text) == 1000
    assert knowledge_copy.text_is_capped(text, 1000) is True


async def test_a_document_not_ready_is_refused_with_a_code(storage) -> None:
    user_id, space_id = uuid.uuid4(), uuid.uuid4()
    doc = _document(
        user_id=user_id,
        space_id=space_id,
        path=storage["rag"] / "x.docx",
        status=RAGDocumentStatus.PROCESSING,
    )
    with pytest.raises(BaseAPIException) as exc_info:
        await _copy(storage, doc)
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == {"code": knowledge_copy.DOCUMENT_NOT_READY_CODE}


async def test_a_missing_stored_file_is_told_not_found(storage) -> None:
    user_id, space_id = uuid.uuid4(), uuid.uuid4()
    doc = _document(user_id=user_id, space_id=space_id, path=storage["rag"] / "gone.docx")
    with pytest.raises(BaseAPIException) as exc_info:
        await _copy(storage, doc)
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


async def test_a_row_that_fails_leaves_no_orphan_copy_on_disk(storage) -> None:
    user_id, space_id = uuid.uuid4(), uuid.uuid4()
    stored = storage["rag"] / str(user_id) / str(space_id) / "abc.docx"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(_docx("kept in the space"))
    doc = _document(user_id=user_id, space_id=space_id, path=stored)
    settings_mock = MagicMock(
        attachments_storage_path=str(storage["att"]),
        rag_spaces_storage_path=str(storage["rag"]),
        attachments_ttl_hours=24,
        attachments_max_pdf_text_chars=50_000,
    )
    with (
        patch.object(knowledge_copy, "settings", settings_mock),
        patch("src.domains.rag_spaces.document_access.settings", settings_mock),
        patch.object(knowledge_copy, "owned_document", AsyncMock(return_value=doc)),
        patch.object(knowledge_copy, "AttachmentRepository") as repo_cls,
    ):
        repo_cls.return_value.create = AsyncMock(side_effect=RuntimeError("db down"))
        with pytest.raises(RuntimeError):
            await knowledge_copy.copy_knowledge_document(
                AsyncMock(), user_id=user_id, space_id=space_id, document_id=doc.id
            )

    # The account's attachment directory holds nothing: the copy was withdrawn.
    account_dir = storage["att"] / str(user_id)
    assert not account_dir.exists() or list(account_dir.iterdir()) == []
    assert stored.exists()
