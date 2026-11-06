"""What an Office file holds, read and added to from its bytes alone (ADR-369, lot 11).

A drive that gives bytes and no content API needs this: Graph's Excel API is absent from personal
accounts, and Word has none anywhere. Everything here is CPU on a file a third party may have
written: the archive's budget precedes every parser, every failure of a parser is one refusal,
and a caller runs these functions on a thread.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from io import BytesIO
from typing import TYPE_CHECKING, Any, Final
from zipfile import BadZipFile, ZipFile

import structlog

from src.core.constants import (
    OFFICE_ARCHIVE_MAX_PARTS,
    OFFICE_ARCHIVE_MAX_UNPACKED_BYTES,
    OFFICE_PARSE_SLOTS,
    SHEETS_READ_MAX_COLUMNS,
)

if TYPE_CHECKING:
    from docx.table import Table
    from docx.text.paragraph import Paragraph

logger = structlog.get_logger(__name__)

#: Word's built-in styles, by the name a file stores whatever language it was written in.
_HEADING_PREFIXES: Final[dict[str, str]] = {
    "Title": "# ",
    "Subtitle": "## ",
    **{f"Heading {level}": f"{'#' * level} " for level in range(1, 7)},
}
_LIST_STYLE_PREFIX: Final = "List"
#: What one worker parses at once: a parser holds many times the size of its file.
_PARSING: Final = threading.BoundedSemaphore(OFFICE_PARSE_SLOTS)


class OfficeRefusal(str, Enum):
    """Why a file's content cannot be read or written; each value says it to the caller."""

    NOT_THIS_FORMAT = "file_format_not_supported"
    TOO_LARGE = "file_too_large"
    UNREADABLE = "file_unreadable"
    WRITES_NOT_HELD = "spreadsheet_writes_not_held_by_this_drive"
    RANGE_REFUSED = "range_not_writable"
    CHANGED = "file_changed_meanwhile"
    LOCKED = "file_locked"


@dataclass(frozen=True, slots=True)
class SheetReading:
    """What a person reads of a sheet, and whether it holds more than that."""

    name: str
    rows: list[list[str]]
    cut: bool


class OfficeContentRefusedError(Exception):
    """A file's content refused, for the reason it carries."""

    def __init__(self, refusal: OfficeRefusal) -> None:
        super().__init__(refusal.value)
        self.refusal = refusal


def archive_within_budget(data: bytes) -> None:
    """Refuse an archive before any parser opens it.

    Raises:
        OfficeContentRefusedError: It is no archive, or it unpacks past its budget.
    """
    try:
        with ZipFile(BytesIO(data)) as archive:
            parts = archive.infolist()
    except BadZipFile as error:
        raise OfficeContentRefusedError(OfficeRefusal.UNREADABLE) from error
    unpacked = sum(part.file_size for part in parts)
    if len(parts) > OFFICE_ARCHIVE_MAX_PARTS or unpacked > OFFICE_ARCHIVE_MAX_UNPACKED_BYTES:
        raise OfficeContentRefusedError(OfficeRefusal.TOO_LARGE)


def _parsed[T](data: bytes, parse: Callable[[bytes], T]) -> T:
    """What ``parse`` makes of a file, within its budget and the worker's slots.

    A parser's failures have no common type, and name what the file holds: they are counted by
    their type alone, as one refusal.

    Raises:
        OfficeContentRefusedError: The file is past its budget, or the parser refused it.
    """
    archive_within_budget(data)
    with _PARSING:
        try:
            return parse(data)
        except OfficeContentRefusedError:
            raise
        except Exception as error:
            logger.info("office_file_unreadable", error_type=type(error).__name__)
            raise OfficeContentRefusedError(OfficeRefusal.UNREADABLE) from error


