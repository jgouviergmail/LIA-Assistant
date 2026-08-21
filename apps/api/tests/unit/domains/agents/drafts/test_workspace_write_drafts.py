"""Sheets/Docs write draft chain (lot F phase write, 2026-08).

Writing into a user's spreadsheet or document goes through the full HITL
draft flow: the preview shows EXACTLY what will be written (verbatim
doctrine), and nothing touches the file until the user confirms.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.preview_renderer import (
    _render_document_append,
    _render_spreadsheet_write,
)
from src.domains.agents.tools.workspace_docs_tools import (
    execute_document_append_draft,
    execute_spreadsheet_write_draft,
)

pytestmark = pytest.mark.unit


class TestDraftTypes:
    def test_types_exist(self) -> None:
        assert DraftType.SPREADSHEET_WRITE.value == "spreadsheet_write"
        assert DraftType.DOCUMENT_APPEND.value == "document_append"


class TestPreviews:
    def test_append_preview_shows_file_sheet_and_every_row(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_spreadsheet_write(
            {
                "spreadsheet_title": "Budget 2026",
                "sheet_name": "Dépenses",
                "mode": "append",
                "values": [["Loyer", "1200"], ["EDF", "80"]],
            },
            labels,
            lambda s: s or "",
        )
        joined = "\n".join(lines)
        assert "Budget 2026" in joined
        assert "Dépenses" in joined
        assert "Loyer | 1200" in joined
        assert "EDF | 80" in joined

    def test_update_preview_shows_the_target_range(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_spreadsheet_write(
            {
                "spreadsheet_title": "Budget 2026",
                "sheet_name": "Dépenses",
                "mode": "update",
                "a1_range": "B2:B3",
                "values": [["1300"], ["90"]],
            },
            labels,
            lambda s: s or "",
        )
        assert any("B2:B3" in line for line in lines)

    def test_long_value_list_is_truncated_with_exact_count(self) -> None:
        labels = get_draft_preview_labels("fr")
        values = [[str(i)] for i in range(25)]
        lines = _render_spreadsheet_write(
            {
                "spreadsheet_title": "T",
                "sheet_name": "S",
                "mode": "append",
                "values": values,
            },
            labels,
            lambda s: s or "",
        )
        joined = "\n".join(lines)
        # Shown rows are bounded, and the hidden remainder is stated exactly.
        assert "(+15)" in joined

    def test_document_append_preview_shows_full_text(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_document_append(
            {"document_title": "Compte-rendu", "text": "Décision: reporter la réunion."},
            labels,
            lambda s: s or "",
        )
        joined = "\n".join(lines)
        assert "Compte-rendu" in joined
        assert "Décision: reporter la réunion." in joined


def _deps_with_client(client: MagicMock) -> MagicMock:
    service = MagicMock()
    service.get_connector_credentials = AsyncMock(return_value=MagicMock())
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=service)
    return deps


class TestExecutors:
    async def test_append_mode_calls_append_values(self) -> None:
        client = MagicMock()
        client.append_values = AsyncMock(return_value={"updates": {"updatedRows": 2}})
        with patch(
            "src.domains.agents.tools.workspace_docs_tools.GoogleSheetsClient",
            return_value=client,
        ):
            result = await execute_spreadsheet_write_draft(
                {
                    "file_id": "sheet-1",
                    "sheet_name": "Dépenses",
                    "mode": "append",
                    "values": [["Loyer", "1200"], ["EDF", "80"]],
                },
                uuid4(),
                _deps_with_client(client),
            )
        assert result["success"] is True
        assert result["updated_rows"] == 2
        args = client.append_values.call_args.args
        assert args[0] == "sheet-1"
        assert args[1] == "'Dépenses'!A1"
        assert args[2] == [["Loyer", "1200"], ["EDF", "80"]]

    async def test_update_mode_calls_update_values_on_the_range(self) -> None:
        client = MagicMock()
        client.update_values = AsyncMock(return_value={"updatedCells": 2})
        with patch(
            "src.domains.agents.tools.workspace_docs_tools.GoogleSheetsClient",
            return_value=client,
        ):
            result = await execute_spreadsheet_write_draft(
                {
                    "file_id": "sheet-1",
                    "sheet_name": "Dépenses",
                    "mode": "update",
                    "a1_range": "B2:B3",
                    "values": [["1300"], ["90"]],
                },
                uuid4(),
                _deps_with_client(client),
            )
        assert result["success"] is True
        assert result["updated_cells"] == 2
        assert client.update_values.call_args.args[1] == "'Dépenses'!B2:B3"

    async def test_document_append_calls_append_text(self) -> None:
        client = MagicMock()
        client.append_text = AsyncMock(return_value={"documentId": "doc-1"})
        with patch(
            "src.domains.agents.tools.workspace_docs_tools.GoogleDocsClient",
            return_value=client,
        ):
            result = await execute_document_append_draft(
                {"file_id": "doc-1", "text": "Nouvelle note."},
                uuid4(),
                _deps_with_client(client),
            )
        assert result["success"] is True
        client.append_text.assert_awaited_once_with("doc-1", "Nouvelle note.")

    async def test_missing_connector_is_an_honest_failure(self) -> None:
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=None)
        deps = MagicMock()
        deps.get_connector_service = AsyncMock(return_value=service)
        result: dict[str, Any] = await execute_document_append_draft(
            {"file_id": "doc-1", "text": "x"}, uuid4(), deps
        )
        assert result["success"] is False
        assert result["error"] == "connector_not_activated"
