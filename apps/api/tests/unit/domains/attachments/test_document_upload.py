"""A document sent from the composer: every format a knowledge space reads (ADR-295 amendment).

The upload took images and PDFs. What must hold now that it takes the rest:

- the type is decided by what the file IS (``document_formats``), after the
  whole content is read — an archive names itself at its END — and never by
  the request's declared type;
- its text is extracted through the knowledge spaces' own readers, under the
  attachments' cap, off the event loop;
- the instance's allowlist is still the last word, and the size cap is the
  DOCUMENT's;
- an extraction that fails costs the text, never the upload — as a scanned
  PDF always did.
"""

from __future__ import annotations

import io
import threading
import uuid
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import UploadFile

from src.core.constants import (
    ATTACHMENTS_ALLOWED_DOC_TYPES_DEFAULT,
    ATTACHMENTS_ALLOWED_IMAGE_TYPES_DEFAULT,
)
from src.core.exceptions import BaseAPIException
from src.domains.attachments import document_formats
from src.domains.attachments.models import AttachmentContentType
from src.domains.attachments.service import AttachmentService
from tests.helpers.attachment_publication import stub_publication

pytestmark = pytest.mark.unit

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _service(tmp_path: Path, **settings: object) -> AttachmentService:
    """A service with the REAL detection, storing under ``tmp_path``."""
    service = AttachmentService(AsyncMock())
    service.repo = AsyncMock()
    base: dict[str, object] = {
        "attachments_storage_path": str(tmp_path),
        "attachments_ttl_hours": 24,
        "attachments_max_pdf_text_chars": 10_000,
        "attachments_max_image_size_mb": 1,
        "attachments_max_doc_size_mb": 1,
        "attachments_allowed_image_types": ATTACHMENTS_ALLOWED_IMAGE_TYPES_DEFAULT,
        "attachments_allowed_doc_types": ATTACHMENTS_ALLOWED_DOC_TYPES_DEFAULT,
    }
    service._settings = MagicMock(**{**base, **settings})
    return service


def _file(body: bytes, filename: str, declared: str | None = None) -> UploadFile:
    headers = {"content-type": declared} if declared else None
    return UploadFile(file=io.BytesIO(body), filename=filename, headers=headers)  # type: ignore[arg-type]


def _docx(text: str = "Quarterly notes") -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def _upload(service: AttachmentService, tmp_path: Path, file: UploadFile) -> object:
    with stub_publication(tmp_path):
        try:
            return await service.upload(uuid.uuid4(), file)
        finally:
            await file.close()


class TestADocumentIsAcceptedForWhatItIs:
    async def test_a_word_document_is_stored_with_its_text(self, tmp_path: Path) -> None:
        result = await _upload(_service(tmp_path), tmp_path, _file(_docx(), "notes.docx"))

        assert result.mime_type == DOCX
        assert result.content_type == AttachmentContentType.DOCUMENT
        assert "Quarterly notes" in (result.extracted_text or "")
        assert [path.suffix for path in tmp_path.rglob("*") if path.is_file()] == [".docx"]

    async def test_the_declared_type_and_the_name_are_not_what_decides(
        self, tmp_path: Path
    ) -> None:
        """A Word document sent as « image/png » under a picture's name is a Word document."""
        result = await _upload(
            _service(tmp_path), tmp_path, _file(_docx(), "holiday.png", declared="image/png")
        )

        assert result.mime_type == DOCX

    async def test_a_spreadsheet_export_is_read_as_rows(self, tmp_path: Path) -> None:
        body = b"name,amount\nAda,12\nGrace,7\n"

        result = await _upload(_service(tmp_path), tmp_path, _file(body, "export.csv"))

        assert result.mime_type == "text/csv"
        assert "Ada\t12" in (result.extracted_text or "")

    async def test_its_text_is_held_to_the_attachments_cap(self, tmp_path: Path) -> None:
        service = _service(tmp_path, attachments_max_pdf_text_chars=40)

        result = await _upload(service, tmp_path, _file(b"x" * 500, "long.txt"))

        assert len(result.extracted_text or "") == 40

    async def test_the_text_is_extracted_off_the_event_loop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        threads: list[int] = []
        real = document_formats.extract_text

        def spy(path: Path, mime_type: str) -> str:
            threads.append(threading.get_ident())
            return real(path, mime_type)

        monkeypatch.setattr(document_formats, "extract_text", spy)

        await _upload(_service(tmp_path), tmp_path, _file(_docx(), "notes.docx"))

        assert threads and threads[0] != threading.get_ident()


class TestWhatIsRefused:
    async def test_an_archive_that_is_no_document(self, tmp_path: Path) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("payload.exe", b"MZ" + b"\x00" * 64)

        with pytest.raises(BaseAPIException) as refused:
            await _upload(_service(tmp_path), tmp_path, _file(buffer.getvalue(), "report.docx"))

        assert refused.value.status_code == 415
        assert not [path for path in tmp_path.rglob("*") if path.is_file()]

    async def test_a_binary_file_named_like_text(self, tmp_path: Path) -> None:
        with pytest.raises(BaseAPIException) as refused:
            await _upload(_service(tmp_path), tmp_path, _file(b"\x00\x01\x02" * 50, "notes.txt"))

        assert refused.value.status_code == 415

    async def test_a_format_the_instance_does_not_allow(self, tmp_path: Path) -> None:
        """The operator's allowlist is the last word, whatever the code can read."""
        service = _service(tmp_path, attachments_allowed_doc_types="application/pdf")

        with pytest.raises(BaseAPIException) as refused:
            await _upload(service, tmp_path, _file(_docx(), "notes.docx"))

        assert refused.value.status_code == 415

    async def test_a_document_over_the_document_cap(self, tmp_path: Path) -> None:
        oversized = b"a" * (1024 * 1024 + 1)

        with pytest.raises(BaseAPIException) as refused:
            await _upload(_service(tmp_path), tmp_path, _file(oversized, "big.txt"))

        assert refused.value.status_code == 413


class TestAnExtractionThatFails:
    async def test_it_costs_the_text_never_the_upload(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(_path: Path, _mime_type: str) -> str:
            raise ValueError("unreadable part")

        monkeypatch.setattr(document_formats, "extract_text", broken)

        result = await _upload(_service(tmp_path), tmp_path, _file(_docx(), "notes.docx"))

        assert result.mime_type == DOCX
        assert result.extracted_text is None
