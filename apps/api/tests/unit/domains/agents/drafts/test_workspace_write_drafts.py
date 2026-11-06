"""Sheets/Docs write draft chain (lot F phase write, 2026-08).

Writing into a user's spreadsheet or document goes through the full HITL
draft flow: the preview shows EXACTLY what will be written (verbatim
doctrine), and nothing touches the file until the user confirms.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.card_spec import to_markdown_lines
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.preview_renderer import (
    _render_document_append,
    _render_spreadsheet_write,
)
from src.domains.agents.tools.workspace_docs_tools import (
    execute_document_append_draft,
    execute_document_replace_draft,
    execute_spreadsheet_write_draft,
)
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal
from src.domains.connectors.models import ConnectorType

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
        joined = "\n".join(to_markdown_lines(lines, labels["separator"]))
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
        assert any("B2:B3" in line for line in to_markdown_lines(lines, labels["separator"]))

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
        joined = "\n".join(to_markdown_lines(lines, labels["separator"]))
        # Shown rows are bounded, and the hidden remainder is stated exactly.
        assert "(+15)" in joined

    def test_document_append_preview_shows_full_text(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_document_append(
            {"document_title": "Compte-rendu", "text": "Décision: reporter la réunion."},
            labels,
            lambda s: s or "",
        )
        joined = "\n".join(to_markdown_lines(lines, labels["separator"]))
        assert "Compte-rendu" in joined
        assert "Décision: reporter la réunion." in joined


_TOOLS = "src.domains.agents.tools.workspace_docs_tools"


def _deps(connected: ConnectorType = ConnectorType.GOOGLE_DRIVE) -> MagicMock:
    async def credentials(_user_id: Any, connector_type: ConnectorType) -> MagicMock | None:
        return MagicMock() if connector_type is connected else None

    service = MagicMock()
    service.get_connector_credentials = AsyncMock(side_effect=credentials)
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=service)
    return deps


@contextmanager
def _confirmed(door: str, content: MagicMock) -> Iterator[list[Any]]:
    """The door of the confirmed act, with the drives it was opened on."""
    opened_on: list[Any] = []

    @asynccontextmanager
    async def opened(drive: Any, _user_id: Any) -> AsyncIterator[MagicMock]:
        opened_on.append(drive)
        yield content

    drives = {
        connector_type: MagicMock(return_value=_drive(connector_type))
        for connector_type in (ConnectorType.GOOGLE_DRIVE, ConnectorType.MICROSOFT_ONEDRIVE)
    }
    with patch(f"{_TOOLS}.{door}", opened), patch.dict(f"{_TOOLS}._DRIVES", drives):
        yield opened_on


def _drive(connector_type: ConnectorType) -> MagicMock:
    drive = MagicMock(connector_type=connector_type)
    drive.close = AsyncMock()
    return drive


class TestExecutors:
    async def test_rows_are_added_to_the_sheet_the_card_named(self) -> None:
        sheets = MagicMock()
        sheets.append_rows = AsyncMock(return_value=2)

        with _confirmed("spreadsheets_of", sheets):
            result = await execute_spreadsheet_write_draft(
                {
                    "file_id": "sheet-1",
                    "sheet_name": "Dépenses",
                    "mode": "append",
                    "values": [["Loyer", "1200"], ["EDF", "80"]],
                },
                uuid4(),
                _deps(),
            )

        assert result == {"success": True, "mode": "append", "updated_rows": 2}
        sheets.append_rows.assert_awaited_once_with(
            "sheet-1", "Dépenses", [["Loyer", "1200"], ["EDF", "80"]]
        )

    async def test_cells_are_written_on_the_range_the_card_named(self) -> None:
        sheets = MagicMock()
        sheets.write_range = AsyncMock(return_value=2)

        with _confirmed("spreadsheets_of", sheets):
            result = await execute_spreadsheet_write_draft(
                {
                    "file_id": "sheet-1",
                    "sheet_name": "Dépenses",
                    "mode": "update",
                    "a1_range": "B2:B3",
                    "values": [["1300"], ["90"]],
                },
                uuid4(),
                _deps(),
            )

        assert result == {"success": True, "mode": "update", "updated_cells": 2}
        sheets.write_range.assert_awaited_once_with(
            "sheet-1", "Dépenses", "B2:B3", [["1300"], ["90"]]
        )

    async def test_a_rewrite_is_written_on_the_version_of_its_card(self) -> None:
        documents = MagicMock()
        documents.replace_text = AsyncMock()

        with _confirmed("documents_of", documents):
            result = await execute_document_replace_draft(
                {"file_id": "f1", "text": "New", "tag": "tag-1"}, uuid4(), _deps()
            )

        documents.replace_text.assert_awaited_once_with("f1", "New", "tag-1")
        assert result == {"success": True}

    @pytest.mark.parametrize(
        ("refusal", "code"),
        [(OfficeRefusal.CHANGED, "FILE_CHANGED"), (OfficeRefusal.LOCKED, "FILE_LOCKED")],
    )
    async def test_a_rewrite_refused_at_the_write_reads_on_the_card(
        self, refusal: OfficeRefusal, code: str
    ) -> None:
        documents = MagicMock()
        documents.replace_text = AsyncMock(side_effect=OfficeContentRefusedError(refusal))

        with _confirmed("documents_of", documents):
            result = await execute_document_replace_draft(
                {"file_id": "f1", "text": "New", "tag": "tag-1"}, uuid4(), _deps()
            )

        assert result["success"] is False
        assert result["error_code"] == code

    async def test_document_append_calls_append_text(self) -> None:
        documents = MagicMock()
        documents.append_text = AsyncMock(return_value={"documentId": "doc-1"})

        with _confirmed("documents_of", documents):
            result = await execute_document_append_draft(
                {"file_id": "doc-1", "text": "Nouvelle note."}, uuid4(), _deps()
            )

        assert result["success"] is True
        documents.append_text.assert_awaited_once_with("doc-1", "Nouvelle note.")

    @pytest.mark.parametrize(
        "connected", [ConnectorType.GOOGLE_DRIVE, ConnectorType.MICROSOFT_ONEDRIVE]
    )
    async def test_the_act_runs_on_the_drive_active_now_and_closes_it(
        self, connected: ConnectorType
    ) -> None:
        documents = MagicMock()
        documents.append_text = AsyncMock()

        with _confirmed("documents_of", documents) as opened_on:
            await execute_document_append_draft(
                {"file_id": "doc-1", "text": "x"}, uuid4(), _deps(connected)
            )

        assert [drive.connector_type for drive in opened_on] == [connected]
        opened_on[0].close.assert_awaited_once()

    @pytest.mark.parametrize(
        ("refusal", "code"),
        [
            (OfficeRefusal.CHANGED, "FILE_CHANGED"),
            (OfficeRefusal.LOCKED, "FILE_LOCKED"),
            (OfficeRefusal.UNREADABLE, "FILE_REFUSED"),
            (OfficeRefusal.TOO_LARGE, "FILE_REFUSED"),
        ],
    )
    async def test_a_document_refused_at_the_write_reads_on_the_card_by_its_reason(
        self, refusal: OfficeRefusal, code: str
    ) -> None:
        documents = MagicMock()
        documents.append_text = AsyncMock(side_effect=OfficeContentRefusedError(refusal))

        with _confirmed("documents_of", documents):
            result = await execute_document_append_draft(
                {"file_id": "doc-1", "text": "x"}, uuid4(), _deps(ConnectorType.MICROSOFT_ONEDRIVE)
            )

        assert result["success"] is False
        assert result["error_code"] == code

    async def test_a_sheet_refused_at_the_write_reads_on_the_card(self) -> None:
        sheets = MagicMock()
        sheets.append_rows = AsyncMock(
            side_effect=OfficeContentRefusedError(OfficeRefusal.WRITES_NOT_HELD)
        )

        with _confirmed("spreadsheets_of", sheets):
            result = await execute_spreadsheet_write_draft(
                {"file_id": "f1", "sheet_name": "S", "mode": "append", "values": [["1"]]},
                uuid4(),
                _deps(ConnectorType.MICROSOFT_ONEDRIVE),
            )

        assert result["error_code"] == "FILE_REFUSED"

    async def test_missing_connector_is_an_honest_failure(self) -> None:
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=None)
        deps = MagicMock()
        deps.get_connector_service = AsyncMock(return_value=service)
        result: dict[str, Any] = await execute_document_append_draft(
            {"file_id": "doc-1", "text": "x"}, uuid4(), deps
        )
        assert result["success"] is False
        # Typed, so the card can say which connector to reconnect.
        assert result["error_code"] == "CONNECTOR_NOT_ACTIVATED"
        assert result["connector_type"] == "google_drive"
