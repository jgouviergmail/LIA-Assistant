"""A file seen in the page (ADR-369, lots 6 and 14).

What ``previews`` makes of a document, read from the drive, in the best form it has. A Google
document, which has no bytes of its own, comes through its PDF export, or its first one (a sheet
as a workbook). An Office document comes as the PDF Graph renders, and as its own bytes when that
fails: tables and words read better as themselves, until they read as nothing. It costs a read of
the file, so it runs under the account's one transfer, and a file past the published ceiling is
refused before it is read.

A file nothing can be shown of is refused, and stays usable: the page simply shows no preview.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.document_types import PDF_TYPE, SLIDES_TYPE, WORD_TYPE, reading_type
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.attachments.preview import DocumentPreview
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.downloads import one_preview
from src.domains.workbench.drive_formats import EXPORTS, PDF_EXPORT, is_google_type
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, TOO_LARGE, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.previews import can_be_shown, shown_document

logger = structlog.get_logger(__name__)

_TOOL = WorkbenchTool.FILES
_FIELDS: Final = ["id", "name", "mimeType", "size"]
#: What Graph's PDF reads better than the file itself: a document, or what nothing here reads.
_CONVERTED_READINGS: Final = frozenset({None, WORD_TYPE, SLIDES_TYPE})


def previewable(raw: Mapping[str, Any]) -> bool:
    """Whether something can be shown of a file: what the page asks before reading it.

    Args:
        raw: The item, in its drive's words: a Google type says what it is, whatever a person
            named it, and a file its drive renders has a PDF whatever its bytes.

    Returns:
        True when reading it would answer something.
    """
    mime_type = str(raw.get("mimeType") or "")
    if is_google_type(mime_type):
        return mime_type in EXPORTS
    return raw.get("pdfConvertible") is True or can_be_shown(mime_type, str(raw.get("name") or ""))


async def preview_file(user_id: UUID, file_id: str) -> DocumentPreview:
    """What can be shown of a file.

    Args:
        user_id: The account.
        file_id: The file.

    Returns:
        What the page lays out.

    Raises:
        BaseAPIException: ``not_supported_by_provider`` when nothing can be shown of it;
            ``too_large`` with the ceiling; ``provider_rate_limited`` when another transfer of
            the account outlasts the wait.
    """
    async with one_preview(user_id), open_tool_client(_TOOL, user_id) as opened:
        client: Any = opened.client
        async with provider_call(_TOOL, "preview", act=False):
            raw = await client.get_file_metadata(file_id, fields=_FIELDS)
            data, mime_type = await _source_of(client, file_id, raw)
            return await _read(client, file_id, raw, data, mime_type)


async def _source_of(client: Any, file_id: str, raw: Mapping[str, Any]) -> tuple[bytes, str]:
    """The bytes a preview reads, and their type; nothing is read of what cannot be shown."""
    mime_type = str(raw.get("mimeType") or "")
    name = str(raw.get("name") or "")
    ceiling = settings.workbench_download_max_bytes
    formats = EXPORTS.get(mime_type)
    if formats is not None:
        export = formats.get(PDF_EXPORT) or next(iter(formats.values()))
        data = await client.export_google_doc(file_id, export.mime_type)
        return _within(data, ceiling), export.mime_type
    if not previewable(raw):
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    if raw.get("pdfConvertible") is True and reading_type(mime_type, name) in _CONVERTED_READINGS:
        pdf = await _converted(client, file_id, ceiling)
        if pdf is not None:
            return pdf, PDF_TYPE
        if not can_be_shown(mime_type, name):
            refuse(NOT_SUPPORTED_BY_PROVIDER)
    listed = raw.get("size")
    size = int(listed) if listed is not None else None
    if size is not None and size > ceiling:
        refuse(TOO_LARGE, max_bytes=ceiling)
    data = await client.get_file_content(file_id, max_size_bytes=ceiling, known_size=size)
    return _within(data, ceiling), mime_type


async def _read(
    client: Any, file_id: str, raw: Mapping[str, Any], data: bytes, mime_type: str
) -> DocumentPreview:
    """What the bytes read as; what reads as nothing comes as the PDF its drive renders, if any."""
    try:
        return await shown_document(data, mime_type, str(raw.get("name") or ""))
    except BaseAPIException:
        if raw.get("pdfConvertible") is not True:
            raise
    pdf = await _converted(client, file_id, settings.workbench_download_max_bytes)
    if pdf is None:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    return DocumentPreview(pdf, PDF_TYPE)


async def _converted(client: Any, file_id: str, ceiling: int) -> bytes | None:
    """The PDF a drive renders; None past the ceiling, or when it could not render it."""
    try:
        pdf: bytes | None = await client.converted_to_pdf(file_id, ceiling)
    except (ConnectorAPIError, ValueError) as failure:
        logger.info("workbench_file_not_converted", error_type=type(failure).__name__)
        return None
    return pdf


def _within(data: bytes | None, ceiling: int) -> bytes:
    """The bytes read, or the refusal of a read the client stopped at its bound."""
    if data is None or len(data) > ceiling:
        refuse(TOO_LARGE, max_bytes=ceiling)
    return data


__all__ = ["preview_file", "previewable"]
