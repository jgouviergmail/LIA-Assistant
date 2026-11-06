"""The tools reading and preparing a spreadsheet or a document, on either drive.

Count doctrine pinned: the grid capacity (rowCount) is a CAPACITY, not a
data count — the tool states how many rows it returned and whether the read
was truncated, never a derived "total rows of data".
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import WORKSPACE_DOC_APPEND_MAX_CHARS
from src.domains.agents.tools.workspace_docs_tools import (
    AppendDocumentTextTool,
    ReadDocumentTool,
    ReadSpreadsheetTool,
    ReplaceDocumentTextTool,
    WriteSpreadsheetTool,
)
from src.domains.connectors.clients.drive_text import DriveText
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal

pytestmark = pytest.mark.unit

_TOOLS = "src.domains.agents.tools.workspace_docs_tools"


def _tool(tool_class: Any) -> Any:
    tool = tool_class()
    tool.runtime = MagicMock()
    return tool


@contextmanager
def _content(sheets: Any = None, documents: Any = None) -> Iterator[None]:
    """The door to the drive's content, answering with the doubles given."""

    def door(content: Any) -> Any:
        @asynccontextmanager
        async def opened(_drive: Any, _user_id: Any) -> AsyncIterator[Any]:
            yield content

        return opened

    with (
        patch(f"{_TOOLS}.spreadsheets_of", door(sheets)),
        patch(f"{_TOOLS}.documents_of", door(documents)),
    ):
        yield


def _sheets(rows: list[list[str]] | None = None, meta: dict[str, Any] | None = None) -> Any:
    sheets = MagicMock()
    sheets.get_spreadsheet = AsyncMock(return_value=meta or dict(_SPREADSHEET_META))
    sheets.read_rows = AsyncMock(return_value=rows or [])
    sheets.write_refusal = AsyncMock(return_value=None)
    return sheets


_SPREADSHEET_META: dict[str, Any] = {
    "properties": {"title": "Budget 2026"},
    "sheets": [
        {
            "properties": {
                "title": "Dépenses",
                "gridProperties": {"rowCount": 1000, "columnCount": 26},
            }
        },
        {
            "properties": {
                "title": "Recettes",
                "gridProperties": {"rowCount": 50, "columnCount": 10},
            }
        },
    ],
}


class TestReadSpreadsheet:
    async def test_reads_first_sheet_by_default_with_honest_counts(self) -> None:
        sheets = _sheets([["Poste", "Montant"], ["Loyer", "1200"]])

        with _content(sheets):
            result = await _tool(ReadSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="sheet-1"
            )

        assert result["success"] is True
        assert result["title"] == "Budget 2026"
        assert [s["title"] for s in result["sheets"]] == ["Dépenses", "Recettes"]
        assert result["sheet"] == "Dépenses"
        assert result["values"] == [["Poste", "Montant"], ["Loyer", "1200"]]
        assert result["returned_rows"] == 2
        assert result["truncated"] is False
        # The rows asked are the first sheet's.
        assert sheets.read_rows.await_args.args[:2] == ("sheet-1", "Dépenses")

    async def test_named_sheet_is_matched_case_insensitively(self) -> None:
        with _content(_sheets()):
            result = await _tool(ReadSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="sheet-1", sheet_name="recettes"
            )

        assert result["sheet"] == "Recettes"

    async def test_unknown_sheet_lists_available_ones(self) -> None:
        with _content(_sheets()):
            result = await _tool(ReadSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="sheet-1", sheet_name="Inconnu"
            )

        assert result["success"] is False
        assert result["error"] == "sheet_not_found"
        assert result["available_sheets"] == ["Dépenses", "Recettes"]

    async def test_a_size_the_file_does_not_declare_stays_unsaid(self) -> None:
        meta = {"properties": {"title": "Budget.xlsx"}, "sheets": [{"properties": {"title": "A"}}]}

        with _content(_sheets(meta=meta)):
            result = await _tool(ReadSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1"
            )

        assert result["sheets"] == [{"title": "A", "grid_rows": None, "grid_columns": None}]

    async def test_a_file_the_drive_cannot_read_says_why(self) -> None:
        sheets = _sheets()
        sheets.get_spreadsheet = AsyncMock(
            side_effect=OfficeContentRefusedError(OfficeRefusal.NOT_THIS_FORMAT)
        )

        with _content(sheets):
            result = await _tool(ReadSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1"
            )

        assert result["success"] is False
        assert result["error"] == OfficeRefusal.NOT_THIS_FORMAT.value
        assert result["message"]

    async def test_full_page_marks_possible_truncation(self) -> None:
        with _content(_sheets([[str(i)] for i in range(5)])):
            result = await _tool(ReadSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="sheet-1", max_rows=5
            )

        assert result["returned_rows"] == 5
        assert result["truncated"] is True


class TestReadDocument:
    @staticmethod
    async def _read(text: str) -> dict[str, Any]:
        documents = MagicMock()
        documents.read_text = AsyncMock(return_value={"title": "Compte-rendu", "content": text})
        with _content(documents=documents):
            return await _tool(ReadDocumentTool).execute_api_call(
                MagicMock(), uuid4(), file_id="doc-1"
            )

    async def test_returns_its_text_with_its_title(self) -> None:
        result = await self._read("# Décisions")

        assert result["success"] is True
        assert result["title"] == "Compte-rendu"
        assert result["content"] == "# Décisions"
        assert result["truncated"] is False

    async def test_long_document_is_truncated_with_flag(self) -> None:
        result = await self._read("x" * 100_000)

        assert result["truncated"] is True
        assert len(result["content"]) < 100_000

    async def test_a_file_the_drive_cannot_read_says_why(self) -> None:
        documents = MagicMock()
        documents.read_text = AsyncMock(
            side_effect=OfficeContentRefusedError(OfficeRefusal.UNREADABLE)
        )

        with _content(documents=documents):
            result = await _tool(ReadDocumentTool).execute_api_call(
                MagicMock(), uuid4(), file_id="doc-1"
            )

        assert result["success"] is False
        assert result["error"] == OfficeRefusal.UNREADABLE.value


