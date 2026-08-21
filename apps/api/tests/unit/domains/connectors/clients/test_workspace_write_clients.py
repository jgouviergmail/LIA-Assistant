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

from src.domains.connectors.clients.google_docs_client import GoogleDocsClient
from src.domains.connectors.clients.google_sheets_client import GoogleSheetsClient

pytestmark = pytest.mark.unit


def _client(cls: type) -> object:
    instance = cls.__new__(cls)
    instance.user_id = uuid4()
    return instance


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
