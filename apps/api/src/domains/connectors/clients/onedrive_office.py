"""OneDrive's Office files, in the words of Sheets and Docs (ADR-369, lot 11).

Both are read from their bytes: Graph's Excel API is absent from personal accounts, and Word has
no content API anywhere. What differs is the write:

- A workbook is written through the Excel API, cell by cell, on a work drive; a personal drive
  holds no such API, and rewriting the file would lose what ``openpyxl`` does not carry (charts,
  pictures, macros): it is refused before any card.
- A document has nothing but its bytes: it is rewritten whole, conditioned on the tag it was read
  at. A person editing it meanwhile answers that write with a refusal, never with a lost edit.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Final

from src.core.constants import OFFICE_FILE_MAX_BYTES
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.clients.office_files import (
    OfficeContentRefusedError,
    OfficeRefusal,
    append_word_text,
    read_rows,
    read_sheets,
    read_word_text,
)
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

WORD_MIME_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
#: The files each parser reads; a legacy ``.xls`` or ``.doc`` is no archive.
_WORKBOOK_SUFFIXES: Final = (".xlsx", ".xlsm")
_WORD_SUFFIXES: Final = (".docx",)
_PERSONAL_DRIVE: Final = "personal"
#: A cell, or a rectangle of cells: an address travels in a path, so nothing else passes.
_ADDRESS: Final = re.compile(
    r"([A-Za-z]{1,3})([1-9][0-9]{0,6})(?::([A-Za-z]{1,3})([1-9][0-9]{0,6}))?"
)
_ALPHABET: Final = 26


def _column_number(letters: str) -> int:
    number = 0
    for letter in letters.upper():
        number = number * _ALPHABET + ord(letter) - ord("A") + 1
    return number


def _column_letters(number: int) -> str:
    letters = ""
    while number:
        number, rest = divmod(number - 1, _ALPHABET)
        letters = chr(ord("A") + rest) + letters
    return letters


def _width(values: list[list[str]]) -> int:
    return max((len(row) for row in values), default=0)


def _rectangle(column: int, row: int, values: list[list[str]]) -> str:
    """The address of ``values`` from a cell: Graph asks a range the size of its values."""
    last_column = _column_letters(column + _width(values) - 1)
    return f"{_column_letters(column)}{row}:{last_column}{row + len(values) - 1}"


def _written_address(a1_range: str, values: list[list[str]]) -> str:
    """The cells ``values`` take from ``a1_range``.

    One cell names where they start. A rectangle holds them or refuses them, as Sheets does: past
    it would be cells the card did not show.

    Raises:
        OfficeContentRefusedError: This is no plain range, or the values overflow it.
    """
    match = _ADDRESS.fullmatch(a1_range)
    if match is None:
        raise OfficeContentRefusedError(OfficeRefusal.RANGE_REFUSED)
    first_letters, first_row, last_letters, last_row = match.groups()
    column, row = _column_number(first_letters), int(first_row)
    if last_letters is not None:
        rows = int(last_row) - row + 1
        columns = _column_number(last_letters) - column + 1
        if len(values) > rows or _width(values) > columns:
            raise OfficeContentRefusedError(OfficeRefusal.RANGE_REFUSED)
    return _rectangle(column, row, values)


def _as_rectangle(values: list[list[str]]) -> list[list[str | None]]:
    """Rows of one width: Graph ignores a null, and reads an empty string as « clear this »."""
    width = _width(values)
    return [[*row, *([None] * (width - len(row)))] for row in values]


def _sheet_path(sheet: str) -> str:
    segment = path_segment(sheet, connector_type=ConnectorType.MICROSOFT_ONEDRIVE)
    return f"worksheets/{segment}"


def _must_be_named(item: dict[str, Any], suffixes: tuple[str, ...]) -> None:
    """Refuse a file of another format before a byte of it is read.

    Raises:
        OfficeContentRefusedError: Its name says it is something else.
    """
    if not str(item.get("name") or "").casefold().endswith(suffixes):
        raise OfficeContentRefusedError(OfficeRefusal.NOT_THIS_FORMAT)


async def _file_of(
    drive: MicrosoftOneDriveClient, file_id: str, suffixes: tuple[str, ...]
) -> tuple[dict[str, Any], bytes]:
    """A file's item and its bytes, never past the ceiling.

    Raises:
        OfficeContentRefusedError: Another format, past the ceiling, or no bytes at all.
    """
    item = await drive.get_file_metadata(file_id)
    _must_be_named(item, suffixes)
    try:
        data = await drive.get_file_content(
            file_id, max_size_bytes=OFFICE_FILE_MAX_BYTES, known_size=item.get("size")
        )
    except ValueError as error:
        raise OfficeContentRefusedError(OfficeRefusal.UNREADABLE) from error
    if data is None:
        raise OfficeContentRefusedError(OfficeRefusal.TOO_LARGE)
    return item, data


class OneDriveSpreadsheets:
    """OneDrive's workbooks, for one act: its download serves all its reads."""

    def __init__(self, drive: MicrosoftOneDriveClient) -> None:
        self._drive = drive
        self._read: dict[str, tuple[str, bytes]] = {}

    async def get_spreadsheet(self, spreadsheet_id: str) -> dict[str, Any]:
        """A workbook's name and sheets, as the Sheets API words them."""
        name, data = await self._workbook(spreadsheet_id)
        return {
            "properties": {"title": name},
            "sheets": await asyncio.to_thread(read_sheets, data),
        }

    async def read_rows(self, spreadsheet_id: str, sheet: str, max_rows: int) -> list[list[str]]:
        """The first rows of a sheet."""
        _, data = await self._workbook(spreadsheet_id)
        return await asyncio.to_thread(read_rows, data, sheet, max_rows)

    async def write_refusal(self, a1_range: str, values: list[list[str]]) -> OfficeRefusal | None:
        """Why this write cannot run, said before the card shows it.

        Args:
            a1_range: The cells named, empty for rows added below the sheet's table.
            values: The rows.

        Returns:
            The refusal, or None.
        """
        if a1_range:
            try:
                _written_address(a1_range, values)
            except OfficeContentRefusedError as error:
                return error.refusal
        kind = await self._drive.drive_type()
        return OfficeRefusal.WRITES_NOT_HELD if kind == _PERSONAL_DRIVE else None

    async def write_range(
        self, spreadsheet_id: str, sheet: str, a1_range: str, values: list[list[str]]
    ) -> int:
        """Overwrite cells of a sheet.

        Returns:
            The cells Graph says it wrote.

        Raises:
            OfficeContentRefusedError: The range is no plain range, or the values overflow it.
        """
        address = _written_address(a1_range, values)
        return int(
            (await self._written(spreadsheet_id, sheet, address, values)).get("cellCount", 0)
        )

    async def append_rows(self, spreadsheet_id: str, sheet: str, values: list[list[str]]) -> int:
        """Add rows below what a sheet uses, from its first used column.

        Returns:
            The rows Graph says it wrote.
        """
        column, row = await self._next_row(spreadsheet_id, sheet)
        address = _rectangle(column, row, values)
        return int((await self._written(spreadsheet_id, sheet, address, values)).get("rowCount", 0))

    async def _workbook(self, spreadsheet_id: str) -> tuple[str, bytes]:
        if spreadsheet_id not in self._read:
            item, data = await _file_of(self._drive, spreadsheet_id, _WORKBOOK_SUFFIXES)
            self._read[spreadsheet_id] = str(item.get("name")), data
        return self._read[spreadsheet_id]

    async def _written(
        self, spreadsheet_id: str, sheet: str, address: str, values: list[list[str]]
    ) -> dict[str, Any]:
        return await self._drive.workbook_request(
            "PATCH",
            spreadsheet_id,
            f"{_sheet_path(sheet)}/range(address='{address}')",
            json_data={"values": _as_rectangle(values)},
        )

    async def _next_row(self, spreadsheet_id: str, sheet: str) -> tuple[int, int]:
        """The first free row under what a sheet uses, and the column it starts from.

        A blank sheet answers with its first cell, used by nothing: only reading it tells the two.
        """
        used_range = f"{_sheet_path(sheet)}/usedRange(valuesOnly=true)"
        used = await self._drive.workbook_request(
            "GET",
            spreadsheet_id,
            used_range,
            params={"$select": "rowIndex,rowCount,columnIndex,cellCount"},
        )
        column = int(used.get("columnIndex") or 0) + 1
        row = int(used.get("rowIndex") or 0) + int(used.get("rowCount") or 0) + 1
        if used.get("cellCount") == 1:
            cell = await self._drive.workbook_request(
                "GET", spreadsheet_id, used_range, params={"$select": "values"}
            )
            if cell.get("values") == [[""]]:
                return column, row - 1
        return column, row


