"""A kept answer or a generated file becomes a message attachment — a COPY (2026-10-24).

The person points the composer at something they already hold: a bookmark is
rendered as the Markdown its knowledge document reads (ADR-291) and attached
as a document with that text; a generated image or document is copied file
and all. Every copy is an UPLOAD (ADR-279) — a reset removes it, the TTL
expires it — and the original is never touched. What is not the caller's,
not generated, past its deadline or gone from the disk does not exist.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docx.opc.exceptions import PackageNotFoundError
from fastapi import status

from src.core.exceptions import BaseAPIException
from src.domains.attachments import owned_copies
from src.domains.attachments.models import (
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)

pytestmark = pytest.mark.unit

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _docx(text: str) -> bytes:
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def storage(tmp_path: Path) -> Path:
    root = tmp_path / "att"
    root.mkdir()
    return root


def _settings(storage: Path, **over: object) -> MagicMock:
    values: dict[str, object] = {
        "attachments_storage_path": str(storage),
        "attachments_ttl_hours": 24,
        "attachments_max_pdf_text_chars": 50_000,
        "attachments_max_image_size_mb": 10,
        "attachments_allowed_image_types": "image/jpeg,image/png,image/webp",
    }
    values.update(over)
    return MagicMock(**values)


class _Repo:
    """The attachments repository the copy writes through."""

    def __init__(self, source: SimpleNamespace | None = None, *, fail: bool = False) -> None:
        self.source = source
        self.fail = fail
        self.created: list[dict[str, object]] = []

    async def get_by_id(self, attachment_id: uuid.UUID) -> SimpleNamespace | None:
        return self.source if self.source and self.source.id == attachment_id else None

    async def create(self, payload: dict[str, object]) -> SimpleNamespace:
        if self.fail:
            raise RuntimeError("database gone")
        self.created.append(payload)
        return SimpleNamespace(id=uuid.uuid4(), **payload)


# -- a kept answer ---------------------------------------------------------------------------


def _bookmark(user_id: uuid.UUID, content: str = "The agenda for Monday.") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        content=content,
        request_content="What is on Monday?",
        answered_at=datetime(2026, 10, 20, 9, 30, tzinfo=UTC),
    )


async def _copy_bookmark(storage: Path, bookmark: SimpleNamespace | None, **settings: object):
    repo = _Repo()
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(language="en", timezone="UTC"))
    with (
        patch.object(owned_copies, "settings", _settings(storage, **settings)),
        patch.object(owned_copies, "AttachmentRepository", return_value=repo),
        patch.object(owned_copies, "BookmarkRepository") as bookmarks,
    ):
        bookmarks.return_value.get_for_user = AsyncMock(return_value=bookmark)
        row = await owned_copies.copy_bookmark(db, user_id=uuid.uuid4(), bookmark_id=uuid.uuid4())
    return row, repo, db


async def test_a_bookmark_becomes_a_markdown_upload_carrying_its_text(storage: Path) -> None:
    bookmark = _bookmark(uuid.uuid4())

    row, repo, db = await _copy_bookmark(storage, bookmark)

    (payload,) = repo.created
    assert payload["content_type"] == AttachmentContentType.DOCUMENT
    assert payload["mime_type"] == "text/markdown"
    assert payload["origin"] == AttachmentOrigin.UPLOAD.value
    assert payload["status"] == AttachmentStatus.READY
    assert str(payload["original_filename"]).endswith(".md")
    text = str(payload["extracted_text"])
    # The request quoted and the answer: what the kept answer's document reads.
    assert "> What is on Monday?" in text and "The agenda for Monday." in text
    written = storage / str(payload["file_path"])
    assert written.read_text(encoding="utf-8") == text
    assert payload["file_size"] == written.stat().st_size
    # The reads end before the copy, the row is committed after it.
    assert db.commit.await_count == 2
    assert row.id is not None


async def test_a_long_bookmark_is_cut_at_the_attachments_cap(storage: Path) -> None:
    bookmark = _bookmark(uuid.uuid4(), content="word " * 400)

    _row, repo, _db = await _copy_bookmark(storage, bookmark, attachments_max_pdf_text_chars=500)

    assert len(str(repo.created[0]["extracted_text"])) == 500


async def test_another_accounts_bookmark_does_not_exist(storage: Path) -> None:
    with pytest.raises(BaseAPIException) as refused:
        await _copy_bookmark(storage, None)
    assert refused.value.status_code == status.HTTP_404_NOT_FOUND


# -- a generated file ------------------------------------------------------------------------


def _generated(
    storage: Path,
    *,
    user_id: uuid.UUID,
    origin: AttachmentOrigin,
    content: bytes,
    mime: str,
    content_type: str,
    suffix: str,
    expires_at: datetime | None = None,
) -> SimpleNamespace:
    stored = f"{uuid.uuid4()}{suffix}"
    path = storage / str(user_id) / stored
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        origin=origin.value,
        status=AttachmentStatus.READY,
        content_type=content_type,
        mime_type=mime,
        original_filename=f"report{suffix}",
        stored_filename=stored,
        file_path=f"{user_id}/{stored}",
        file_size=len(content),
        expires_at=expires_at,
    )


async def _copy_generated(
    storage: Path, source: SimpleNamespace, caller: uuid.UUID, **settings: object
):
    repo = _Repo(source)
    db = AsyncMock()
    with (
        patch.object(owned_copies, "settings", _settings(storage, **settings)),
        patch.object(owned_copies, "AttachmentRepository", return_value=repo),
    ):
        row = await owned_copies.copy_generated(db, user_id=caller, attachment_id=source.id)
    return row, repo


async def test_a_generated_document_is_copied_with_its_text(storage: Path) -> None:
    user_id = uuid.uuid4()
    source = _generated(
        storage,
        user_id=user_id,
        origin=AttachmentOrigin.GENERATED_DOCUMENT,
        content=_docx("the quarterly figures"),
        mime=DOCX,
        content_type=AttachmentContentType.DOCUMENT,
        suffix=".docx",
        expires_at=datetime.now(UTC) + timedelta(hours=3),
    )

    _row, repo = await _copy_generated(storage, source, user_id)

    (payload,) = repo.created
    assert payload["origin"] == AttachmentOrigin.UPLOAD.value
    assert payload["content_type"] == AttachmentContentType.DOCUMENT
    assert payload["mime_type"] == DOCX
    assert "the quarterly figures" in str(payload["extracted_text"])
    assert payload["stored_filename"] != source.stored_filename
    # The original stays where it was.
    assert (storage / source.file_path).is_file()


async def test_a_generated_image_is_copied_as_an_image_without_text(storage: Path) -> None:
    user_id = uuid.uuid4()
    source = _generated(
        storage,
        user_id=user_id,
        origin=AttachmentOrigin.GENERATED_IMAGE,
        content=PNG,
        mime="image/png",
        content_type=AttachmentContentType.IMAGE,
        suffix=".png",
    )

    _row, repo = await _copy_generated(storage, source, user_id)

    (payload,) = repo.created
    assert payload["content_type"] == AttachmentContentType.IMAGE
    assert payload["extracted_text"] is None
    assert (storage / str(payload["file_path"])).read_bytes() == PNG


@pytest.mark.parametrize(
    ("origin", "expires_in", "owned", "on_disk"),
    [
        pytest.param(AttachmentOrigin.UPLOAD, 3, True, True, id="an-upload-is-not-generated"),
        pytest.param(AttachmentOrigin.GENERATED_IMAGE, -1, True, True, id="past-its-deadline"),
        pytest.param(AttachmentOrigin.GENERATED_IMAGE, 3, False, True, id="another-account"),
        pytest.param(AttachmentOrigin.GENERATED_IMAGE, 3, True, False, id="gone-from-disk"),
    ],
)
async def test_what_is_not_a_live_generated_file_of_the_caller_does_not_exist(
    storage: Path, origin: AttachmentOrigin, expires_in: int, owned: bool, on_disk: bool
) -> None:
    user_id = uuid.uuid4()
    source = _generated(
        storage,
        user_id=user_id,
        origin=origin,
        content=PNG,
        mime="image/png",
        content_type=AttachmentContentType.IMAGE,
        suffix=".png",
        expires_at=datetime.now(UTC) + timedelta(hours=expires_in),
    )
    if not on_disk:
        (storage / source.file_path).unlink()

    with pytest.raises(BaseAPIException) as refused:
        await _copy_generated(storage, source, user_id if owned else uuid.uuid4())
    assert refused.value.status_code == status.HTTP_404_NOT_FOUND


async def test_an_image_past_the_upload_bounds_is_refused_as_an_upload_would_be(
    storage: Path,
) -> None:
    user_id = uuid.uuid4()
    source = _generated(
        storage,
        user_id=user_id,
        origin=AttachmentOrigin.BROWSER_SCREENSHOT,
        content=PNG,
        mime="image/png",
        content_type=AttachmentContentType.IMAGE,
        suffix=".png",
    )
    with pytest.raises(BaseAPIException) as refused:
        await _copy_generated(
            storage, source, user_id, attachments_allowed_image_types="image/jpeg"
        )
    assert refused.value.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


async def test_a_copy_whose_row_fails_leaves_no_file(storage: Path) -> None:
    user_id = uuid.uuid4()
    source = _generated(
        storage,
        user_id=user_id,
        origin=AttachmentOrigin.GENERATED_IMAGE,
        content=PNG,
        mime="image/png",
        content_type=AttachmentContentType.IMAGE,
        suffix=".png",
    )
    repo = _Repo(source, fail=True)
    with (
        patch.object(owned_copies, "settings", _settings(storage)),
        patch.object(owned_copies, "AttachmentRepository", return_value=repo),
        pytest.raises(RuntimeError),
    ):
        await owned_copies.copy_generated(AsyncMock(), user_id=user_id, attachment_id=source.id)
    assert [path.name for path in (storage / str(user_id)).iterdir()] == [source.stored_filename]


async def test_a_copy_whose_text_cannot_be_read_leaves_no_file(storage: Path) -> None:
    # The copy is made before its text is extracted: a file the extraction
    # refuses would otherwise lie on disk with no row any sweep could find.
    user_id = uuid.uuid4()
    source = _generated(
        storage,
        user_id=user_id,
        origin=AttachmentOrigin.GENERATED_DOCUMENT,
        content=b"not a word document",
        mime=DOCX,
        content_type=AttachmentContentType.DOCUMENT,
        suffix=".docx",
    )
    repo = _Repo(source)
    with (
        patch.object(owned_copies, "settings", _settings(storage)),
        patch.object(owned_copies, "AttachmentRepository", return_value=repo),
        pytest.raises(PackageNotFoundError),
    ):
        await owned_copies.copy_generated(AsyncMock(), user_id=user_id, attachment_id=source.id)
    assert repo.created == []
    assert [path.name for path in (storage / str(user_id)).iterdir()] == [source.stored_filename]


async def test_the_reads_end_before_a_generated_file_is_copied(storage: Path) -> None:
    # Copying a file and extracting its text can take seconds: the source's
    # read must not keep a transaction idle meanwhile.
    user_id = uuid.uuid4()
    source = _generated(
        storage,
        user_id=user_id,
        origin=AttachmentOrigin.GENERATED_DOCUMENT,
        content=_docx("the quarterly figures"),
        mime=DOCX,
        content_type=AttachmentContentType.DOCUMENT,
        suffix=".docx",
    )
    order: list[str] = []
    db = AsyncMock()
    db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
    copy = owned_copies.copy_and_extract

    def recorded_copy(*args: object) -> tuple[str | None, int]:
        order.append("copy")
        return copy(*args)  # type: ignore[arg-type]

    with (
        patch.object(owned_copies, "settings", _settings(storage)),
        patch.object(owned_copies, "AttachmentRepository", return_value=_Repo(source)),
        patch.object(owned_copies, "copy_and_extract", recorded_copy),
    ):
        await owned_copies.copy_generated(db, user_id=user_id, attachment_id=source.id)

    assert order == ["commit", "copy", "commit"]


async def test_the_reads_end_before_a_kept_answer_is_written(storage: Path) -> None:
    order: list[str] = []
    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(language="en", timezone="UTC"))
    db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
    write = owned_copies.write_text_copy

    def recorded_write(*args: object) -> int:
        order.append("write")
        return write(*args)  # type: ignore[arg-type]

    with (
        patch.object(owned_copies, "settings", _settings(storage)),
        patch.object(owned_copies, "AttachmentRepository", return_value=_Repo()),
        patch.object(owned_copies, "BookmarkRepository") as bookmarks,
        patch.object(owned_copies, "write_text_copy", recorded_write),
    ):
        bookmarks.return_value.get_for_user = AsyncMock(return_value=_bookmark(uuid.uuid4()))
        await owned_copies.copy_bookmark(db, user_id=uuid.uuid4(), bookmark_id=uuid.uuid4())

    assert order == ["commit", "write", "commit"]
