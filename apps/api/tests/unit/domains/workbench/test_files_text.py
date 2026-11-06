"""A text file changed by the person's own hand, on both drives (ADR-369, lot 14).

The read hands the page the version it read; the write is conditioned on it, so an edit made
elsewhere meanwhile is refused with a sentence the page can tell, and the words typed stay on the
screen. Nothing here reaches a model or the registers.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import files_text
from src.domains.workbench.errors import (
    CONFLICT,
    FILE_LOCKED,
    NOT_SUPPORTED_BY_PROVIDER,
    TOO_LARGE,
)
from src.domains.workbench.schemas.files import FileTextChange

pytestmark = pytest.mark.unit

USER = uuid4()


def _door(client: Any, kind: ConnectorType = ConnectorType.MICROSOFT_ONEDRIVE) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        assert user_id == USER
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(files_text, "open_tool_client", opened)


def _client(data: bytes = b"Hello\n", tag: str = "tag-1") -> MagicMock:
    listed = {"id": "f1", "name": "notes.txt", "mimeType": "text/plain", "size": len(data)}
    return MagicMock(
        get_file_metadata=AsyncMock(return_value={**listed, "eTag": tag}),
        get_file_content=AsyncMock(return_value=data),
        replace_content=AsyncMock(return_value={**listed, "eTag": "tag-2"}),
    )


CHANGE = FileTextChange(id="f1", text="Bye\n", tag="tag-1")


async def _refused(call: Any) -> Any:
    with pytest.raises(BaseAPIException) as refused:
        await call
    return refused.value.detail["code"]


class TestTheRead:
    async def test_it_answers_the_words_and_the_version_they_are_at(self) -> None:
        with _door(_client()):
            read = await files_text.read_text(USER, "f1")

        assert (read.text, read.tag) == ("Hello\n", "tag-1")

    async def test_what_cannot_be_edited_here_is_refused(self) -> None:
        client = _client(b"caf\xe9")

        with _door(client):
            assert await _refused(files_text.read_text(USER, "f1")) == NOT_SUPPORTED_BY_PROVIDER


class TestTheWrite:
    async def test_the_words_are_written_on_their_version(self) -> None:
        client = _client()

        with _door(client):
            item = await files_text.write_text(USER, CHANGE)

        client.replace_content.assert_awaited_once_with("f1", b"Bye\n", "text/plain", "tag-1")
        assert item.id == "f1"

    async def test_a_change_made_elsewhere_meanwhile_is_a_conflict(self) -> None:
        with _door(_client(tag="tag-9")):
            assert await _refused(files_text.write_text(USER, CHANGE)) == CONFLICT

    async def test_a_file_someone_holds_is_said_locked(self) -> None:
        from src.domains.connectors.clients.office_files import (
            OfficeContentRefusedError,
            OfficeRefusal,
        )

        client = _client()
        client.replace_content.side_effect = OfficeContentRefusedError(OfficeRefusal.LOCKED)

        with _door(client):
            assert await _refused(files_text.write_text(USER, CHANGE)) == FILE_LOCKED

    async def test_a_text_past_the_bound_is_too_large(self) -> None:
        from src.core.constants import DRIVE_TEXT_MAX_BYTES

        change = FileTextChange(id="f1", text="é" * DRIVE_TEXT_MAX_BYTES, tag="tag-1")

        with _door(_client()):
            assert await _refused(files_text.write_text(USER, change)) == TOO_LARGE


class TestTheRequest:
    @pytest.mark.parametrize("tag", ["", "x" * 600])
    def test_a_version_nobody_read_never_reaches_a_drive(self, tag: str) -> None:
        with pytest.raises(ValueError):
            FileTextChange(id="f1", text="Bye", tag=tag)

    def test_a_field_nobody_declared_is_refused(self) -> None:
        with pytest.raises(ValueError):
            FileTextChange.model_validate({"id": "f1", "text": "a", "tag": "t", "extra": 1})
