"""OneDrive's Office files, in the words of Sheets and Docs (ADR-369, lot 11).

A workbook and a document are read from their bytes: Graph's Excel API is absent from personal
accounts and Word has none. A workbook is written through that API where it exists and refused,
before any card, where it does not; a document is rewritten whole, conditioned on the tag it was
read at. The bytes here are real files: a double of the parsers would prove nothing.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from docx import Document
from openpyxl import Workbook

from src.core.constants import OFFICE_FILE_MAX_BYTES
from src.domains.connectors.clients.office_files import (
    OfficeContentRefusedError,
    OfficeRefusal,
    read_word_text,
)
from src.domains.connectors.clients.onedrive_office import (
    WORD_MIME_TYPE,
    OneDriveDocuments,
    OneDriveSpreadsheets,
)

pytestmark = pytest.mark.unit


def _book() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Dépenses"
    sheet.append(["Poste", "Montant"])
    sheet.append(["Loyer", 1200])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _document() -> bytes:
    document = Document()
    document.add_heading("Notes", level=1)
    document.add_paragraph("Existant")
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _drive(name: str, content: bytes | None, **item: Any) -> Any:
    drive = MagicMock()
    drive.get_file_metadata = AsyncMock(return_value={"name": name, "size": 10, **item})
    drive.get_file_content = AsyncMock(return_value=content)
    drive.drive_type = AsyncMock(return_value="business")
    drive.workbook_request = AsyncMock(return_value={"cellCount": 4, "rowCount": 2})
    drive.replace_content = AsyncMock(return_value={"id": "f1", "eTag": "tag-2"})
    return drive


class TestReadingAWorkbook:
    async def test_one_download_serves_its_sheets_and_its_rows(self) -> None:
        drive = _drive("Budget.xlsx", _book())
        sheets = OneDriveSpreadsheets(drive)

        outline = await sheets.get_spreadsheet("f1")
        rows = await sheets.read_rows("f1", "Dépenses", 10)

        assert outline["properties"]["title"] == "Budget.xlsx"
        assert [s["properties"]["title"] for s in outline["sheets"]] == ["Dépenses"]
        assert rows == [["Poste", "Montant"], ["Loyer", "1200"]]
        drive.get_file_content.assert_awaited_once_with(
            "f1", max_size_bytes=OFFICE_FILE_MAX_BYTES, known_size=10
        )

    @pytest.mark.parametrize("name", ["Budget.xls", "Budget.csv", "Budget.ods", "Budget"])
    async def test_another_format_is_refused_unread(self, name: str) -> None:
        drive = _drive(name, _book())

        with pytest.raises(OfficeContentRefusedError) as refused:
            await OneDriveSpreadsheets(drive).get_spreadsheet("f1")

        assert refused.value.refusal is OfficeRefusal.NOT_THIS_FORMAT
        drive.get_file_content.assert_not_awaited()

    @pytest.mark.parametrize("name", ["BUDGET.XLSX", "macro.xlsm"])
    async def test_a_workbook_is_known_by_its_name_whatever_its_case(self, name: str) -> None:
        outline = await OneDriveSpreadsheets(_drive(name, _book())).get_spreadsheet("f1")

        assert outline["properties"]["title"] == name

    async def test_a_file_past_the_ceiling_is_refused(self) -> None:
        with pytest.raises(OfficeContentRefusedError) as refused:
            await OneDriveSpreadsheets(_drive("Budget.xlsx", None)).get_spreadsheet("f1")

        assert refused.value.refusal is OfficeRefusal.TOO_LARGE

    async def test_an_item_with_no_bytes_is_refused(self) -> None:
        drive = _drive("Budget.xlsx", b"")
        drive.get_file_content = AsyncMock(side_effect=ValueError("no content"))

        with pytest.raises(OfficeContentRefusedError) as refused:
            await OneDriveSpreadsheets(drive).get_spreadsheet("f1")

        assert refused.value.refusal is OfficeRefusal.UNREADABLE


class TestWhatAWriteIsToldBeforeTheCard:
    async def test_a_personal_drive_holds_no_workbook_api(self) -> None:
        drive = _drive("Budget.xlsx", _book())
        drive.drive_type = AsyncMock(return_value="personal")

        refusal = await OneDriveSpreadsheets(drive).write_refusal("B2", [["1"]])

        assert refusal is OfficeRefusal.WRITES_NOT_HELD

    @pytest.mark.parametrize("kind", ["business", "documentLibrary"])
    async def test_a_work_drive_does(self, kind: str) -> None:
        drive = _drive("Budget.xlsx", _book())
        drive.drive_type = AsyncMock(return_value=kind)

        assert await OneDriveSpreadsheets(drive).write_refusal("B2", [["1"]]) is None

    async def test_rows_added_below_name_no_range(self) -> None:
        assert await OneDriveSpreadsheets(_drive("b.xlsx", None)).write_refusal("", [["1"]]) is None

    @pytest.mark.parametrize(
        "address", ["B", "2", "A1:B", "Feuil!A1", "A1')/x", "A1;B2", "A0", "ABCD1"]
    )
    async def test_what_is_no_plain_range_is_refused(self, address: str) -> None:
        sheets = OneDriveSpreadsheets(_drive("b.xlsx", None))

        assert await sheets.write_refusal(address, [["1"]]) is OfficeRefusal.RANGE_REFUSED

    async def test_values_that_overflow_their_range_are_refused(self) -> None:
        sheets = OneDriveSpreadsheets(_drive("b.xlsx", None))

        refusal = await sheets.write_refusal("A1:A2", [["1"], ["2"], ["3"]])

        assert refusal is OfficeRefusal.RANGE_REFUSED


class TestWritingCells:
    async def test_the_cells_go_where_the_card_said(self) -> None:
        drive = _drive("b.xlsx", None)

        count = await OneDriveSpreadsheets(drive).write_range(
            "f1", "Dépenses", "B2:C3", [["1", "2"], ["3", "4"]]
        )

        assert drive.workbook_request.await_args.args == (
            "PATCH",
            "f1",
            "worksheets/D%C3%A9penses/range(address='B2:C3')",
        )
        assert drive.workbook_request.await_args.kwargs == {
            "json_data": {"values": [["1", "2"], ["3", "4"]]}
        }
        assert count == 4

    async def test_one_cell_names_where_the_values_start(self) -> None:
        drive = _drive("b.xlsx", None)

        await OneDriveSpreadsheets(drive).write_range("f1", "S", "Y9", [["1", "2", "3"], ["4"]])

        assert "range(address='Y9:AA10')" in drive.workbook_request.await_args.args[2]

    async def test_a_range_wider_than_the_values_writes_only_them(self) -> None:
        """Graph asks a range the size of its values; Sheets leaves the rest alone."""
        drive = _drive("b.xlsx", None)

        await OneDriveSpreadsheets(drive).write_range("f1", "S", "A1:C3", [["1"]])

        assert "range(address='A1:A1')" in drive.workbook_request.await_args.args[2]

    async def test_a_short_row_leaves_the_cells_past_it_as_they_are(self) -> None:
        """Graph ignores a null, and takes an empty string as « clear this cell »."""
        drive = _drive("b.xlsx", None)

        await OneDriveSpreadsheets(drive).write_range("f1", "S", "A1", [["1", "2"], ["3"]])

        values = drive.workbook_request.await_args.kwargs["json_data"]["values"]
        assert values == [["1", "2"], ["3", None]]

    async def test_a_range_refused_at_the_card_is_refused_at_the_write(self) -> None:
        drive = _drive("b.xlsx", None)

        with pytest.raises(OfficeContentRefusedError) as refused:
            await OneDriveSpreadsheets(drive).write_range("f1", "S", "A1')/x", [["1"]])

        assert refused.value.refusal is OfficeRefusal.RANGE_REFUSED
        drive.workbook_request.assert_not_awaited()

    async def test_a_sheet_name_travels_as_one_segment(self) -> None:
        drive = _drive("b.xlsx", None)

        await OneDriveSpreadsheets(drive).write_range("f1", "a/../b", "A1", [["1"]])

        assert drive.workbook_request.await_args.args[2].startswith("worksheets/a%2F..%2Fb/")


class TestAddingRows:
    @staticmethod
    def _answers(*answers: dict[str, Any]) -> Any:
        drive = _drive("b.xlsx", None)
        drive.workbook_request = AsyncMock(side_effect=[*answers, {"rowCount": 2}])
        return drive

    async def test_they_go_below_what_the_sheet_uses(self) -> None:
        drive = self._answers({"rowIndex": 2, "rowCount": 5, "columnIndex": 1, "cellCount": 10})

        count = await OneDriveSpreadsheets(drive).append_rows("f1", "S", [["1", "2"], ["3", "4"]])

        assert "usedRange(valuesOnly=true)" in drive.workbook_request.await_args_list[0].args[2]
        assert "range(address='B8:C9')" in drive.workbook_request.await_args_list[1].args[2]
        assert count == 2

    async def test_a_blank_sheet_starts_at_its_top(self) -> None:
        used = {"rowIndex": 0, "rowCount": 1, "columnIndex": 0, "cellCount": 1}
        drive = self._answers(used, {"values": [[""]]})

        await OneDriveSpreadsheets(drive).append_rows("f1", "S", [["1"]])

        assert "range(address='A1:A1')" in drive.workbook_request.await_args_list[2].args[2]

    async def test_one_cell_that_holds_a_value_is_not_a_blank_sheet(self) -> None:
        used = {"rowIndex": 0, "rowCount": 1, "columnIndex": 0, "cellCount": 1}
        drive = self._answers(used, {"values": [["Titre"]]})

        await OneDriveSpreadsheets(drive).append_rows("f1", "S", [["1"]])

        assert "range(address='A2:A2')" in drive.workbook_request.await_args_list[2].args[2]


class TestADocument:
    async def test_it_reads_under_its_name(self) -> None:
        documents = OneDriveDocuments(_drive("Notes.docx", _document()))

        assert await documents.read_text("f1") == {
            "title": "Notes.docx",
            "content": "# Notes\nExistant",
        }

    async def test_its_title_costs_no_download(self) -> None:
        drive = _drive("Notes.docx", _document())

        assert await OneDriveDocuments(drive).read_title("f1") == "Notes.docx"
        drive.get_file_content.assert_not_awaited()

    @pytest.mark.parametrize("name", ["Notes.doc", "Notes.txt", "Notes.pdf"])
    async def test_another_format_is_refused_before_the_card(self, name: str) -> None:
        with pytest.raises(OfficeContentRefusedError) as refused:
            await OneDriveDocuments(_drive(name, None)).read_title("f1")

        assert refused.value.refusal is OfficeRefusal.NOT_THIS_FORMAT

    async def test_one_past_the_ceiling_is_refused_before_the_card(self) -> None:
        drive = _drive("Notes.docx", None, size=OFFICE_FILE_MAX_BYTES + 1)

        with pytest.raises(OfficeContentRefusedError) as refused:
            await OneDriveDocuments(drive).read_title("f1")

        assert refused.value.refusal is OfficeRefusal.TOO_LARGE

    async def test_text_is_written_on_the_tag_it_was_read_at(self) -> None:
        drive = _drive("Notes.docx", _document(), eTag="tag-1")

        await OneDriveDocuments(drive).append_text("f1", "Ajout")

        file_id, written, mime_type, tag = drive.replace_content.await_args.args
        assert (file_id, mime_type, tag) == ("f1", WORD_MIME_TYPE, "tag-1")
        assert read_word_text(written).endswith("Existant\nAjout")

    async def test_a_document_with_no_tag_is_not_written_blind(self) -> None:
        drive = _drive("Notes.docx", _document())

        with pytest.raises(OfficeContentRefusedError) as refused:
            await OneDriveDocuments(drive).append_text("f1", "Ajout")

        assert refused.value.refusal is OfficeRefusal.UNREADABLE
        drive.replace_content.assert_not_awaited()
