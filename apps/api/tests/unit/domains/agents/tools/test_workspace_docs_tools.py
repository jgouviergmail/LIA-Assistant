"""Read tools for Google Sheets/Docs content (lot F phase read, 2026-08).

Count doctrine pinned: the grid capacity (rowCount) is a CAPACITY, not a
data count — the tool states how many rows it returned and whether the read
was truncated, never a derived "total rows of data".
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.agents.tools.workspace_docs_tools import (
    ReadDocumentTool,
    ReadSpreadsheetTool,
)

pytestmark = pytest.mark.unit


def _tool(tool_class: Any) -> Any:
    tool = tool_class()
    tool.runtime = MagicMock()
    return tool


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
        client = MagicMock()
        client.get_spreadsheet = AsyncMock(return_value=dict(_SPREADSHEET_META))
        client.get_values = AsyncMock(
            return_value={"values": [["Poste", "Montant"], ["Loyer", "1200"]]}
        )

        result = await _tool(ReadSpreadsheetTool).execute_api_call(
            client, uuid4(), file_id="sheet-1"
        )

        assert result["success"] is True
        assert result["title"] == "Budget 2026"
        assert [s["title"] for s in result["sheets"]] == ["Dépenses", "Recettes"]
        assert result["sheet"] == "Dépenses"
        assert result["values"] == [["Poste", "Montant"], ["Loyer", "1200"]]
        assert result["returned_rows"] == 2
        assert result["truncated"] is False
        # The requested range targets the first sheet.
        assert "Dépenses" in client.get_values.call_args.args[1]

    async def test_named_sheet_is_matched_case_insensitively(self) -> None:
        client = MagicMock()
        client.get_spreadsheet = AsyncMock(return_value=dict(_SPREADSHEET_META))
        client.get_values = AsyncMock(return_value={"values": []})

        result = await _tool(ReadSpreadsheetTool).execute_api_call(
            client, uuid4(), file_id="sheet-1", sheet_name="recettes"
        )

        assert result["sheet"] == "Recettes"

    async def test_unknown_sheet_lists_available_ones(self) -> None:
        client = MagicMock()
        client.get_spreadsheet = AsyncMock(return_value=dict(_SPREADSHEET_META))

        result = await _tool(ReadSpreadsheetTool).execute_api_call(
            client, uuid4(), file_id="sheet-1", sheet_name="Inconnu"
        )

        assert result["success"] is False
        assert result["error"] == "sheet_not_found"
        assert result["available_sheets"] == ["Dépenses", "Recettes"]

    async def test_sheet_title_with_apostrophe_is_escaped_in_the_a1_range(self) -> None:
        # A1 notation quotes sheet names with single quotes; a quote INSIDE
        # the name must be doubled ("Bob's" → 'Bob''s') or the API 400s.
        meta = {
            "properties": {"title": "Perso"},
            "sheets": [
                {
                    "properties": {
                        "title": "Bob's data",
                        "gridProperties": {"rowCount": 10, "columnCount": 5},
                    }
                }
            ],
        }
        client = MagicMock()
        client.get_spreadsheet = AsyncMock(return_value=meta)
        client.get_values = AsyncMock(return_value={"values": []})

        result = await _tool(ReadSpreadsheetTool).execute_api_call(
            client, uuid4(), file_id="sheet-1"
        )

        assert result["success"] is True
        requested_range = client.get_values.call_args.args[1]
        assert requested_range.startswith("'Bob''s data'!")

    async def test_full_page_marks_possible_truncation(self) -> None:
        client = MagicMock()
        client.get_spreadsheet = AsyncMock(return_value=dict(_SPREADSHEET_META))
        client.get_values = AsyncMock(return_value={"values": [[str(i)] for i in range(5)]})

        result = await _tool(ReadSpreadsheetTool).execute_api_call(
            client, uuid4(), file_id="sheet-1", max_rows=5
        )

        assert result["returned_rows"] == 5
        assert result["truncated"] is True


class TestReadDocument:
    async def test_returns_markdown_text_with_title(self) -> None:
        client = MagicMock()
        client.get_document = AsyncMock(
            return_value={
                "title": "Compte-rendu",
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                "elements": [{"textRun": {"content": "Décisions\n"}}],
                            }
                        }
                    ]
                },
            }
        )

        result = await _tool(ReadDocumentTool).execute_api_call(client, uuid4(), file_id="doc-1")

        assert result["success"] is True
        assert result["title"] == "Compte-rendu"
        assert "# Décisions" in result["content"]
        assert result["truncated"] is False

    async def test_long_document_is_truncated_with_flag(self) -> None:
        client = MagicMock()
        long_text = "x" * 100_000
        client.get_document = AsyncMock(
            return_value={
                "title": "Long",
                "body": {
                    "content": [{"paragraph": {"elements": [{"textRun": {"content": long_text}}]}}]
                },
            }
        )

        result = await _tool(ReadDocumentTool).execute_api_call(client, uuid4(), file_id="doc-1")

        assert result["truncated"] is True
        assert len(result["content"]) < 100_000
