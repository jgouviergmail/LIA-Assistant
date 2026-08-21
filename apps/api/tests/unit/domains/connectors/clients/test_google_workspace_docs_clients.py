"""Sheets + Docs clients (lot F phase read, 2026-08).

Both ride the existing GOOGLE_DRIVE OAuth token (the Sheets and Docs APIs
accept the already-granted `auth/drive` scope — no re-consent). Request
shapes are the contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_docs_client import (
    GoogleDocsClient,
    docs_structure_to_text,
)
from src.domains.connectors.clients.google_sheets_client import GoogleSheetsClient
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit


def _client(cls):  # type: ignore[no-untyped-def]
    instance = cls.__new__(cls)
    instance.user_id = uuid4()
    return instance


class TestSheetsClient:
    def test_rides_the_drive_connector_token(self) -> None:
        assert GoogleSheetsClient.connector_type is ConnectorType.GOOGLE_DRIVE

    async def test_get_spreadsheet_requests_titles_and_exact_grid_sizes(self) -> None:
        client = _client(GoogleSheetsClient)
        spy = AsyncMock(return_value={"sheets": []})
        client._make_request = spy  # type: ignore[method-assign]

        await client.get_spreadsheet("sheet-id-1")

        assert spy.call_args.args[:2] == ("GET", "/spreadsheets/sheet-id-1")
        fields = spy.call_args.kwargs["params"]["fields"]
        assert "gridProperties" in fields and "title" in fields

    async def test_get_values_uses_a1_range(self) -> None:
        client = _client(GoogleSheetsClient)
        spy = AsyncMock(return_value={"values": [["a", "b"]]})
        client._make_request = spy  # type: ignore[method-assign]

        result = await client.get_values("sheet-id-1", "'Feuille 1'!A1:ZZ50")

        assert spy.call_args.args[0] == "GET"
        assert spy.call_args.args[1].startswith("/spreadsheets/sheet-id-1/values/")
        # The A1 range must be URL-encoded (quotes, spaces, !).
        assert " " not in spy.call_args.args[1]
        assert result["values"] == [["a", "b"]]


class TestDocsClient:
    def test_rides_the_drive_connector_token(self) -> None:
        assert GoogleDocsClient.connector_type is ConnectorType.GOOGLE_DRIVE

    async def test_get_document_fetches_body(self) -> None:
        client = _client(GoogleDocsClient)
        spy = AsyncMock(return_value={"title": "Doc", "body": {"content": []}})
        client._make_request = spy  # type: ignore[method-assign]

        result = await client.get_document("doc-id-1")

        assert spy.call_args.args[:2] == ("GET", "/documents/doc-id-1")
        assert result["title"] == "Doc"


def _paragraph(text: str, style: str | None = None, bullet: bool = False) -> dict:
    paragraph: dict = {"elements": [{"textRun": {"content": text + "\n"}}]}
    if style:
        paragraph["paragraphStyle"] = {"namedStyleType": style}
    element: dict = {"paragraph": paragraph}
    if bullet:
        paragraph["bullet"] = {"listId": "list1"}
    return element


class TestDocsStructureToText:
    def test_headings_lists_and_paragraphs_render_as_markdown(self) -> None:
        content = [
            _paragraph("Titre principal", style="HEADING_1"),
            _paragraph("Un paragraphe simple."),
            _paragraph("Premier point", bullet=True),
            _paragraph("Deuxième point", bullet=True),
            _paragraph("Sous-titre", style="HEADING_2"),
        ]
        text = docs_structure_to_text({"body": {"content": content}})
        assert "# Titre principal" in text
        assert "Un paragraphe simple." in text
        assert "- Premier point" in text
        assert "## Sous-titre" in text

    def test_tables_render_rows_with_pipes(self) -> None:
        table = {
            "table": {
                "tableRows": [
                    {
                        "tableCells": [
                            {"content": [_paragraph("Nom")]},
                            {"content": [_paragraph("Prix")]},
                        ]
                    },
                    {
                        "tableCells": [
                            {"content": [_paragraph("Pomme")]},
                            {"content": [_paragraph("2€")]},
                        ]
                    },
                ]
            }
        }
        text = docs_structure_to_text({"body": {"content": [table]}})
        assert "Nom | Prix" in text
        assert "Pomme | 2€" in text

    def test_empty_document(self) -> None:
        assert docs_structure_to_text({"body": {"content": []}}) == ""