class OneDriveDocuments:
    """OneDrive's Word documents."""

    def __init__(self, drive: MicrosoftOneDriveClient) -> None:
        self._drive = drive

    async def read_text(self, document_id: str) -> dict[str, str]:
        """A document's name and its text."""
        item, data = await _file_of(self._drive, document_id, _WORD_SUFFIXES)
        return {
            "title": str(item.get("name")),
            "content": await asyncio.to_thread(read_word_text, data),
        }

    async def read_title(self, document_id: str) -> str:
        """A document's name, once it is one this drive can add to.

        Raises:
            OfficeContentRefusedError: Another format, or past the ceiling.
        """
        item = await self._drive.get_file_metadata(document_id)
        _must_be_named(item, _WORD_SUFFIXES)
        if int(item.get("size") or 0) > OFFICE_FILE_MAX_BYTES:
            raise OfficeContentRefusedError(OfficeRefusal.TOO_LARGE)
        return str(item.get("name"))

    async def append_text(self, document_id: str, text: str) -> None:
        """Add text at a document's end, on the tag it was read at.

        Raises:
            OfficeContentRefusedError: It cannot be read, or it is not written: someone changed
                it meanwhile, or holds it locked.
        """
        item, data = await _file_of(self._drive, document_id, _WORD_SUFFIXES)
        tag = item.get("eTag")
        if not isinstance(tag, str) or not tag:
            raise OfficeContentRefusedError(OfficeRefusal.UNREADABLE)
        written = await asyncio.to_thread(append_word_text, data, text)
        await self._drive.replace_content(document_id, written, WORD_MIME_TYPE, tag)


__all__ = ["WORD_MIME_TYPE", "OneDriveDocuments", "OneDriveSpreadsheets"]
