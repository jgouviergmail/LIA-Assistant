"""A drive's plain text file, read and written whole (ADR-369, lot 14).

A text is written back on the version it was read at, so a change made elsewhere meanwhile is
refused rather than lost. What the person cannot see in a text box stays as it was: a byte order
mark, Windows line ends. A file whose words cannot be told for sure is refused, never rewritten.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import DRIVE_TEXT_MAX_BYTES
from src.domains.connectors.clients.drive_text import (
    DriveText,
    TextFileDocuments,
    append_to_text_file,
    read_text_file,
    rewrite_text_file,
)
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal

pytestmark = pytest.mark.unit

BOM = b"\xef\xbb\xbf"


def _onedrive(
    data: bytes | None = b"Hello\n",
    *,
    name: str = "notes.txt",
    mime_type: str = "text/plain",
    size: int | None = None,
    tag: str = "tag-1",
) -> MagicMock:
    listed = {
        "id": "f1",
        "name": name,
        "mimeType": mime_type,
        "size": len(data or b"") if size is None else size,
        "eTag": tag,
    }
    return MagicMock(
        get_file_metadata=AsyncMock(return_value=listed),
        get_file_content=AsyncMock(return_value=data),
        replace_content=AsyncMock(return_value={"id": "f1", "eTag": "tag-2"}),
    )


def _google(data: bytes = b"Hello\n", revision: str = "rev-1") -> MagicMock:
    drive = _onedrive(data)
    listed = dict(drive.get_file_metadata.return_value)
    del listed["eTag"]
    drive.get_file_metadata.return_value = {**listed, "headRevisionId": revision}
    return drive


async def _refusal(call: Any) -> OfficeRefusal:
    with pytest.raises(OfficeContentRefusedError) as refused:
        await call
    return refused.value.refusal


class TestReadingIt:
    async def test_it_comes_with_its_name_and_the_version_it_was_read_at(self) -> None:
        assert await read_text_file(_onedrive(), "f1") == DriveText("notes.txt", "Hello\n", "tag-1")

    async def test_a_google_file_is_versioned_by_its_revision(self) -> None:
        assert (await read_text_file(_google(), "f1")).tag == "rev-1"

    async def test_the_revision_is_asked_of_the_drive(self) -> None:
        drive = _google()

        await read_text_file(drive, "f1")

        assert "headRevisionId" in drive.get_file_metadata.await_args.kwargs["fields"]

    async def test_a_file_that_declares_nothing_is_a_text_by_its_name(self) -> None:
        drive = _onedrive(b"# Title", name="notes.md", mime_type="application/octet-stream")

        assert (await read_text_file(drive, "f1")).text == "# Title"

    async def test_windows_line_ends_read_as_a_text_box_would_show_them(self) -> None:
        assert (await read_text_file(_onedrive(b"a\r\nb\r\n"), "f1")).text == "a\nb\n"

    async def test_a_byte_order_mark_is_never_a_character_of_the_text(self) -> None:
        assert (await read_text_file(_onedrive(BOM + b"Hello"), "f1")).text == "Hello"

    @pytest.mark.parametrize(
        ("name", "mime_type"),
        [
            ("report.docx", "application/octet-stream"),
            ("photo.png", "image/png"),
            ("notes.md", "application/vnd.google-apps.document"),
        ],
    )
    async def test_what_is_no_text_is_refused_before_a_byte_is_read(
        self, name: str, mime_type: str
    ) -> None:
        drive = _onedrive(name=name, mime_type=mime_type)

        assert await _refusal(read_text_file(drive, "f1")) is OfficeRefusal.NOT_THIS_FORMAT
        drive.get_file_content.assert_not_awaited()

    async def test_a_file_past_the_bound_is_refused_before_a_byte_is_read(self) -> None:
        drive = _onedrive(size=DRIVE_TEXT_MAX_BYTES + 1)

        assert await _refusal(read_text_file(drive, "f1")) is OfficeRefusal.TOO_LARGE
        drive.get_file_content.assert_not_awaited()

    async def test_a_file_the_client_stopped_at_its_bound_is_too_large(self) -> None:
        assert await _refusal(read_text_file(_onedrive(None), "f1")) is OfficeRefusal.TOO_LARGE

    async def test_bytes_that_are_no_utf8_are_refused_never_guessed(self) -> None:
        assert await _refusal(read_text_file(_onedrive(b"caf\xe9"), "f1")) is (
            OfficeRefusal.UNREADABLE
        )

    async def test_a_file_with_no_version_is_refused(self) -> None:
        drive = _onedrive(tag="")

        assert await _refusal(read_text_file(drive, "f1")) is OfficeRefusal.UNREADABLE


class TestWritingItBack:
    async def test_it_is_written_on_the_version_it_was_read_at(self) -> None:
        drive = _onedrive()

        written = await rewrite_text_file(drive, "f1", "Bye\n", "tag-1")

        drive.replace_content.assert_awaited_once_with("f1", b"Bye\n", "text/plain", "tag-1")
        assert written == {"id": "f1", "eTag": "tag-2"}

    async def test_a_version_that_moved_is_refused_and_nothing_is_written(self) -> None:
        drive = _onedrive(tag="tag-9")

        refusal = await _refusal(rewrite_text_file(drive, "f1", "Bye", "tag-1"))

        assert refusal is OfficeRefusal.CHANGED
        drive.replace_content.assert_not_awaited()

    async def test_a_text_that_did_not_change_writes_nothing(self) -> None:
        drive = _onedrive(b"Hello\r\n")

        answered = await rewrite_text_file(drive, "f1", "Hello\n", "tag-1")

        drive.replace_content.assert_not_awaited()
        assert answered["eTag"] == "tag-1"

    async def test_windows_line_ends_stay_windows_line_ends(self) -> None:
        drive = _onedrive(b"a\r\nb\r\n")

        await rewrite_text_file(drive, "f1", "a\nc\n", "tag-1")

        assert drive.replace_content.await_args.args[1] == b"a\r\nc\r\n"

    async def test_a_file_of_unix_line_ends_keeps_them(self) -> None:
        drive = _onedrive(b"a\nb\n")

        await rewrite_text_file(drive, "f1", "a\r\nc\n", "tag-1")

        assert drive.replace_content.await_args.args[1] == b"a\nc\n"

    async def test_a_byte_order_mark_stays_where_it_was(self) -> None:
        drive = _onedrive(BOM + b"a")

        await rewrite_text_file(drive, "f1", "b", "tag-1")

        assert drive.replace_content.await_args.args[1] == BOM + b"b"

    async def test_a_text_past_the_bound_is_refused(self) -> None:
        drive = _onedrive()

        refusal = await _refusal(
            rewrite_text_file(drive, "f1", "é" * DRIVE_TEXT_MAX_BYTES, "tag-1")
        )

        assert refusal is OfficeRefusal.TOO_LARGE
        drive.replace_content.assert_not_awaited()

    async def test_a_file_that_became_something_else_is_refused(self) -> None:
        drive = _onedrive(b"caf\xe9")

        assert await _refusal(rewrite_text_file(drive, "f1", "cafe", "tag-1")) is (
            OfficeRefusal.UNREADABLE
        )
        drive.replace_content.assert_not_awaited()


class TestTheAssistantsDoor:
    @staticmethod
    def _documents() -> MagicMock:
        return MagicMock(
            read_text=AsyncMock(return_value={"title": "Doc", "content": "Body"}),
            read_title=AsyncMock(return_value="Doc"),
            append_text=AsyncMock(return_value={"done": True}),
        )

    async def test_a_text_is_read_from_the_drive(self) -> None:
        documents = self._documents()

        read = await TextFileDocuments(_onedrive(), documents).read_text("f1")

        assert read == {"title": "notes.txt", "content": "Hello\n"}
        documents.read_text.assert_not_awaited()

    async def test_a_document_stays_with_the_drives_documents(self) -> None:
        documents = self._documents()
        drive = _onedrive(name="report.docx", mime_type="application/octet-stream")

        read = await TextFileDocuments(drive, documents).read_text("f1")

        assert read == {"title": "Doc", "content": "Body"}
        drive.get_file_content.assert_not_awaited()

    async def test_a_text_is_named_by_the_drive(self) -> None:
        documents = self._documents()

        assert await TextFileDocuments(_onedrive(), documents).read_title("f1") == "notes.txt"
        documents.read_title.assert_not_awaited()

    async def test_a_document_is_named_by_the_drives_documents(self) -> None:
        drive = _onedrive(mime_type="application/vnd.google-apps.document", name="Plan")

        assert await TextFileDocuments(drive, self._documents()).read_title("f1") == "Doc"

    async def test_words_added_to_a_text_go_to_the_drive(self) -> None:
        drive = _onedrive(b"Hello\n")
        documents = self._documents()

        await TextFileDocuments(drive, documents).append_text("f1", "Bye")

        assert drive.replace_content.await_args.args[1] == b"Hello\nBye\n"
        documents.append_text.assert_not_awaited()

    async def test_words_added_to_a_document_go_to_the_drives_documents(self) -> None:
        drive = _onedrive(name="report.docx", mime_type="application/octet-stream")
        documents = self._documents()

        await TextFileDocuments(drive, documents).append_text("f1", "Bye")

        documents.append_text.assert_awaited_once_with("f1", "Bye")
        drive.replace_content.assert_not_awaited()

    async def test_a_rewrite_names_the_version_it_read(self) -> None:
        drive = _onedrive()
        door = TextFileDocuments(drive, self._documents())

        read = await door.read_version("f1")
        await door.replace_text("f1", "Bye\n", read.tag)

        drive.replace_content.assert_awaited_once_with("f1", b"Bye\n", "text/plain", "tag-1")

    async def test_a_document_cannot_be_rewritten_whole(self) -> None:
        drive = _onedrive(name="report.docx", mime_type="application/octet-stream")

        refusal = await _refusal(TextFileDocuments(drive, self._documents()).read_version("f1"))

        assert refusal is OfficeRefusal.NOT_THIS_FORMAT


class TestAddingToIt:
    async def test_it_starts_on_a_line_of_its_own(self) -> None:
        drive = _onedrive(b"Hello")

        await append_to_text_file(drive, "f1", "Bye")

        assert drive.replace_content.await_args.args[1] == b"Hello\nBye\n"

    async def test_a_file_ending_its_line_gets_no_empty_one(self) -> None:
        drive = _onedrive(b"Hello\n")

        await append_to_text_file(drive, "f1", "Bye")

        assert drive.replace_content.await_args.args[1] == b"Hello\nBye\n"

    async def test_an_empty_file_starts_with_it(self) -> None:
        drive = _onedrive(b"")

        await append_to_text_file(drive, "f1", "Bye")

        assert drive.replace_content.await_args.args[1] == b"Bye\n"

    async def test_it_is_written_on_the_version_it_read(self) -> None:
        drive = _onedrive(tag="tag-7")

        await append_to_text_file(drive, "f1", "Bye")

        assert drive.replace_content.await_args.args[3] == "tag-7"
