"""Tests for AttachmentService — CA-4: an upload's heavy steps run off the event loop.

The upload path writes the (potentially multi-MB) file bytes to disk, converts a
HEIC picture to JPEG and extracts a PDF's text. Run synchronously on the async
request path, each one blocks the whole event loop — every request and stream of
the worker. Measured 2026-10-25 on a workstation, the longest stall of the loop was
0.9-1.2 s for a 12-megapixel HEIC and about 230 ms for a 300-page PDF read to its
last page; offloaded, under 20 ms for both (PyMuPDF holds the GIL during each call,
so its longest one still bounds the stall). All three go through
``asyncio.to_thread``.
"""

import io
import threading
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from src.domains.attachments.models import AttachmentContentType
from src.domains.attachments.service import AttachmentService
from tests.helpers.attachment_publication import stub_publication


@pytest.mark.unit
class TestAttachmentUploadOffEventLoop:
    """CA-4: the attachment disk write must not run on the event-loop thread."""

    @pytest.mark.asyncio
    async def test_upload_writes_off_event_loop(self, tmp_path) -> None:
        db = AsyncMock()
        service = AttachmentService(db)
        service.repo = AsyncMock()

        # Stub the in-memory processing so the flow reaches the disk write with a
        # plain PNG and no HEIC/PDF branches.
        service._settings = MagicMock(
            attachments_storage_path=str(tmp_path), attachments_ttl_hours=24
        )
        service._detect_mime_type = MagicMock(return_value="image/png")
        service._classify_content = MagicMock(return_value=AttachmentContentType.IMAGE)
        service._get_max_size_bytes = MagicMock(return_value=10_000_000)
        service._mime_to_extension = MagicMock(return_value="png")

        png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        mock_file = _upload_file(png_bytes, "photo.png")

        main_tid = threading.get_ident()
        write_tid: dict[str, int] = {}
        real_write = Path.write_bytes

        def spy_write(self_path, data):
            write_tid["tid"] = threading.get_ident()
            return real_write(self_path, data)

        with patch("pathlib.Path.write_bytes", spy_write), stub_publication(tmp_path):
            result = await service.upload(uuid.uuid4(), mock_file)
        await mock_file.close()

        assert result.file_size == len(png_bytes)
        assert result.mime_type == "image/png"
        # Ran in a worker thread, not the event-loop thread.
        assert write_tid["tid"] != main_tid
        # Behavior preserved: the file is physically written to disk.
        written = list(tmp_path.rglob("*.png"))
        assert written and written[0].read_bytes() == png_bytes

    @pytest.mark.asyncio
    async def test_a_heic_upload_is_converted_off_event_loop(self, tmp_path) -> None:
        service = _upload_service(tmp_path, "image/heic", AttachmentContentType.IMAGE)
        threads: list[int] = []
        real_convert = AttachmentService._convert_heic_to_jpeg

        def spy_convert(file_bytes: bytes) -> tuple[bytes, str]:
            threads.append(threading.get_ident())
            return real_convert(file_bytes)

        file = _upload_file(_heic_bytes(), "photo.heic")
        with (
            patch.object(AttachmentService, "_convert_heic_to_jpeg", staticmethod(spy_convert)),
            stub_publication(tmp_path),
        ):
            result = await service.upload(uuid.uuid4(), file)
        await file.close()

        assert threads and threads[0] != threading.get_ident()
        # Behavior preserved: the JPEG is what is stored and recorded.
        assert result.mime_type == "image/jpeg"
        assert list(tmp_path.rglob("*.jpg"))

    @pytest.mark.asyncio
    async def test_a_pdf_upload_extracts_its_text_off_event_loop(self, tmp_path) -> None:
        service = _upload_service(tmp_path, "application/pdf", AttachmentContentType.DOCUMENT)
        threads: list[int] = []
        real_extract = AttachmentService._extract_pdf_text

        def spy_extract(file_bytes: bytes, max_chars: int) -> str | None:
            threads.append(threading.get_ident())
            return real_extract(file_bytes, max_chars)

        file = _upload_file(_pdf_bytes("a page"), "notes.pdf")
        with (
            patch.object(AttachmentService, "_extract_pdf_text", staticmethod(spy_extract)),
            stub_publication(tmp_path),
        ):
            result = await service.upload(uuid.uuid4(), file)
        await file.close()

        assert threads and threads[0] != threading.get_ident()
        # Behavior preserved: the text reaches the record, within its budget.
        assert result.extracted_text is not None and "a page" in result.extracted_text


def _upload_service(
    tmp_path: Path, mime: str, category: AttachmentContentType
) -> AttachmentService:
    """A service whose upload takes the ``mime`` branch and stores under ``tmp_path``."""
    service = AttachmentService(AsyncMock())
    service.repo = AsyncMock()
    service.repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    service._settings = MagicMock(
        attachments_storage_path=str(tmp_path),
        attachments_ttl_hours=24,
        attachments_max_pdf_text_chars=10_000,
    )
    service._detect_mime_type = MagicMock(return_value=mime)
    service._classify_content = MagicMock(return_value=category)
    service._get_max_size_bytes = MagicMock(return_value=10_000_000)
    return service


def _upload_file(body: bytes, filename: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(body), filename=filename)


def _heic_bytes() -> bytes:
    """A real HEIC picture, encoded by the same codec the decode relies on."""
    import io

    from PIL import Image

    from src.infrastructure.media.heif import ensure_heif_support

    ensure_heif_support()
    buffer = io.BytesIO()
    Image.new("RGB", (24, 16), (200, 30, 30)).save(buffer, format="HEIF")
    return buffer.getvalue()


@pytest.mark.unit
class TestHeicUploadIsConverted:
    """The router promises « HEIC images are automatically converted to JPEG »."""

    def test_a_heic_picture_becomes_a_jpeg(self) -> None:
        import io

        from PIL import Image

        converted, mime = AttachmentService._convert_heic_to_jpeg(_heic_bytes())

        assert mime == "image/jpeg"
        with Image.open(io.BytesIO(converted)) as img:
            assert img.format == "JPEG"
            assert img.size == (24, 16)


def _pdf_bytes(*pages: str) -> bytes:
    """A real PDF, one page per text (an empty text leaves its page blank)."""
    import pymupdf

    with pymupdf.open() as doc:
        for text in pages:
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), text)
        return doc.tobytes()


@pytest.mark.unit
class TestPdfTextExtraction:
    """An uploaded PDF reaches the model as its text, within a character budget."""

    def test_every_page_is_read_in_order(self) -> None:
        text = AttachmentService._extract_pdf_text(_pdf_bytes("first page", "second page"), 10_000)

        assert text is not None
        assert text.index("first page") < text.index("second page")

    def test_the_page_that_crosses_the_budget_is_cut_there(self) -> None:
        text = AttachmentService._extract_pdf_text(_pdf_bytes("abcdefghij", "klmnopqrst"), 15)

        assert text is not None
        assert text.startswith("abcdefghij")
        assert text.endswith("klmn")

    def test_a_pdf_without_a_text_layer_reads_as_nothing(self) -> None:
        assert AttachmentService._extract_pdf_text(_pdf_bytes(""), 1_000) is None

    def test_bytes_that_are_not_a_pdf_read_as_nothing(self) -> None:
        assert AttachmentService._extract_pdf_text(b"%PDF-not really", 1_000) is None
