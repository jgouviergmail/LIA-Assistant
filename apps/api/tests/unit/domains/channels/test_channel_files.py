"""Files on a channel, both ways (Telegram lot 11).

A photo or a document sent on Telegram reached nobody, and a file LIA made
(an image, a document) never left the app. Received files go through the
chat's own door (``AttachmentService.upload``: the type decided by the bytes,
the instance's limits, the conversation's source), under the ATTACHMENTS
switch, all or nothing; made files are sent from their own row, the person's
alone.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.core._exceptions_base import BaseAPIException
from src.core.config import settings
from src.core.constants import (
    ATTACHMENTS_FILENAME_MAX_CHARS,
    TELEGRAM_DOCUMENT_UPLOAD_MAX_BYTES,
    TELEGRAM_FILE_DOWNLOAD_MAX_BYTES,
)
from src.domains.attachments.urls import attachment_url
from src.domains.channels import channel_files
from src.domains.channels.abstractions import ChannelFile, ChannelFileKind
from src.domains.channels.channel_files import (
    FileRefusal,
    file_words,
    generated_files_of,
    receive_files,
    send_generated_files,
)
from src.infrastructure.channels.telegram.formatter import get_bot_message

pytestmark = pytest.mark.unit

OWNER = uuid4()
#: The person's language — never the instance's, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)


def _file(
    file_id: str = "f1", name: str | None = "photo.jpg", size: int | None = 10
) -> ChannelFile:
    kind = ChannelFileKind.PHOTO if name == "photo.jpg" else ChannelFileKind.DOCUMENT
    return ChannelFile(file_id, kind, name, None, size)


class _Storage:
    """The chat's upload door, recorded: what it was handed, what it answered."""

    def __init__(self) -> None:
        self.stored: list[tuple[UUID, str, bytes, object]] = []
        self.forgotten: list[UUID] = []
        self.failures: dict[int, BaseException] = {}
        self.target = object()

    def service(self, _db: object) -> Any:
        storage = self

        async def upload(user_id: UUID, file: Any, *, target: object) -> Any:
            if len(storage.stored) in storage.failures:
                raise storage.failures[len(storage.stored)]
            content = await file.read()
            attachment = SimpleNamespace(id=uuid4())
            storage.stored.append((attachment.id, file.filename, content, target))
            assert user_id == OWNER
            return attachment

        async def delete(attachment_id: UUID, user_id: UUID) -> None:
            assert user_id == OWNER
            storage.forgotten.append(attachment_id)

        return SimpleNamespace(upload=upload, delete_for_user_single=delete)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Storage]:
    recorded = _Storage()

    @asynccontextmanager
    async def session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    async def source(_db: object, owner: UUID, _selection: object) -> object:
        assert owner == OWNER
        return recorded.target

    monkeypatch.setattr(channel_files, "get_db_context", session)
    monkeypatch.setattr(channel_files, "AttachmentService", recorded.service)
    monkeypatch.setattr(channel_files, "resolve_conversation_source", source)
    monkeypatch.setattr(settings, "attachments_enabled", True)
    monkeypatch.setattr(channel_files, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(channel_files, "get_bot", lambda: MagicMock())
    yield recorded


@pytest.fixture
def downloads(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    download = AsyncMock(side_effect=lambda _bot, file_id, *, max_bytes: f"<{file_id}>".encode())
    monkeypatch.setattr(channel_files, "download_file", download)
    return download


class TestReceivedFiles:
    async def test_files_are_stored_through_the_chat_s_door_in_order(
        self, storage: _Storage, downloads: AsyncMock
    ) -> None:
        received = await receive_files((_file("a"), _file("b", "report.pdf")), user_id=OWNER)

        assert received == tuple(stored[0] for stored in storage.stored)
        assert [stored[1:] for stored in storage.stored] == [
            ("photo.jpg", b"<a>", storage.target),
            ("report.pdf", b"<b>", storage.target),
        ]
        assert all(
            call.kwargs == {"max_bytes": TELEGRAM_FILE_DOWNLOAD_MAX_BYTES}
            for call in downloads.await_args_list
        )

    async def test_a_document_with_no_name_is_named_by_what_it_is(
        self, storage: _Storage, downloads: AsyncMock
    ) -> None:
        await receive_files((_file("a", None),), user_id=OWNER)

        assert storage.stored[0][1] == "document"

    async def test_an_unstorable_name_is_cut_keeping_its_extension(
        self, storage: _Storage, downloads: AsyncMock
    ) -> None:
        await receive_files((_file("a", "x\x00" + "y" * 400 + ".pdf"),), user_id=OWNER)

        name = storage.stored[0][1]
        assert len(name) == ATTACHMENTS_FILENAME_MAX_CHARS and name.endswith(".pdf")
        assert "\x00" not in name

    async def test_a_switched_off_capability_takes_no_file(
        self, storage: _Storage, downloads: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(channel_files, "is_capability_enabled", AsyncMock(return_value=False))

        assert await receive_files((_file(),), user_id=OWNER) is FileRefusal.UNAVAILABLE
        downloads.assert_not_awaited()

    async def test_an_instance_without_attachments_takes_no_file(
        self, storage: _Storage, downloads: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "attachments_enabled", False)

        assert await receive_files((_file(),), user_id=OWNER) is FileRefusal.UNAVAILABLE
        downloads.assert_not_awaited()

    async def test_more_files_than_a_message_takes_are_refused(
        self, storage: _Storage, downloads: AsyncMock
    ) -> None:
        files = tuple(
            _file(f"f{index}") for index in range(settings.attachments_max_per_message + 1)
        )

        assert await receive_files(files, user_id=OWNER) is FileRefusal.TOO_MANY
        downloads.assert_not_awaited()

    async def test_a_file_past_telegram_s_ceiling_is_refused_before_any_download(
        self, storage: _Storage, downloads: AsyncMock
    ) -> None:
        files = (_file("a"), _file("b", "big.pdf", TELEGRAM_FILE_DOWNLOAD_MAX_BYTES + 1))

        assert await receive_files(files, user_id=OWNER) is FileRefusal.TOO_LARGE
        downloads.assert_not_awaited()

    async def test_a_file_telegram_does_not_give_keeps_nothing(
        self, storage: _Storage, downloads: AsyncMock
    ) -> None:
        downloads.side_effect = [b"first", None]

        refusal = await receive_files((_file("a"), _file("b", "b.pdf")), user_id=OWNER)

        assert refusal is FileRefusal.UNREADABLE
        assert storage.forgotten == [storage.stored[0][0]]

    @pytest.mark.parametrize(
        ("status", "refusal"),
        [(413, FileRefusal.TOO_LARGE), (415, FileRefusal.REFUSED_TYPE)],
        ids=["too_large", "refused_type"],
    )
    async def test_what_the_door_refuses_is_said_and_nothing_is_kept(
        self, status: int, refusal: FileRefusal, storage: _Storage, downloads: AsyncMock
    ) -> None:
        storage.failures[1] = BaseAPIException(status_code=status, detail="refused")

        assert await receive_files((_file("a"), _file("b", "b.pdf")), user_id=OWNER) is refusal
        assert storage.forgotten == [storage.stored[0][0]]

    async def test_any_other_failure_is_raised_and_nothing_is_kept(
        self, storage: _Storage, downloads: AsyncMock
    ) -> None:
        storage.failures[1] = RuntimeError("disk away")

        with pytest.raises(RuntimeError):
            await receive_files((_file("a"), _file("b", "b.pdf")), user_id=OWNER)
        assert storage.forgotten == [storage.stored[0][0]]


def test_files_sent_without_words_are_named() -> None:
    words = file_words((_file("a"), _file("b", "[x](https://e.example).pdf")))

    assert words == "📎 photo.jpg, &#91;x&#93;(https://e.example).pdf"


# --- Files LIA made, sent where the person reads --------------------------------


def test_the_files_a_turn_made_are_read_from_its_cards() -> None:
    image, document = uuid4(), uuid4()
    metadata = {
        "generated_images": [{"url": attachment_url(image)}, {"url": attachment_url(image)}],
        "generated_documents": [
            {"url": attachment_url(document), "filename": "r.pdf"},
            {"url": "https://elsewhere.example/x"},
            {"url": None},
            "not a card",
        ],
    }

    assert generated_files_of(metadata) == (image, document)


def test_a_turn_that_made_nothing_sends_nothing() -> None:
    assert generated_files_of({}) == ()


class _Rows:
    """The person's file rows, as the repository answers them."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.asked: list[tuple[list[UUID], UUID]] = []

    def repository(self, _db: object) -> Any:
        rows = self

        async def batch(ids: list[UUID], user_id: UUID) -> list[Any]:
            rows.asked.append((ids, user_id))
            return [row for row in rows.rows if row.id in ids]

        return SimpleNamespace(get_batch_for_user=batch)


def _row(
    tmp_path: Path, name: str, mime: str, content: bytes | None = b"data", size: int = 4
) -> Any:
    stored = tmp_path / f"{uuid4()}.bin"
    if content is not None:
        stored.write_bytes(content)
    return SimpleNamespace(
        id=uuid4(), file_path=stored.name, original_filename=name, mime_type=mime, file_size=size
    )


@pytest.fixture
def made(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[_Rows, MagicMock]]:
    rows = _Rows([])

    @asynccontextmanager
    async def session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    monkeypatch.setattr(channel_files, "get_db_context", session)
    monkeypatch.setattr(channel_files, "AttachmentRepository", rows.repository)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    sender = MagicMock(
        send_file=AsyncMock(return_value=True), send_message=AsyncMock(return_value="1")
    )
    yield rows, sender


class TestMadeFilesLeave:
    async def test_each_file_is_sent_as_itself_from_its_row(
        self, made: tuple[_Rows, MagicMock], tmp_path: Path
    ) -> None:
        rows, sender = made
        image = _row(tmp_path, "sunset.png", "image/png", b"png!")
        report = _row(tmp_path, "report.pdf", "application/pdf", b"%PDF")
        rows.rows = [image, report]

        await send_generated_files(
            sender, "12345", user_id=OWNER, attachment_ids=(report.id, image.id), language=_PERSON
        )

        assert rows.asked == [([report.id, image.id], OWNER)]
        sent = [
            (call.args, call.kwargs["filename"], call.kwargs["mime_type"])
            for call in sender.send_file.await_args_list
        ]
        assert sent == [
            (("12345", b"%PDF"), "report.pdf", "application/pdf"),
            (("12345", b"png!"), "sunset.png", "image/png"),
        ]

    async def test_a_file_too_large_for_telegram_is_named_not_sent(
        self, made: tuple[_Rows, MagicMock], tmp_path: Path
    ) -> None:
        rows, sender = made
        rows.rows = [
            _row(
                tmp_path,
                "<big>.zip",
                "application/zip",
                size=TELEGRAM_DOCUMENT_UPLOAD_MAX_BYTES + 1,
            )
        ]

        await send_generated_files(
            sender, "12345", user_id=OWNER, attachment_ids=(rows.rows[0].id,), language=_PERSON
        )

        sender.send_file.assert_not_awaited()
        notice = sender.send_message.await_args.args[1].text
        expected = get_bot_message("file_too_large_to_send", _PERSON).format(name="&lt;big&gt;.zip")
        assert notice == expected

    async def test_a_file_gone_from_disk_or_not_the_person_s_is_skipped(
        self, made: tuple[_Rows, MagicMock], tmp_path: Path
    ) -> None:
        rows, sender = made
        gone = _row(tmp_path, "gone.pdf", "application/pdf", content=None)
        kept = _row(tmp_path, "kept.pdf", "application/pdf")
        rows.rows = [gone, kept]

        await send_generated_files(
            sender,
            "12345",
            user_id=OWNER,
            attachment_ids=(uuid4(), gone.id, kept.id),
            language=_PERSON,
        )

        assert [call.kwargs["filename"] for call in sender.send_file.await_args_list] == [
            "kept.pdf"
        ]

    async def test_nothing_made_reads_nothing(self, made: tuple[_Rows, MagicMock]) -> None:
        rows, sender = made

        await send_generated_files(
            sender, "12345", user_id=OWNER, attachment_ids=(), language=_PERSON
        )

        assert rows.asked == []
        sender.send_file.assert_not_awaited()
