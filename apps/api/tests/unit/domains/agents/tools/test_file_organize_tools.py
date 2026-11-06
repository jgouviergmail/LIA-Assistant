"""The assistant organises the person's files, on Drive and OneDrive (ADR-369, lot 6, D2)."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import ONEDRIVE_REFUSED_NAME_CHARACTERS
from src.core.exceptions import ConnectorAPIError
from src.domains.agents.drive.organize_manifest import (
    FILE_ACTIONS,
    FILE_NAME_DESCRIPTION,
    FILE_SOURCE_DESCRIPTION,
    manage_files_catalogue_manifest,
)
from src.domains.agents.tools import file_organize_tools as organize_tools
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.file_organize_tools import (
    ManageFilesTool,
    StoredFile,
    manage_files_tool,
)
from src.domains.connectors.clients.files_management import (
    FileNameRefusedError,
    FileNameTakenError,
)

pytestmark = pytest.mark.unit

USER = uuid4()
ITEM = {"id": "f1", "name": "Notes", "mimeType": "text/plain"}


def _client(**answers: Any) -> Any:
    client = MagicMock(
        create_folder=AsyncMock(return_value=ITEM),
        rename_file=AsyncMock(return_value=ITEM),
        move_file=AsyncMock(return_value=ITEM),
        copy_file=AsyncMock(return_value=ITEM),
    )
    client.configure_mock(**answers)
    return client


async def _run(client: Any, **kwargs: Any) -> dict[str, Any]:
    return await ManageFilesTool().execute_api_call(client, USER, **kwargs)


class TestTheContract:
    def test_each_act_is_undone_by_one_more_call(self) -> None:
        assert manage_files_catalogue_manifest.mutation_policy == "reversible"

    def test_the_actions_are_published_as_the_tool_reads_them(self) -> None:
        action = next(p for p in manage_files_catalogue_manifest.parameters if p.name == "action")
        assert tuple(action.constraints[0].value) == FILE_ACTIONS

    def test_manifest_and_schema_read_one_wording(self) -> None:
        schema = manage_files_tool.tool_call_schema.model_json_schema()
        assert schema["properties"]["name"]["description"] == FILE_NAME_DESCRIPTION
        assert schema["properties"]["file_name"]["description"] == FILE_SOURCE_DESCRIPTION


class TestTheActs:
    async def test_a_folder_goes_at_the_top_unless_a_parent_is_named(self) -> None:
        client = _client()

        result = await _run(client, action="create_folder", name="Invoices")

        client.create_folder.assert_awaited_once_with("Invoices", "root")
        assert result["item"]["id"] == "f1"

    async def test_a_folder_goes_in_the_parent_named(self) -> None:
        client = _client()

        await _run(client, action="create_folder", name="Invoices", folder_id="d1")

        client.create_folder.assert_awaited_once_with("Invoices", "d1")

    async def test_a_rename_reaches_the_client(self) -> None:
        client = _client()

        await _run(client, action="rename", file_id="f1", name="Report.pdf")

        client.rename_file.assert_awaited_once_with("f1", "Report.pdf")

    async def test_a_move_reaches_the_client(self) -> None:
        client = _client()

        await _run(client, action="move", file_id="f1", folder_id="d1")

        client.move_file.assert_awaited_once_with("f1", "d1")

    async def test_a_move_with_no_folder_goes_to_the_top(self) -> None:
        client = _client()

        await _run(client, action="move", file_id="f1")

        client.move_file.assert_awaited_once_with("f1", "root")

    async def test_a_restore_takes_it_out_of_the_trash(self) -> None:
        client = _client(restore_file=AsyncMock(return_value=ITEM))

        result = await _run(client, action="restore", file_id="f1")

        client.restore_file.assert_awaited_once_with("f1")
        assert result["item"]["id"] == "f1"

    def test_nothing_deletes_for_good_owner_decision_a2(self) -> None:
        assert not {"delete", "delete_forever", "empty_trash"}.intersection(FILE_ACTIONS)

    async def test_a_copy_answers_the_copy(self) -> None:
        client = _client()

        result = await _run(client, action="copy", file_id="f1", folder_id="d1", name="Mine")

        client.copy_file.assert_awaited_once_with("f1", "d1", "Mine")
        assert result["copying"] is False

    async def test_a_copy_the_provider_finishes_later_says_so(self) -> None:
        client = _client(copy_file=AsyncMock(return_value=None))

        result = await _run(client, action="copy", file_id="f1")

        client.copy_file.assert_awaited_once_with("f1", None, None)
        assert result["copying"] is True
        assert result["item"] is None


STORED = StoredFile(name="Report.pdf", relative_path="u/r.pdf", mime_type="application/pdf", size=3)


class TestAnUpload:
    @pytest.fixture
    def disk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
        (tmp_path / "u").mkdir()
        (tmp_path / "u" / "r.pdf").write_bytes(b"pdf")
        return tmp_path

    @staticmethod
    def _held(stored: StoredFile | None = STORED) -> Any:
        return patch.object(organize_tools, "_stored_file", AsyncMock(return_value=stored))

    async def test_the_file_named_goes_to_the_top_by_default(self, disk: Path) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with self._held() as held:
            result = await _run(client, action="upload", file_name="Report.pdf")

        held.assert_awaited_once_with(USER, "Report.pdf")
        client.upload_file.assert_awaited_once_with("Report.pdf", b"pdf", "application/pdf", "root")
        assert result["item"]["id"] == "f1"

    async def test_it_goes_where_it_is_asked_under_the_name_asked(self, disk: Path) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with self._held():
            await _run(
                client, action="upload", file_name="Report.pdf", folder_id="d1", name="Mine.pdf"
            )

        client.upload_file.assert_awaited_once_with("Mine.pdf", b"pdf", "application/pdf", "d1")

    async def test_a_name_nothing_answers_to_is_said(self) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with self._held(None):
            result = await _run(client, action="upload", file_name="Nothing.pdf")

        assert result["error_code"] == ToolErrorCode.NOT_FOUND.value
        client.upload_file.assert_not_awaited()

    async def test_a_file_gone_from_the_disk_is_said(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with self._held():
            result = await _run(client, action="upload", file_name="Report.pdf")

        assert result["error_code"] == ToolErrorCode.NOT_FOUND.value
        client.upload_file.assert_not_awaited()

    async def test_a_file_past_the_published_ceiling_reads_nothing(
        self, disk: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "workbench_upload_max_bytes", 2)
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with self._held():
            result = await _run(client, action="upload", file_name="Report.pdf")

        assert result["error_code"] == ToolErrorCode.CONSTRAINT_VIOLATION.value
        assert "2" in result["message"]
        client.upload_file.assert_not_awaited()

    async def test_a_name_held_in_the_folder_is_said(self, disk: Path) -> None:
        client = _client(upload_file=AsyncMock(side_effect=FileNameTakenError))

        with self._held():
            result = await _run(client, action="upload", file_name="Report.pdf")

        assert result["error_code"] == ToolErrorCode.CONSTRAINT_VIOLATION.value

    async def test_the_read_ends_with_its_session_before_anything_leaves(self) -> None:
        """No transaction stays open across a network call (ADR-304)."""
        entered: list[str] = []

        @contextlib.asynccontextmanager
        async def session() -> AsyncIterator[Any]:
            entered.append("open")
            yield MagicMock()
            entered.append("closed")

        row = MagicMock(
            original_filename="Report.pdf",
            file_path="u/r.pdf",
            mime_type="application/pdf",
            file_size=3,
        )
        repository = MagicMock(newest_by_filename=AsyncMock(return_value=row))
        with (
            patch.object(organize_tools, "get_db_context", session),
            patch.object(organize_tools, "AttachmentRepository", return_value=repository),
        ):
            found = await organize_tools._stored_file(USER, "Report.pdf")

        assert entered == ["open", "closed"]
        assert found == STORED


class TestTheRefusals:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"action": "erase", "file_id": "f1"},
            {"action": "create_folder"},
            {"action": "rename", "file_id": "f1"},
            {"action": "rename", "name": "x"},
            {"action": "move"},
            {"action": "copy"},
            {"action": "restore"},
            {"action": "create_folder", "name": "a/b"},
            {"action": "rename", "file_id": "f1", "name": "a\\b"},
            {"action": "upload"},
            {"action": "upload", "file_name": "a.pdf", "name": "a/b"},
        ],
    )
    async def test_what_lacks_is_said_before_any_call(self, kwargs: dict[str, Any]) -> None:
        client = _client()

        result = await _run(client, **kwargs)

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        client.create_folder.assert_not_awaited()
        client.rename_file.assert_not_awaited()

    async def test_a_name_taken_is_said(self) -> None:
        client = _client(create_folder=AsyncMock(side_effect=FileNameTakenError))

        result = await _run(client, action="create_folder", name="Invoices")

        assert result["error_code"] == ToolErrorCode.CONSTRAINT_VIOLATION.value

    async def test_a_name_the_drive_refuses_is_said_with_the_characters(self) -> None:
        client = _client(rename_file=AsyncMock(side_effect=FileNameRefusedError))

        result = await _run(client, action="rename", file_id="f1", name="a:b")

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT.value
        assert ONEDRIVE_REFUSED_NAME_CHARACTERS in result["message"]

    def test_the_characters_are_published_to_whoever_writes_the_name(self) -> None:
        assert ONEDRIVE_REFUSED_NAME_CHARACTERS in FILE_NAME_DESCRIPTION

    async def test_an_item_gone_is_said_as_the_provider_answered(self) -> None:
        gone = ConnectorAPIError(connector_type="google_drive", status_code=404, detail="gone")
        client = _client(rename_file=AsyncMock(side_effect=gone))

        result = await _run(client, action="rename", file_id="f1", name="x")

        assert "error_code" in result

    def test_a_refusal_is_a_failure(self) -> None:
        refused = ManageFilesTool().format_registry_response(
            {"error_code": "INVALID_INPUT", "message": "no"}
        )

        assert refused.success is False

    def test_an_act_done_is_a_success(self) -> None:
        done = ManageFilesTool().format_registry_response(
            {"action": "move", "item": {"id": "f1"}, "copying": False}
        )

        assert done.success is True
