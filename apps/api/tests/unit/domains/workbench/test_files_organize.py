"""Organising a drive in the « Tools » section (ADR-369, lot 6).

A new folder runs once per submission; a move answers each file; a copy Graph finishes after
it answers is said as such; a name taken is said in the page's words, on the provider that
refuses one.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import WORKBENCH_FILE_NAME_MAX_CHARS
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.connectors.clients.files_management import (
    FileNameRefusedError,
    FileNameTakenError,
)
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import files_organize, idempotency
from src.domains.workbench.errors import (
    NAME_REFUSED,
    NAME_TAKEN,
    NOT_SUPPORTED_BY_PROVIDER,
    TOO_LARGE,
)
from src.domains.workbench.schemas.files import (
    FileCopy,
    FileFromMail,
    FileMove,
    FileRename,
    FileSelection,
    FileStar,
    NewFolder,
)
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
KEY = "11111111-1111-4111-8111-111111111111"
ITEM = {"id": "f1", "name": "Notes", "mimeType": "text/plain"}


@pytest.fixture(autouse=True)
def _redis() -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


def _door(client: Any, kind: ConnectorType = ConnectorType.GOOGLE_DRIVE) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        assert user_id == USER
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(files_organize, "open_tool_client", opened)


def _client(**answers: Any) -> MagicMock:
    client = MagicMock(
        create_folder=AsyncMock(return_value=ITEM),
        rename_file=AsyncMock(return_value=ITEM),
        move_file=AsyncMock(return_value=ITEM),
        copy_file=AsyncMock(return_value=ITEM),
    )
    client.configure_mock(**answers)
    return client


class TestANewFolder:
    REQUEST = NewFolder(name="Trips", idempotency_key=KEY)

    async def test_it_is_created_at_the_top_when_nothing_is_named(self) -> None:
        client = _client()

        with _door(client):
            made = await files_organize.create_folder(USER, self.REQUEST)

        client.create_folder.assert_awaited_once_with("Trips", "root")
        assert made.id == "f1"

    async def test_it_goes_in_the_folder_named(self) -> None:
        client = _client()
        request = NewFolder(name="Trips", folder_id="d1", idempotency_key=KEY)

        with _door(client):
            await files_organize.create_folder(USER, request)

        client.create_folder.assert_awaited_once_with("Trips", "d1")

    async def test_a_second_press_creates_nothing(self) -> None:
        client = _client()

        with _door(client):
            await files_organize.create_folder(USER, self.REQUEST)
            with pytest.raises(BaseAPIException):
                await files_organize.create_folder(USER, self.REQUEST)

        client.create_folder.assert_awaited_once()

    async def test_a_name_taken_is_said(self) -> None:
        client = _client(create_folder=AsyncMock(side_effect=FileNameTakenError))

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            with pytest.raises(BaseAPIException) as caught:
                await files_organize.create_folder(USER, self.REQUEST)

        assert caught.value.detail["code"] == NAME_TAKEN

    async def test_a_name_the_drive_refuses_is_said(self) -> None:
        client = _client(create_folder=AsyncMock(side_effect=FileNameRefusedError))

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            with pytest.raises(BaseAPIException) as caught:
                await files_organize.create_folder(USER, self.REQUEST)

        assert caught.value.detail["code"] == NAME_REFUSED

    @pytest.mark.parametrize(
        "name", ["  ", "x" * (WORKBENCH_FILE_NAME_MAX_CHARS + 1), "a/b", "a\\b", "bad\nname"]
    )
    def test_a_name_is_one_name(self, name: str) -> None:
        with pytest.raises(ValidationError):
            NewFolder(name=name, idempotency_key=KEY)


class TestARename:
    async def test_it_reaches_the_client(self) -> None:
        client = _client()

        with _door(client):
            renamed = await files_organize.rename_file(
                USER, FileRename(file_id="f1", name="Notes.txt")
            )

        client.rename_file.assert_awaited_once_with("f1", "Notes.txt")
        assert renamed.id == "f1"


class TestAMove:
    async def test_each_file_is_answered(self) -> None:
        async def move(file_id: str, parent_id: str) -> dict[str, Any]:
            if file_id == "f2":
                raise FileNameTakenError
            return ITEM

        client = _client(move_file=AsyncMock(side_effect=move))

        with _door(client):
            outcome = await files_organize.move_files(
                USER, FileMove(file_ids=["f1", "f2"], folder_id="d1")
            )

        assert outcome.done == ["f1"]
        assert [(item.id, item.status) for item in outcome.failed] == [("f2", "name_taken")]

    async def test_the_same_file_twice_moves_once(self) -> None:
        client = _client()

        with _door(client):
            await files_organize.move_files(USER, FileMove(file_ids=["f1", "f1"], folder_id="d1"))

        client.move_file.assert_awaited_once_with("f1", "d1")

    async def test_nothing_named_is_the_top_of_the_drive(self) -> None:
        client = _client()

        with _door(client):
            await files_organize.move_files(USER, FileMove(file_ids=["f1"]))

        client.move_file.assert_awaited_once_with("f1", "root")

    def test_a_move_is_bounded(self) -> None:
        with pytest.raises(ValidationError):
            FileMove(file_ids=[])
        with pytest.raises(ValidationError):
            FileMove(
                file_ids=[f"f{index}" for index in range(settings.workbench_bulk_max_items + 1)]
            )


class TestAnUpload:
    UPLOAD = files_organize.DriveUpload(
        name="Notes.txt", data=b"data", mime_type="text/plain", folder_id="d1", key=KEY
    )

    async def test_it_reaches_the_client(self) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with _door(client):
            made = await files_organize.upload_file(USER, self.UPLOAD)

        client.upload_file.assert_awaited_once_with("Notes.txt", b"data", "text/plain", "d1")
        assert made.id == "f1"

    async def test_nothing_named_is_the_top_of_the_drive(self) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))
        upload = replace(self.UPLOAD, folder_id=None)

        with _door(client):
            await files_organize.upload_file(USER, upload)

        assert client.upload_file.await_args.args[3] == "root"

    async def test_a_second_press_sends_nothing(self) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with _door(client):
            await files_organize.upload_file(USER, self.UPLOAD)
            with pytest.raises(BaseAPIException):
                await files_organize.upload_file(USER, self.UPLOAD)

        client.upload_file.assert_awaited_once()

    async def test_a_name_taken_is_said_and_frees_the_submission(self) -> None:
        client = _client(upload_file=AsyncMock(side_effect=[FileNameTakenError, ITEM]))

        with _door(client):
            with pytest.raises(BaseAPIException) as caught:
                await files_organize.upload_file(USER, self.UPLOAD)
            await files_organize.upload_file(USER, self.UPLOAD)

        assert caught.value.detail["code"] == NAME_TAKEN


class TestFromAMail:
    REQUEST = FileFromMail(
        message_id="m1",
        attachment_id="a1",
        filename="Invoice.pdf",
        folder_id="d1",
        idempotency_key=KEY,
    )

    @staticmethod
    def _held(size: int = 3, name: str = "Invoice.pdf", mime: str = "application/pdf") -> Any:
        content = EmailAttachmentContent(filename=name, mime_type=mime, data=b"x" * size)
        return patch.object(files_organize, "download_attachment", AsyncMock(return_value=content))

    async def test_it_reaches_the_folder_under_its_own_name(self) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with _door(client), self._held() as read:
            made = await files_organize.save_mail_attachment(USER, self.REQUEST)

        asked = read.await_args.args[1]
        assert (asked.message_id, asked.attachment_id, asked.filename) == (
            "m1",
            "a1",
            "Invoice.pdf",
        )
        client.upload_file.assert_awaited_once_with("Invoice.pdf", b"xxx", "application/pdf", "d1")
        assert made.id == "f1"

    async def test_a_type_nobody_can_serve_is_sent_opaque(self) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with _door(client), self._held(mime="text/html; evil"):
            await files_organize.save_mail_attachment(USER, self.REQUEST)

        assert client.upload_file.await_args.args[2] == "application/octet-stream"

    @pytest.mark.parametrize("name", ["a/b.pdf", "a\\b.pdf", "", "   "])
    async def test_a_name_no_drive_takes_is_refused(self, name: str) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with _door(client), self._held(name=name):
            with pytest.raises(BaseAPIException) as caught:
                await files_organize.save_mail_attachment(USER, self.REQUEST)

        assert caught.value.detail["code"] == NAME_REFUSED
        client.upload_file.assert_not_awaited()

    async def test_past_the_ceiling_it_sends_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "workbench_upload_max_bytes", 2)
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with _door(client), self._held(size=3):
            with pytest.raises(BaseAPIException) as caught:
                await files_organize.save_mail_attachment(USER, self.REQUEST)

        assert caught.value.detail == {"code": TOO_LARGE, "max_bytes": 2}
        client.upload_file.assert_not_awaited()

    async def test_a_second_press_sends_nothing(self) -> None:
        client = _client(upload_file=AsyncMock(return_value=ITEM))

        with _door(client), self._held():
            await files_organize.save_mail_attachment(USER, self.REQUEST)
            with pytest.raises(BaseAPIException):
                await files_organize.save_mail_attachment(USER, self.REQUEST)

        client.upload_file.assert_awaited_once()

    def test_an_attachment_is_named_by_its_handle_or_its_name(self) -> None:
        with pytest.raises(ValidationError):
            FileFromMail(message_id="m1", idempotency_key=KEY)


class TestAStar:
    async def test_it_reaches_the_client(self) -> None:
        client = _client(set_starred=AsyncMock(return_value=ITEM))

        with _door(client):
            item = await files_organize.star_file(USER, FileStar(file_id="f1", starred=True))

        client.set_starred.assert_awaited_once_with("f1", True)
        assert item.id == "f1"

    async def test_a_drive_with_no_stars_asks_nothing(self) -> None:
        client = _client(set_starred=AsyncMock(return_value=ITEM))

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            with pytest.raises(BaseAPIException) as caught:
                await files_organize.star_file(USER, FileStar(file_id="f1", starred=True))

        assert caught.value.detail["code"] == NOT_SUPPORTED_BY_PROVIDER
        client.set_starred.assert_not_awaited()


class TestTheTrash:
    async def test_a_restore_answers_each_file(self) -> None:
        gone = ConnectorAPIError(connector_type="google_drive", status_code=404, detail="x")
        client = _client(restore_file=AsyncMock(side_effect=[ITEM, gone]))

        with _door(client):
            outcome = await files_organize.restore_files(USER, FileSelection(file_ids=["f1", "f2"]))

        assert outcome.done == ["f1"]
        assert [(item.id, item.status) for item in outcome.failed] == [("f2", "not_found")]

    async def test_onedrive_restores_too(self) -> None:
        client = _client(restore_file=AsyncMock(return_value=ITEM))

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            outcome = await files_organize.restore_files(USER, FileSelection(file_ids=["f1"]))

        assert outcome.done == ["f1"]

    async def test_a_file_deleted_for_good_is_answered_too(self) -> None:
        client = _client(delete_file_forever=AsyncMock(return_value=None))

        with _door(client):
            outcome = await files_organize.delete_files(USER, FileSelection(file_ids=["f1"]))

        client.delete_file_forever.assert_awaited_once_with("f1")
        assert outcome.done == ["f1"]

    async def test_the_trash_is_emptied(self) -> None:
        client = _client(empty_trash=AsyncMock(return_value=None))

        with _door(client):
            await files_organize.empty_trash(USER)

        client.empty_trash.assert_awaited_once_with()

    @pytest.mark.parametrize("act", ["delete", "empty"])
    async def test_a_drive_with_no_trash_of_ours_asks_nothing(self, act: str) -> None:
        """OneDrive cannot list its recycle bin: nothing is deleted for good through it."""
        client = _client(delete_file_forever=AsyncMock(), empty_trash=AsyncMock())

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            with pytest.raises(BaseAPIException) as caught:
                if act == "delete":
                    await files_organize.delete_files(USER, FileSelection(file_ids=["f1"]))
                else:
                    await files_organize.empty_trash(USER)

        assert caught.value.detail["code"] == NOT_SUPPORTED_BY_PROVIDER
        client.delete_file_forever.assert_not_awaited()
        client.empty_trash.assert_not_awaited()


class TestACopy:
    async def test_it_answers_the_copy_where_the_provider_has_it(self) -> None:
        client = _client()

        with _door(client):
            done = await files_organize.copy_file(
                USER, FileCopy(file_id="f1", folder_id="d1", idempotency_key=KEY)
            )

        client.copy_file.assert_awaited_once_with("f1", "d1", None)
        assert done.item is not None
        assert done.item.id == "f1"

    async def test_a_second_press_copies_nothing(self) -> None:
        client = _client()
        request = FileCopy(file_id="f1", idempotency_key=KEY)

        with _door(client):
            await files_organize.copy_file(USER, request)
            with pytest.raises(BaseAPIException):
                await files_organize.copy_file(USER, request)

        client.copy_file.assert_awaited_once()

    async def test_a_copy_the_provider_finishes_later_says_it_is_under_way(self) -> None:
        client = _client(copy_file=AsyncMock(return_value=None))

        with _door(client, ConnectorType.MICROSOFT_ONEDRIVE):
            done = await files_organize.copy_file(USER, FileCopy(file_id="f1", idempotency_key=KEY))

        assert done.item is None
