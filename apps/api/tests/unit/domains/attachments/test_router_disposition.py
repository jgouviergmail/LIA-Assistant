"""Serving disposition: images AND pdf inline, other documents download (ADR-226).

PDF inline lets the browser open generated reports (and the user's own
uploaded PDFs) in a tab; every other document keeps the download prompt.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.attachments.router import get_attachment


def _attachment(mime: str, file_path: str, filename: str) -> MagicMock:
    attachment = MagicMock()
    attachment.mime_type = mime
    attachment.file_path = file_path
    attachment.original_filename = filename
    return attachment


async def _serve(tmp_path, mime: str, filename: str) -> object:
    """Invoke the route handler with patched service + storage root."""
    relative = f"user/{filename}"
    stored = tmp_path / relative
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(b"payload")

    fake_settings = MagicMock()
    fake_settings.attachments_storage_path = str(tmp_path)

    service = MagicMock()
    service.get_for_user = AsyncMock(return_value=_attachment(mime, relative, filename))

    with (
        patch("src.domains.attachments.router.get_settings", return_value=fake_settings),
        patch("src.domains.attachments.router.AttachmentService", return_value=service),
    ):
        return await get_attachment(attachment_id=MagicMock(), user=MagicMock(), db=MagicMock())


@pytest.mark.unit
class TestServingDisposition:
    """The disposition rule: displayable-in-browser => inline, else download."""

    async def test_image_is_inline(self, tmp_path) -> None:
        response = await _serve(tmp_path, "image/png", "a.png")
        assert response.headers["content-disposition"].startswith("inline")

    async def test_pdf_is_inline(self, tmp_path) -> None:
        response = await _serve(tmp_path, "application/pdf", "rapport.pdf")
        assert response.headers["content-disposition"].startswith("inline")

    async def test_docx_stays_a_download(self, tmp_path) -> None:
        response = await _serve(
            tmp_path,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "rapport.docx",
        )
        assert response.headers["content-disposition"].startswith("attachment")

    async def test_csv_stays_a_download(self, tmp_path) -> None:
        response = await _serve(tmp_path, "text/csv", "data.csv")
        assert response.headers["content-disposition"].startswith("attachment")
