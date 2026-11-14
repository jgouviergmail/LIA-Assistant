"""What can be read of a document, for the mail and the files (ADR-369, lot 14).

ONE door for both screens, so a mail's attachment and a drive's file read alike. An image a page
can draw, a PDF and a Word file travel as themselves, whole: the page has a viewer for each, and a
Word file's archive is held to its budget first. A Markdown says it is one, and the page lays it
out. A slide deck reads as its text, a workbook and a CSV as tables: rows of words the page lays
out, nothing it runs. The peek a generated document shows stops at 24 paragraphs and 7 rows; a
person consulting a file reads it up to the bounds below, the cut said. A text that is no UTF-8 is
read in Windows' own letters, which is what a spreadsheet exports here (``core.text_decoding``,
the door the knowledge spaces' readers ask too): reading it wrong costs a wrong letter on the
screen, and it is never written back (``drive_text`` refuses it).
"""

from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import asdict, replace
from io import StringIO
from typing import Final

from fastapi import Response

from src.core.constants import (
    WORKBENCH_READING_CELL_MAX_CHARS,
    WORKBENCH_READING_MAX_COLUMNS,
    WORKBENCH_READING_MAX_ROWS,
    WORKBENCH_READING_MAX_SHEETS,
    WORKBENCH_READING_TEXT_MAX_BYTES,
)
from src.core.document_types import (
    CSV_TYPE,
    MARKDOWN_TYPE,
    PDF_TYPE,
    SLIDES_TYPE,
    WORD_TYPE,
    WORKBOOK_TYPE,
    plain_type,
    reading_type,
)
from src.core.text_decoding import decode_text
from src.domains.attachments.preview import DocumentPreview, PreviewUnavailable
from src.domains.connectors.clients.office_files import (
    OfficeContentRefusedError,
    SheetReading,
    archive_within_budget,
    read_slides_text,
    read_workbook,
)
from src.domains.workbench.downloads import DOWNLOAD_POLICY
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refuse

#: What a page draws; an SVG is a document that runs where it is opened, HEIC no browser reads.
_SHOWN_IMAGES: Final = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
#: What tables travel as: the page lays them out, and only this type says it may.
_SHEETS_MEDIA_TYPE: Final = "application/json"
_TEXT_MEDIA_TYPE: Final = "text/plain"
#: What separates a CSV's cells: a French spreadsheet writes semicolons.
_DELIMITERS: Final = ",;\t"
#: How much of a CSV tells its separator.
_SNIFFED_CHARS: Final = 4096


def can_be_shown(mime_type: str, name: str) -> bool:
    """Whether a document has anything to show: what a page asks before offering it.

    Args:
        mime_type: Its declared type.
        name: Its name.

    Returns:
        True when reading it would answer something.
    """
    return plain_type(mime_type) in _SHOWN_IMAGES or reading_type(mime_type, name) is not None


async def shown_document(data: bytes, mime_type: str, name: str) -> DocumentPreview:
    """What a person sees of a document.

    Args:
        data: Its bytes.
        mime_type: Its declared type: untrusted.
        name: Its name: untrusted.

    Returns:
        An image, a PDF, a Word file, a text or tables, the cut said.

    Raises:
        BaseAPIException: ``not_supported_by_provider`` when nothing can be shown of it.
    """
    plain = plain_type(mime_type)
    if plain in _SHOWN_IMAGES:
        return DocumentPreview(data, plain)
    kind = reading_type(mime_type, name)
    if kind is None:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    try:
        return await _read(data, kind)
    except OfficeContentRefusedError, PreviewUnavailable:
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def preview_response(shown: DocumentPreview) -> Response:
    """What is shown as an answer: kept by no cache, and never run.

    Args:
        shown: What can be shown.

    Returns:
        The response, the cut said in a header.
    """
    return Response(
        content=shown.content,
        media_type=shown.media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": DOWNLOAD_POLICY,
            "X-Content-Type-Options": "nosniff",
            "X-Preview-Truncated": str(shown.truncated).lower(),
        },
    )


async def _read(data: bytes, kind: str) -> DocumentPreview:
    if kind == PDF_TYPE:
        return DocumentPreview(data, PDF_TYPE)
    if kind == WORD_TYPE:
        await asyncio.to_thread(archive_within_budget, data)
        return DocumentPreview(data, WORD_TYPE)
    if kind == SLIDES_TYPE:
        return _words(await asyncio.to_thread(read_slides_text, data))
    if kind == WORKBOOK_TYPE:
        sheets, more = await asyncio.to_thread(
            read_workbook,
            data,
            sheets=WORKBENCH_READING_MAX_SHEETS,
            rows=WORKBENCH_READING_MAX_ROWS,
            columns=WORKBENCH_READING_MAX_COLUMNS,
            cell_chars=WORKBENCH_READING_CELL_MAX_CHARS,
        )
        return _tables(sheets, more)
    kept = data[:WORKBENCH_READING_TEXT_MAX_BYTES]
    # A letter the bound cut is no reason to read the text otherwise: `cut`.
    read = _words(decode_text(kept, cut=True), cut=len(data) > len(kept))
    if kind == CSV_TYPE:
        return _table_of(read)
    return replace(read, media_type=MARKDOWN_TYPE) if kind == MARKDOWN_TYPE else read


def _words(text: str, *, cut: bool = False) -> DocumentPreview:
    """A document's text up to the bound: the cut falls between two characters."""
    data = text.encode()
    if len(data) <= WORKBENCH_READING_TEXT_MAX_BYTES:
        return DocumentPreview(data, _TEXT_MEDIA_TYPE, cut)
    kept = data[:WORKBENCH_READING_TEXT_MAX_BYTES].decode(errors="ignore").encode()
    return DocumentPreview(kept, _TEXT_MEDIA_TYPE, True)


def _tables(sheets: list[SheetReading], more: bool) -> DocumentPreview:
    """Tables as the page lays them out; a workbook of chart sheets alone has none to show."""
    if not sheets:
        raise PreviewUnavailable
    body = json.dumps({"sheets": [asdict(sheet) for sheet in sheets]}, ensure_ascii=False)
    cut = more or any(sheet.cut for sheet in sheets)
    return DocumentPreview(body.encode(), _SHEETS_MEDIA_TYPE, cut)


def _table_of(read: DocumentPreview) -> DocumentPreview:
    """A CSV as one table, or its words if it is none.

    A line the byte bound broke is left out rather than shown wrong.
    """
    lines = read.content.decode().splitlines(keepends=True)
    if read.truncated and lines:
        lines.pop()
    try:
        rows = _csv_rows("".join(lines))
    except csv.Error:
        return read
    kept = [
        [cell[:WORKBENCH_READING_CELL_MAX_CHARS] for cell in row[:WORKBENCH_READING_MAX_COLUMNS]]
        for row in rows[:WORKBENCH_READING_MAX_ROWS]
    ]
    cut = read.truncated or len(rows) > WORKBENCH_READING_MAX_ROWS or kept != rows
    return _tables([SheetReading("", kept, cut)], False)


def _csv_rows(text: str) -> list[list[str]]:
    try:
        dialect: type[csv.Dialect] = csv.Sniffer().sniff(text[:_SNIFFED_CHARS], _DELIMITERS)
    except csv.Error:
        dialect = csv.excel
    # newline=None reads every line end, an old Mac's among them, as the reader expects.
    return [row for row in csv.reader(StringIO(text, newline=None), dialect) if row]


__all__ = ["can_be_shown", "preview_response", "shown_document"]
