"""A file seen in the page, on both drives (ADR-369, lots 6 and 14).

The best a file can be read as: a PDF whole, a Google document through its PDF export, an Office
document through the PDF Graph renders, a table as tables, a text as its words. What nothing can
show is refused, unread, and the file stays usable.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import WORKBENCH_READING_TEXT_MAX_BYTES
from src.core.document_types import PDF_TYPE, SLIDES_TYPE, WORD_TYPE, WORKBOOK_TYPE
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.attachments.preview import DocumentPreview
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.office_files import SheetReading
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import files_preview, previews
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, TOO_LARGE

pytestmark = pytest.mark.unit

USER = uuid4()
PNG = b"\x89PNG\r\n\x1a\nimage"
CEILING = settings.workbench_download_max_bytes


def _door(client: Any, kind: ConnectorType = ConnectorType.GOOGLE_DRIVE) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        assert user_id == USER
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(files_preview, "open_tool_client", opened)


@pytest.fixture(autouse=True)
def _one_preview() -> Any:
    @contextlib.asynccontextmanager
    async def claim(user_id: Any) -> AsyncIterator[None]:
        yield

    with patch.object(files_preview, "one_preview", claim):
        yield


def _client(mime_type: str, data: bytes | None = b"x", size: int | None = 1) -> MagicMock:
    listed = {"id": "f1", "mimeType": mime_type}
    if size is not None:
        listed["size"] = str(size)
    return MagicMock(
        get_file_metadata=AsyncMock(return_value=listed),
        get_file_content=AsyncMock(return_value=data),
        export_google_doc=AsyncMock(return_value=data),
        converted_to_pdf=AsyncMock(return_value=b"%PDF converted"),
    )


def _convertible(mime_type: str, name: str, data: bytes = b"own bytes") -> MagicMock:
    client = _client(mime_type, data, len(data))
    client.get_file_metadata.return_value.update(name=name, pdfConvertible=True)
    return client


async def _refused(client: MagicMock) -> Any:
    with _door(client), pytest.raises(BaseAPIException) as caught:
        await files_preview.preview_file(USER, "f1")
    return caught.value.detail["code"]


class TestWhatCanBeShown:
    @pytest.mark.parametrize("kind", [ConnectorType.GOOGLE_DRIVE, ConnectorType.MICROSOFT_ONEDRIVE])
    async def test_an_image_is_shown_as_itself(self, kind: ConnectorType) -> None:
        client = _client("image/jpeg", PNG, len(PNG))

        with _door(client, kind):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(PNG, "image/jpeg")

    async def test_an_image_of_a_type_nobody_can_serve_is_refused(self) -> None:
        assert await _refused(_client("image/jpeg evil")) == NOT_SUPPORTED_BY_PROVIDER

    async def test_an_image_type_is_read_without_its_parameters(self) -> None:
        client = _client("image/jpeg; name=a.jpg", PNG, len(PNG))

        with _door(client):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(PNG, "image/jpeg")

    async def test_a_pdf_is_served_whole(self) -> None:
        client = _client(PDF_TYPE, b"%PDF")

        with _door(client):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(b"%PDF", PDF_TYPE)

    async def test_a_word_file_no_drive_renders_is_served_for_the_page_to_lay_out(self) -> None:
        client = _client(WORD_TYPE, b"zip")

        with _door(client), patch.object(previews, "archive_within_budget"):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(b"zip", WORD_TYPE)
        client.converted_to_pdf.assert_not_awaited()

    async def test_a_file_that_declares_nothing_is_read_by_its_name(self) -> None:
        client = _client("application/octet-stream", b"# Title", 7)
        client.get_file_metadata.return_value["name"] = "notes.md"

        with _door(client):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(b"# Title", "text/markdown", False)
        assert "name" in client.get_file_metadata.await_args.kwargs["fields"]

    async def test_a_text_shows_its_beginning_and_says_it_is_cut(self) -> None:
        size = WORKBENCH_READING_TEXT_MAX_BYTES + 1
        client = _client("text/plain", b"a" * size, size)

        with _door(client):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown.truncated is True
        assert len(shown.content) == WORKBENCH_READING_TEXT_MAX_BYTES

    async def test_a_short_text_is_shown_whole(self) -> None:
        client = _client("text/plain", b"hello", 5)

        with _door(client):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(b"hello", "text/plain", False)

    @pytest.mark.parametrize(
        ("mime_type", "exported"),
        [
            ("application/vnd.google-apps.document", "application/pdf"),
            ("application/vnd.google-apps.presentation", "application/pdf"),
        ],
    )
    async def test_a_google_document_shows_through_its_export(
        self, mime_type: str, exported: str
    ) -> None:
        client = _client(mime_type, b"%PDF", None)

        with _door(client):
            shown = await files_preview.preview_file(USER, "f1")

        client.export_google_doc.assert_awaited_once_with("f1", exported)
        client.get_file_content.assert_not_awaited()
        assert shown == DocumentPreview(b"%PDF", PDF_TYPE)

    async def test_a_google_sheet_reads_as_the_tables_of_its_export(self) -> None:
        client = _client("application/vnd.google-apps.spreadsheet", b"zip", None)
        read = ([SheetReading("Budget", [["A", "B"]], False)], False)

        with _door(client), patch.object(previews, "read_workbook", return_value=read):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown.media_type == "application/json"
        assert json.loads(shown.content)["sheets"][0]["rows"] == [["A", "B"]]


class TestWhatGraphRenders:
    @pytest.mark.parametrize(
        ("mime_type", "name"),
        [
            (WORD_TYPE, "Report.docx"),
            (SLIDES_TYPE, "Deck.pptx"),
            ("application/msword", "Old.doc"),
            ("application/octet-stream", "Letter.odt"),
        ],
    )
    async def test_an_office_document_comes_as_its_pdf(self, mime_type: str, name: str) -> None:
        client = _convertible(mime_type, name)

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            shown = await files_preview.preview_file(USER, "f1")

        client.converted_to_pdf.assert_awaited_once_with("f1", CEILING)
        client.get_file_content.assert_not_awaited()
        assert shown == DocumentPreview(b"%PDF converted", PDF_TYPE)

    @pytest.mark.parametrize(
        ("mime_type", "name", "media_type"),
        [
            ("application/octet-stream", "notes.md", "text/markdown"),
            ("text/plain", "notes.txt", "text/plain"),
            (PDF_TYPE, "scan.pdf", PDF_TYPE),
        ],
    )
    async def test_what_reads_as_itself_is_not_converted(
        self, mime_type: str, name: str, media_type: str
    ) -> None:
        client = _convertible(mime_type, name)

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            shown = await files_preview.preview_file(USER, "f1")

        client.converted_to_pdf.assert_not_awaited()
        assert shown.media_type == media_type

    async def test_a_workbook_stays_tables(self) -> None:
        client = _convertible(WORKBOOK_TYPE, "Budget.xlsx")
        read = ([SheetReading("Budget", [["A"]], False)], False)

        with (
            _door(client, ConnectorType.MICROSOFT_ONEDRIVE),
            patch.object(previews, "read_workbook", return_value=read),
        ):
            shown = await files_preview.preview_file(USER, "f1")

        client.converted_to_pdf.assert_not_awaited()
        assert shown.media_type == "application/json"

    async def test_a_workbook_with_no_table_to_read_comes_as_its_pdf(self) -> None:
        """Measured 2026-11-06: a real 87 KB workbook read as no sheet, and showed nothing."""
        client = _convertible(WORKBOOK_TYPE, "Charts.xlsx")

        with (
            _door(client, ConnectorType.MICROSOFT_ONEDRIVE),
            patch.object(previews, "read_workbook", return_value=([], False)),
        ):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(b"%PDF converted", PDF_TYPE)

    async def test_a_drive_that_renders_nothing_leaves_it_refused(self) -> None:
        client = _client(WORKBOOK_TYPE, b"zip")

        with patch.object(previews, "read_workbook", return_value=([], False)):
            assert await _refused(client) == NOT_SUPPORTED_BY_PROVIDER

        client.converted_to_pdf.assert_not_awaited()

    async def test_a_workbook_nobody_can_render_either_shows_nothing(self) -> None:
        client = _convertible(WORKBOOK_TYPE, "Charts.xlsx")
        client.converted_to_pdf.return_value = None

        with (
            _door(client, ConnectorType.MICROSOFT_ONEDRIVE),
            patch.object(previews, "read_workbook", return_value=([], False)),
        ):
            assert await _refused(client) == NOT_SUPPORTED_BY_PROVIDER

    @pytest.mark.parametrize(
        "failure",
        [
            ConnectorAPIError(connector_type="microsoft_onedrive", status_code=406, detail="x"),
            ValueError("no address"),
        ],
    )
    async def test_a_conversion_that_fails_falls_back_on_the_file(self, failure: Exception) -> None:
        client = _convertible(WORD_TYPE, "Report.docx")
        client.converted_to_pdf.side_effect = failure

        with (
            _door(client, ConnectorType.MICROSOFT_ONEDRIVE),
            patch.object(previews, "archive_within_budget"),
        ):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown == DocumentPreview(b"own bytes", WORD_TYPE)

    async def test_a_conversion_past_the_ceiling_falls_back_on_the_file(self) -> None:
        client = _convertible(WORD_TYPE, "Report.docx")
        client.converted_to_pdf.return_value = None

        with (
            _door(client, ConnectorType.MICROSOFT_ONEDRIVE),
            patch.object(previews, "archive_within_budget"),
        ):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown.media_type == WORD_TYPE

    async def test_with_nothing_else_to_read_a_failed_conversion_shows_nothing(self) -> None:
        client = _convertible("application/msword", "Old.doc")
        client.converted_to_pdf.return_value = None

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            assert await _refused(client) == NOT_SUPPORTED_BY_PROVIDER

        client.get_file_content.assert_not_awaited()


class TestWhatCannot:
    @pytest.mark.parametrize(
        "mime_type",
        ["application/zip", "video/mp4", "application/vnd.google-apps.folder"],
    )
    async def test_it_is_refused_unread(self, mime_type: str) -> None:
        client = _client(mime_type)

        assert await _refused(client) == NOT_SUPPORTED_BY_PROVIDER
        client.get_file_content.assert_not_awaited()
        client.export_google_doc.assert_not_awaited()

    async def test_a_file_listed_past_the_ceiling_is_never_read(self) -> None:
        client = _client(PDF_TYPE, size=CEILING + 1)

        assert await _refused(client) == TOO_LARGE
        client.get_file_content.assert_not_awaited()

    async def test_a_file_of_exactly_the_ceiling_is_read(self) -> None:
        client = _client(PDF_TYPE, b"%PDF", CEILING)

        with _door(client):
            shown = await files_preview.preview_file(USER, "f1")

        assert shown.content == b"%PDF"

    async def test_a_file_the_client_stopped_reading_is_too_large(self) -> None:
        assert await _refused(_client(PDF_TYPE, None)) == TOO_LARGE

    async def test_an_export_past_the_ceiling_is_too_large(self) -> None:
        client = _client("application/vnd.google-apps.document", b"x" * (CEILING + 1), None)

        assert await _refused(client) == TOO_LARGE

    async def test_the_refusal_says_the_ceiling(self) -> None:
        client = _client(PDF_TYPE, size=CEILING + 1)

        with _door(client), pytest.raises(BaseAPIException) as caught:
            await files_preview.preview_file(USER, "f1")

        assert caught.value.detail["max_bytes"] == CEILING