def _cell_text(value: object) -> str:
    """A cell as a person reads it; Excel's own text for what it stores as a number."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).upper()
    if isinstance(value, datetime):
        midnight = value.time() == time.min
        return value.date().isoformat() if midnight else value.isoformat(sep=" ")
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _row_text(row: tuple[object, ...]) -> list[str]:
    """A row up to its last value: what the Sheets API answers too."""
    cells = [_cell_text(value) for value in row]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def _open_workbook(data: bytes) -> Any:
    from openpyxl import load_workbook

    return load_workbook(BytesIO(data), read_only=True, data_only=True, keep_links=False)


def _outline(sheet: Any) -> dict[str, Any]:
    """A sheet in the words of Sheets; a size only where the file declares one."""
    properties: dict[str, Any] = {"title": sheet.title}
    if sheet.max_row and sheet.max_column:
        properties["gridProperties"] = {"rowCount": sheet.max_row, "columnCount": sheet.max_column}
    return {"properties": properties}


def read_sheets(data: bytes) -> list[dict[str, Any]]:
    """The sheets of a workbook.

    Args:
        data: The file's bytes.

    Returns:
        Each sheet's ``properties``, as the Sheets API words them.

    Raises:
        OfficeContentRefusedError: The file cannot be read.
    """

    def parse(content: bytes) -> list[dict[str, Any]]:
        book = _open_workbook(content)
        try:
            return [_outline(sheet) for sheet in book.worksheets]
        finally:
            book.close()

    return _parsed(data, parse)


def read_rows(data: bytes, sheet: str, max_rows: int) -> list[list[str]]:
    """The first rows of a sheet, as a person reads them.

    A formula reads as the value Excel last stored with it: nothing here computes.

    Args:
        data: The file's bytes.
        sheet: The sheet's exact title.
        max_rows: The most rows read.

    Returns:
        The rows, an empty one between two others kept, the empty ones after the last dropped.

    Raises:
        OfficeContentRefusedError: The file cannot be read, or holds no such sheet.
    """

    def parse(content: bytes) -> list[list[str]]:
        book = _open_workbook(content)
        try:
            rows = book[sheet].iter_rows(
                max_row=max_rows, max_col=SHEETS_READ_MAX_COLUMNS, values_only=True
            )
            read = [_row_text(row) for row in rows]
        finally:
            book.close()
        while read and not read[-1]:
            read.pop()
        return read

    return _parsed(data, parse)


def _sheet_reading(sheet: Any, rows: int, columns: int, cell_chars: int) -> SheetReading:
    """A sheet up to its bounds; a row or a column past them is read to know it is there."""
    read: list[list[str]] = []
    cut = False
    for index, row in enumerate(
        sheet.iter_rows(max_row=rows + 1, max_col=columns + 1, values_only=True)
    ):
        cells = _row_text(row)
        if index == rows:
            cut = cut or bool(cells)
            break
        cut = cut or len(cells) > columns or any(len(cell) > cell_chars for cell in cells)
        read.append([cell[:cell_chars] for cell in cells[:columns]])
    while read and not read[-1]:
        read.pop()
    return SheetReading(sheet.title, read, cut)


def read_workbook(
    data: bytes, *, sheets: int, rows: int, columns: int, cell_chars: int
) -> tuple[list[SheetReading], bool]:
    """A workbook as a person consults it, in one parse.

    Args:
        data: The file's bytes.
        sheets: The most sheets read.
        rows: The most rows read of a sheet.
        columns: The most columns read of a sheet.
        cell_chars: The most characters read of a cell.

    Returns:
        Its first sheets, and whether more follow.

    Raises:
        OfficeContentRefusedError: The file cannot be read.
    """

    def parse(content: bytes) -> tuple[list[SheetReading], bool]:
        book = _open_workbook(content)
        try:
            read = [
                _sheet_reading(sheet, rows, columns, cell_chars)
                for sheet in book.worksheets[:sheets]
            ]
            return read, len(book.worksheets) > sheets
        finally:
            book.close()

    return _parsed(data, parse)


def _shape_lines(shape: Any) -> Iterator[str]:
    """What a shape of a slide says: its paragraphs, or a table's rows."""
    if shape.has_text_frame:
        for paragraph in shape.text_frame.paragraphs:
            if text := paragraph.text.strip():
                yield text
    elif shape.has_table:
        for row in shape.table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                yield " | ".join(cells)


