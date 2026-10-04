"""Preview is an owner-authorized bounded read, never a whole-file download."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.attachments.models import AttachmentOrigin
from src.domains.attachments.preview import PreviewUnavailable, build_preview
from src.domains.attachments.router import get_attachment_preview

pytestmark = pytest.mark.unit


def source(tmp_path: Path, payload: bytes, mime: str = "text/plain") -> SimpleNamespace:
    (tmp_path / "owned").write_bytes(payload)
    return SimpleNamespace(
        id=uuid4(),
        origin=AttachmentOrigin.GENERATED_DOCUMENT.value,
        file_path="owned",
        mime_type=mime,
        expires_at=None,
    )


async def test_text_is_bounded_without_leaking_whole_document(tmp_path: Path) -> None:
    value = await build_preview(source(tmp_path, b"A" * 80000), tmp_path)
    assert value.media_type == "text/plain"
    assert len(value.content) <= 65536
    assert value.truncated is True


@pytest.mark.parametrize("path", ["../elsewhere", "/outside", "missing"])
async def test_unreadable_or_outside_paths_refused_before_parse(tmp_path: Path, path: str) -> None:
    item = source(tmp_path, b"text")
    item.file_path = path
    with pytest.raises(PreviewUnavailable):
        await build_preview(item, tmp_path)


async def test_pdf_first_page_is_real_png_with_bounded_dimensions(tmp_path: Path) -> None:
    from io import BytesIO

    import pymupdf
    from PIL import Image

    with pymupdf.open() as document:
        page = document.new_page(width=2000, height=3000)
        page.insert_text((50, 70), "Source first page")
        document.new_page()
        data = document.tobytes()
    value = await build_preview(source(tmp_path, data, "application/pdf"), tmp_path)
    assert value.media_type == "image/png"
    assert value.content.startswith(b"\x89PNG")
    with Image.open(BytesIO(value.content)) as image:
        assert image.width <= 640 and image.height <= 900


@pytest.mark.parametrize("payload", [b"not a PDF", b""])
async def test_malformed_pdf_has_no_sensitive_parser_error(tmp_path: Path, payload: bytes) -> None:
    with pytest.raises(PreviewUnavailable):
        await build_preview(source(tmp_path, payload, "application/pdf"), tmp_path)


async def test_preview_route_checks_owner_before_render(tmp_path: Path) -> None:
    item = source(tmp_path, b"received")
    user = SimpleNamespace(id=uuid4())
    service = MagicMock(get_for_user=AsyncMock(return_value=item))
    with (
        patch("src.domains.attachments.router.AttachmentService", return_value=service),
        patch(
            "src.domains.attachments.router.get_settings",
            return_value=SimpleNamespace(attachments_storage_path=str(tmp_path)),
        ),
    ):
        result = await get_attachment_preview(item.id, user, MagicMock())
    service.get_for_user.assert_awaited_once_with(attachment_id=item.id, user_id=user.id)
    assert result.body == b"received"
    assert result.headers["cache-control"] == "private, no-store"


async def test_preview_expiry_is_checked_even_before_cleanup(tmp_path: Path) -> None:
    item = source(tmp_path, b"text")
    item.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    service = MagicMock(get_for_user=AsyncMock(return_value=item))
    with patch("src.domains.attachments.router.AttachmentService", return_value=service):
        with pytest.raises(BaseAPIException) as error:
            await get_attachment_preview(item.id, SimpleNamespace(id=uuid4()), MagicMock())
    assert error.value.status_code == 404


async def test_preview_is_readable_after_upload_feature_is_disabled() -> None:
    from src.domains.attachments.router import router
    from tests._routes import served_routes

    route = next(
        value for value in served_routes(router) if value.path.endswith("/{attachment_id}/preview")
    )
    names = [getattr(value.call, "__name__", "") for value in route.dependant.dependencies]
    assert "get_current_active_session" in names
    assert not any("capability" in name for name in names)


@pytest.mark.parametrize(
    "origin,mime",
    [
        ("upload", "application/pdf"),
        ("generated_document", "text/html"),
        ("generated_document", "application/zip"),
    ],
)
async def test_unsupported_sources_are_refused_before_disk_read(
    tmp_path: Path, origin: str, mime: str
) -> None:
    item = source(tmp_path, b"secret", mime)
    item.origin = origin
    with patch("src.domains.attachments.preview._read_source") as read:
        with pytest.raises(PreviewUnavailable):
            await build_preview(item, tmp_path)
    read.assert_not_called()


async def test_denied_owner_never_reaches_preview_renderer() -> None:
    from src.domains.attachments.service import raise_attachment_not_found

    denied = uuid4()

    def refuse(**kwargs):
        raise_attachment_not_found(denied)

    service = MagicMock(get_for_user=AsyncMock(side_effect=refuse))
    with (
        patch("src.domains.attachments.router.AttachmentService", return_value=service),
        patch("src.domains.attachments.preview.build_preview") as render,
    ):
        with pytest.raises(BaseAPIException):
            await get_attachment_preview(denied, SimpleNamespace(id=uuid4()), MagicMock())
    render.assert_not_called()


async def test_oversized_pdf_never_starts_parser(tmp_path: Path) -> None:
    item = source(tmp_path, b"%PDF" + b"x" * (10 * 1024 * 1024), "application/pdf")
    with patch("src.domains.attachments.preview._run_pdf_worker") as worker:
        with pytest.raises(PreviewUnavailable):
            await build_preview(item, tmp_path)
    worker.assert_not_called()


def test_busy_renderer_refuses_immediately_and_timeout_releases_slot() -> None:
    import subprocess
    import threading

    from src.domains.attachments.preview import _run_pdf_worker

    slot = threading.BoundedSemaphore(1)
    slot.acquire()
    with (
        patch("src.domains.attachments.preview._PDF_SLOTS", slot),
        patch("src.domains.attachments.preview.subprocess.run") as run,
    ):
        with pytest.raises(PreviewUnavailable):
            _run_pdf_worker(b"pdf")
        run.assert_not_called()
        slot.release()
        run.side_effect = subprocess.TimeoutExpired("python", 8)
        with pytest.raises(PreviewUnavailable):
            _run_pdf_worker(b"pdf")
        assert slot.acquire(blocking=False)
        slot.release()


async def test_multibyte_cut_does_not_invent_replacement_character(tmp_path: Path) -> None:
    data = b"a" * 65535 + "émore".encode()
    result = await build_preview(source(tmp_path, data), tmp_path)
    assert result.truncated
    assert result.content == b"a" * 65535


@pytest.mark.parametrize("format", ["docx", "pptx", "xlsx"])
async def test_generated_office_documents_have_received_excerpt(
    tmp_path: Path, format: str
) -> None:
    from io import BytesIO
    from zipfile import ZipFile

    mimes = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    paths = {
        "docx": "word/document.xml",
        "pptx": "ppt/slides/slide1.xml",
        "xlsx": "xl/worksheets/sheet1.xml",
    }
    archive = BytesIO()
    if format == "xlsx":
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.append(["Received excerpt", 0])
        workbook.save(archive)
    else:
        with ZipFile(archive, "w") as file:
            file.writestr(paths[format], "<root><p><t>Received excerpt</t></p></root>")
    value = await build_preview(source(tmp_path, archive.getvalue(), mimes[format]), tmp_path)
    assert b"Received excerpt" in value.content
    if format == "xlsx":
        assert b",0" in value.content


@pytest.mark.parametrize("format", ["docx", "pptx", "xlsx"])
async def test_preview_reads_real_app_renderer_output(tmp_path: Path, format: str) -> None:
    from src.domains.document_generation.context import RenderContext
    from src.domains.document_generation.renderers import DOCUMENT_MIME_TYPES, render_document
    from src.domains.document_generation.schemas import (
        DocumentType,
        SectionBlock,
        SectionedContent,
        Slide,
        SlideContent,
        TableSheet,
        TabularContent,
    )

    kind = DocumentType(format)
    if format == "xlsx":
        content = TabularContent(
            filename_stem="preview",
            title="Received excerpt",
            sheets=[
                TableSheet(
                    name="Data", headers=["Received excerpt", "Value"], rows=[["Source", "0"]]
                )
            ],
        )
    elif format == "pptx":
        content = SlideContent(
            filename_stem="preview",
            title="Received excerpt",
            slides=[Slide(title="Source", bullets=["source body"])],
        )
    else:
        content = SectionedContent(
            filename_stem="preview",
            title="Received excerpt",
            blocks=[SectionBlock(kind="paragraph", text="source body")],
        )
    data = render_document(kind, content, RenderContext(language="en"))
    value = await build_preview(source(tmp_path, data, DOCUMENT_MIME_TYPES[kind]), tmp_path)
    assert b"Received excerpt" in value.content


@pytest.mark.parametrize(
    "xml",
    [
        pytest.param(b"<root>" + b"a" * 1048576 + b"</root>", id="xml-budget"),
        pytest.param(
            b'<!DOCTYPE x [<!ENTITY xx SYSTEM "file:///secrets">]><root><p><t>&xx;</t></p></root>',
            id="external-entity",
        ),
    ],
)
async def test_archive_budget_and_external_entities_are_rejected(
    tmp_path: Path, xml: bytes
) -> None:
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile

    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as file:
        file.writestr("word/document.xml", xml)
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    with pytest.raises(PreviewUnavailable):
        await build_preview(source(tmp_path, archive.getvalue(), mime), tmp_path)