class TestWhatARefusalTellsTheModel:
    @pytest.mark.parametrize("tool_class", [WriteSpreadsheetTool, AppendDocumentTextTool])
    def test_a_write_says_why_in_a_sentence(self, tool_class: Any) -> None:
        refused = {
            "success": False,
            "error": OfficeRefusal.WRITES_NOT_HELD.value,
            "message": "Why it cannot run.",
        }

        output = _tool(tool_class).format_registry_response(refused)

        assert output.message == "Why it cannot run."

    @pytest.mark.parametrize("tool_class", [WriteSpreadsheetTool, AppendDocumentTextTool])
    def test_a_refusal_of_the_request_itself_reads_by_its_code(self, tool_class: Any) -> None:
        output = _tool(tool_class).format_registry_response(
            {"success": False, "error": "values_required"}
        )

        assert output.message == "values required"


class TestPreparingAWrite:
    async def test_a_drive_that_cannot_write_refuses_before_the_card_and_unread(self) -> None:
        sheets = _sheets()
        sheets.write_refusal = AsyncMock(return_value=OfficeRefusal.WRITES_NOT_HELD)

        with _content(sheets):
            result = await _tool(WriteSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", values=[["1"]], mode="append"
            )

        assert result["success"] is False
        assert result["error"] == OfficeRefusal.WRITES_NOT_HELD.value
        sheets.get_spreadsheet.assert_not_awaited()

    async def test_the_range_of_an_update_is_the_one_judged(self) -> None:
        sheets = _sheets()

        with _content(sheets):
            await _tool(WriteSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", values=[["1"]], mode="update", a1_range="B2"
            )

        sheets.write_refusal.assert_awaited_once_with("B2", [["1"]])

    async def test_rows_added_below_name_no_range(self) -> None:
        sheets = _sheets()

        with _content(sheets):
            await _tool(WriteSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", values=[["1"]], mode="append", a1_range="B2"
            )

        sheets.write_refusal.assert_awaited_once_with("", [["1"]])

    async def test_a_file_that_cannot_be_read_is_refused_before_the_card(self) -> None:
        sheets = _sheets()
        sheets.get_spreadsheet = AsyncMock(
            side_effect=OfficeContentRefusedError(OfficeRefusal.TOO_LARGE)
        )

        with _content(sheets):
            result = await _tool(WriteSpreadsheetTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", values=[["1"]]
            )

        assert result["error"] == OfficeRefusal.TOO_LARGE.value

    async def test_a_document_names_its_card_by_its_title(self) -> None:
        documents = MagicMock()
        documents.read_title = AsyncMock(return_value="Notes.docx")

        with _content(documents=documents):
            result = await _tool(AppendDocumentTextTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", text="Ajout"
            )

        assert result == {
            "success": True,
            "file_id": "f1",
            "document_title": "Notes.docx",
            "text": "Ajout",
        }

    async def test_a_document_of_another_format_is_refused_before_the_card(self) -> None:
        documents = MagicMock()
        documents.read_title = AsyncMock(
            side_effect=OfficeContentRefusedError(OfficeRefusal.NOT_THIS_FORMAT)
        )

        with _content(documents=documents):
            result = await _tool(AppendDocumentTextTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", text="Ajout"
            )

        assert result["error"] == OfficeRefusal.NOT_THIS_FORMAT.value


class TestRewritingATextFile:
    """The text is the card's: it travels with the version the card was built on."""

    @staticmethod
    def _documents(read: Any = None) -> MagicMock:
        answer = read if read is not None else DriveText("notes.txt", "Old\n", "tag-1")
        return MagicMock(
            read_version=AsyncMock(
                side_effect=answer if isinstance(answer, Exception) else None,
                return_value=None if isinstance(answer, Exception) else answer,
            )
        )

    async def test_the_draft_carries_the_words_and_the_version_read(self) -> None:
        with _content(documents=self._documents()):
            result = await _tool(ReplaceDocumentTextTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", text="New\n"
            )

        assert result == {
            "success": True,
            "file_id": "f1",
            "document_title": "notes.txt",
            "text": "New\n",
            "tag": "tag-1",
        }

    async def test_a_rewrite_of_nothing_is_refused_before_any_read(self) -> None:
        documents = self._documents()

        with _content(documents=documents):
            result = await _tool(ReplaceDocumentTextTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", text="   "
            )

        assert result == {"success": False, "error": "text_required"}
        documents.read_version.assert_not_awaited()

    async def test_words_past_what_a_card_shows_are_refused(self) -> None:
        documents = self._documents()

        with _content(documents=documents):
            result = await _tool(ReplaceDocumentTextTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", text="x" * (WORKSPACE_DOC_APPEND_MAX_CHARS + 1)
            )

        assert result == {"success": False, "error": "text_too_long"}
        documents.read_version.assert_not_awaited()

    async def test_what_is_no_text_is_refused_by_its_reason(self) -> None:
        documents = self._documents(OfficeContentRefusedError(OfficeRefusal.NOT_THIS_FORMAT))

        with _content(documents=documents):
            result = await _tool(ReplaceDocumentTextTool).execute_api_call(
                MagicMock(), uuid4(), file_id="f1", text="New"
            )

        assert result["success"] is False
        assert result["error"] == OfficeRefusal.NOT_THIS_FORMAT.value