def _slide_lines(slide: Any) -> Iterator[str]:
    """What a slide says, what is said over it after."""
    for shape in slide.shapes:
        yield from _shape_lines(shape)
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
        if notes := slide.notes_slide.notes_text_frame.text.strip():
            yield notes


def read_slides_text(data: bytes) -> str:
    """A slide deck as text: its slides in order, a blank line between two.

    Args:
        data: The file's bytes.

    Returns:
        The text of every slide that has some, its tables and notes included.

    Raises:
        OfficeContentRefusedError: The file cannot be read.
    """

    def parse(content: bytes) -> str:
        from pptx import Presentation

        deck = Presentation(BytesIO(content))
        slides = ("\n".join(_slide_lines(slide)) for slide in deck.slides)
        return "\n\n".join(slide for slide in slides if slide)

    return _parsed(data, parse)


def _paragraph_line(paragraph: Paragraph) -> str | None:
    """A paragraph as the Docs reader words it; None when it says nothing."""
    text = paragraph.text.strip()
    if not text:
        return None
    style = paragraph.style.name if paragraph.style is not None else ""
    prefix = _HEADING_PREFIXES.get(style or "", "")
    numbered = paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None
    if not prefix and (numbered or (style or "").startswith(_LIST_STYLE_PREFIX)):
        prefix = "- "
    return f"{prefix}{text}"


def _table_lines(table: Table) -> Iterator[str]:
    """A table's rows, a merged cell read once."""
    for row in table.rows:
        cells = []
        for cell in row.cells:
            if not cells or cell._tc is not cells[-1]._tc:
                cells.append(cell)
        yield " | ".join(" ".join(cell.text.split()) for cell in cells)


def _word_blocks(parent: Any, body: Any) -> Iterator[Paragraph | Table]:
    """The paragraphs and tables under ``parent``, in order, a content control read through."""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in parent.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, body)
        elif child.tag == qn("w:tbl"):
            yield Table(child, body)
        elif child.tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                yield from _word_blocks(content, body)


def read_word_text(data: bytes) -> str:
    """A Word document as compact text: headings, lists and tables, in its order.

    Args:
        data: The file's bytes.

    Returns:
        The text, in the words of the Docs reader.

    Raises:
        OfficeContentRefusedError: The file cannot be read.
    """

    def parse(content: bytes) -> str:
        from docx import Document
        from docx.table import Table

        document = Document(BytesIO(content))
        body = document._body
        lines: list[str] = []
        for block in _word_blocks(document.element.body, body):
            if isinstance(block, Table):
                lines.extend(_table_lines(block))
            elif (line := _paragraph_line(block)) is not None:
                lines.append(line)
        return "\n".join(lines)

    return _parsed(data, parse)


def append_word_text(data: bytes, text: str) -> bytes:
    """A Word document with text added at its end, what it held left as it was.

    Args:
        data: The file's bytes.
        text: The text, one paragraph per line.

    Returns:
        The new file's bytes.

    Raises:
        OfficeContentRefusedError: The file cannot be read.
    """

    def parse(content: bytes) -> bytes:
        from docx import Document

        document = Document(BytesIO(content))
        for line in text.split("\n"):
            document.add_paragraph(line)
        written = BytesIO()
        document.save(written)
        return written.getvalue()

    return _parsed(data, parse)


__all__ = [
    "OfficeContentRefusedError",
    "OfficeRefusal",
    "SheetReading",
    "append_word_text",
    "read_rows",
    "read_sheets",
    "read_slides_text",
    "read_word_text",
    "read_workbook",
]
