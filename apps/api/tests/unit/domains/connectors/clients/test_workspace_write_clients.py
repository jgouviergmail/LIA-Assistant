"""Sheets/Docs WRITE client calls (lot F phase write, 2026-08).

Pins the exact Google payloads: Sheets writes go through the values
endpoints with USER_ENTERED input (so "=SUM(...)" and dates behave as if
typed by the user), Docs appends go through batchUpdate with
endOfSegmentLocation (no fragile index arithmetic).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.constants import SHEETS_READ_MAX_COLUMN
from src.domains.connectors.clients.google_docs_client import GoogleDocsClient
from src.domains.connectors.clients.google_sheets_client import GoogleSheetsClient

pytestmark = pytest.mark.unit


def _client(cls: type) -> object:
    instance = cls.__new__(cls)
    instance.user_id = uuid4()
    return instance


class TestSheetsInTheWordsOfBothDrives:
    async def test_rows_are_read_up_to_the_page(self) -> None:
        client = _client(GoogleSheetsClient)
        client.get_values = AsyncMock(return_value={"values": [["a"]]})  # type: ignore[attr-defined]

        rows = await client.read_rows("sheet-1", "Dépenses", 50)  # type: ignore[attr-defined]

        assert rows == [["a"]]
        client.get_values.assert_awaited_once_with(  # type: ignore[attr-defined]
            "sheet-1", f"'Dépenses'!A1:{SHEETS_READ_MAX_COLUMN}50"
        )

    async def test_a_sheet_with_no_values_reads_no_rows(self) -> None:
        client = _client(GoogleSheetsClient)
        client.get_values = AsyncMock(return_value={})  # type: ignore[attr-defined]

        assert await client.read_rows("sheet-1", "Vide", 5) == []  # type: ignore[attr-defined]

    async def test_a_quote_in_a_sheet_name_is_doubled_or_the_api_refuses_it(self) -> None:
        client = _client(GoogleSheetsClient)
        client.get_values = AsyncMock(return_value={})  # type: ignore[attr-defined]

        await client.read_rows("sheet-1", "Bob's data", 5)  # type: ignore[attr-defined]

        requested = client.get_values.await_args.args[1]  # type: ignore[attr-defined]
        assert requested.startswith("'Bob''s data'!")

    async def test_cells_are_written_on_their_sheet_and_counted_by_the_api(self) -> None:
        client = _client(GoogleSheetsClient)
        client.update_values = AsyncMock(return_value={"updatedCells": 2})  # type: ignore[attr-defined]

        count = await client.write_range(  # type: ignore[attr-defined]
            "sheet-1", "Dépenses", "B2:B3", [["1"], ["2"]]
        )

        assert count == 2
        client.update_values.assert_awaited_once_with(  # type: ignore[attr-defined]
            "sheet-1", "'Dépenses'!B2:B3", [["1"], ["2"]]
        )

    async def test_rows_are_added_below_the_sheets_table_and_counted_by_the_api(self) -> None:
        client = _client(GoogleSheetsClient)
        client.append_values = AsyncMock(  # type: ignore[attr-defined]
            return_value={"updates": {"updatedRows": 1}}
        )

        count = await client.append_rows("sheet-1", "Dépenses", [["x"]])  # type: ignore[attr-defined]

        assert count == 1
        client.append_values.assert_awaited_once_with(  # type: ignore[attr-defined]
            "sheet-1", "'Dépenses'!A1", [["x"]]
        )

    async def test_it_refuses_no_write_ahead(self) -> None:
        client = _client(GoogleSheetsClient)

        assert await client.write_refusal("B2", [["1"]]) is None  # type: ignore[attr-defined]


class TestDocsInTheWordsOfBothDrives:
    async def test_a_document_reads_as_its_title_and_its_text(self) -> None:
        client = _client(GoogleDocsClient)
        client.get_document = AsyncMock(  # type: ignore[attr-defined]
            return_value={
                "title": "Notes",
                "body": {
                    "content": [{"paragraph": {"elements": [{"textRun": {"content": "Salut\n"}}]}}]
                },
            }
        )

        read = await client.read_text("doc-1")  # type: ignore[attr-defined]

        assert read == {"title": "Notes", "content": "Salut"}

    async def test_its_title_is_the_one_it_holds(self) -> None:
        client = _client(GoogleDocsClient)
        client.get_document = AsyncMock(return_value={"title": "Notes"})  # type: ignore[attr-defined]

        assert await client.read_title("doc-1") == "Notes"  # type: ignore[attr-defined]


class TestSheetsWrites:
    async def test_update_values_puts_user_entered(self) -> None:
        client = _client(GoogleSheetsClient)
        spy = AsyncMock(return_value={"updatedCells": 4})
        client._make_request = spy  # type: ignore[attr-defined]

        result = await client.update_values(  # type: ignore[attr-defined]
            "sheet-1", "'Feuil1'!A1:B2", [["a", "b"], ["c", "d"]]
        )

        method, path = spy.call_args.args[:2]
        assert method == "PUT"
        # The A1 range is URL-encoded inside the path (quotes, !, accents).
        assert path.startswith("/spreadsheets/sheet-1/values/")
        assert "%21A1%3AB2" in path
        assert spy.call_args.kwargs["params"] == {"valueInputOption": "USER_ENTERED"}
        assert spy.call_args.kwargs["json_data"] == {"values": [["a", "b"], ["c", "d"]]}
        assert result["updatedCells"] == 4

    async def test_append_values_posts_to_the_append_endpoint(self) -> None:
        client = _client(GoogleSheetsClient)
        spy = AsyncMock(return_value={"updates": {"updatedRows": 1}})
        client._make_request = spy  # type: ignore[attr-defined]

        await client.append_values(  # type: ignore[attr-defined]
            "sheet-1", "'Feuil1'!A1", [["x", "y"]]
        )

        method, path = spy.call_args.args[:2]
        assert method == "POST"
        assert path.startswith("/spreadsheets/sheet-1/values/")
        assert path.endswith(":append")
        assert spy.call_args.kwargs["params"] == {"valueInputOption": "USER_ENTERED"}
        assert spy.call_args.kwargs["json_data"] == {"values": [["x", "y"]]}


class TestDocsAppend:
    async def test_append_text_uses_end_of_segment_location(self) -> None:
        client = _client(GoogleDocsClient)
        spy = AsyncMock(return_value={"documentId": "doc-1"})
        client._make_request = spy  # type: ignore[attr-defined]

        await client.append_text("doc-1", "Note ajoutée.")  # type: ignore[attr-defined]

        method, path = spy.call_args.args[:2]
        assert (method, path) == ("POST", "/documents/doc-1:batchUpdate")
        payload = spy.call_args.kwargs["json_data"]
        insert = payload["requests"][0]["insertText"]
        # endOfSegmentLocation appends at the body end without index math;
        # the leading newline separates the note from the existing content.
        assert insert["endOfSegmentLocation"] == {}
        assert insert["text"] == "\nNote ajoutée."
