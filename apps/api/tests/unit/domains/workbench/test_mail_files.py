"""The person's own files, attached to a message they write (ADR-369, Task 4.5).

A selection is attached WHOLE or refused: an id gone since it was offered
refuses the message (``item_gone``), and so do files whose total passes what
the provider carries (``too_large`` with the bound) — a message leaves whole
or not at all. The listing pages the live files with their exact total. (The
statement itself is proven on PostgreSQL: ``test_attachable_queries_db``.)
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.content_disposition import OPAQUE_MEDIA_TYPE
from src.core.exceptions import BaseAPIException
from src.domains.attachments.models import (
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.workbench import mail_files
from src.domains.workbench.errors import TOO_LARGE
from src.domains.workbench.files_service import DriveDownload

pytestmark = pytest.mark.unit

USER = uuid4()


def _row(tmp_path: Path, name: str, data: bytes = b"%PDF", on_disk: bool = True) -> Any:
    stored = tmp_path / f"{uuid4()}.bin"
    if on_disk:
        stored.write_bytes(data)
    return SimpleNamespace(
        id=uuid4(),
        original_filename=name,
        title=None,
        mime_type="application/pdf",
        file_size=len(data),
        file_path=str(stored),
        origin="upload",
        expires_at=None,
    )


def _session(rows: list[Any], total: int | None = None) -> Any:
    """A session answering the listing's rows, then its count."""
    answers = iter(
        [
            MagicMock(scalars=lambda: MagicMock(all=lambda: rows)),
            MagicMock(scalar_one=lambda: len(rows) if total is None else total),
        ]
    )

    @contextlib.asynccontextmanager
    async def opened() -> AsyncIterator[Any]:
        async def execute(statement: Any) -> Any:
            return next(answers)

        yield SimpleNamespace(execute=execute)

    return patch.object(mail_files, "get_db_context", opened)


class TestAFileOfTheDevice:
    """A message carries anything: the door takes what the chat's would not."""

    PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452")

    def _kept(self, tmp_path: Path, *, create: Any = None) -> Any:
        """The door, on a disk of the test's and a session that files the row."""
        made = create or AsyncMock(
            side_effect=lambda fields: SimpleNamespace(id=uuid4(), title=None, **fields)
        )

        @contextlib.asynccontextmanager
        async def opened() -> AsyncIterator[Any]:
            yield MagicMock()

        return (
            patch.object(mail_files.settings, "attachments_storage_path", str(tmp_path)),
            patch.object(mail_files, "get_db_context", opened),
            patch.object(mail_files, "AttachmentRepository", return_value=MagicMock(create=made)),
            made,
        )

    async def _keep(self, tmp_path: Path, file: mail_files.DeviceFile) -> Any:
        path, session, repository, made = self._kept(tmp_path)
        with path, session, repository:
            kept = await mail_files.keep_device_file(USER, file)
        return kept, made.await_args.args[0]

    async def test_its_bytes_are_kept_where_the_send_reads_them(self, tmp_path: Path) -> None:
        file = mail_files.DeviceFile("notes.txt", "text/plain", b"hello")

        _kept, row = await self._keep(tmp_path, file)

        assert (tmp_path / row["file_path"]).read_bytes() == b"hello"
        assert row["file_path"].startswith(f"{USER}/")
        assert row["file_size"] == 5

    async def test_it_is_the_person_s_upload_under_the_upload_s_deadline(
        self, tmp_path: Path
    ) -> None:
        before = datetime.now(UTC)

        kept, row = await self._keep(
            tmp_path, mail_files.DeviceFile("notes.txt", "text/plain", b"hello")
        )

        assert row["origin"] == AttachmentOrigin.UPLOAD.value
        assert row["status"] == AttachmentStatus.READY
        hours = timedelta(hours=settings.attachments_ttl_hours)
        assert before + hours <= row["expires_at"] <= datetime.now(UTC) + hours
        assert (kept.filename, kept.size, kept.origin) == ("notes.txt", 5, "upload")

    async def test_its_bytes_speak_before_what_the_form_declares(self, tmp_path: Path) -> None:
        kept, row = await self._keep(
            tmp_path, mail_files.DeviceFile("a.txt", "text/plain", self.PNG)
        )

        assert kept.mime_type == "image/png"
        assert row["content_type"] == AttachmentContentType.IMAGE

    async def test_a_type_nobody_can_read_is_declared_opaque(self, tmp_path: Path) -> None:
        kept, row = await self._keep(
            tmp_path, mail_files.DeviceFile("a.bin", "not a type\r\nX: 1", b"\x00\x01")
        )

        assert kept.mime_type == OPAQUE_MEDIA_TYPE
        assert row["content_type"] == AttachmentContentType.DOCUMENT

    @pytest.mark.parametrize(
        ("sent", "kept_as"),
        [
            ("C:\\Users\\Ana\\rapport.pdf", "rapport.pdf"),
            ("../../etc/passwd", "passwd"),
            ("  note.txt  ", "note.txt"),
            ("", mail_files.UNNAMED_FILE),
            ("a\r\nX-Evil: 1.txt", "aX-Evil: 1.txt"),
        ],
    )
    async def test_it_keeps_a_file_s_name_and_never_a_path(
        self, tmp_path: Path, sent: str, kept_as: str
    ) -> None:
        kept, _row = await self._keep(tmp_path, mail_files.DeviceFile(sent, "text/plain", b"x"))

        assert kept.filename == kept_as

    async def test_a_name_past_what_can_be_kept_is_refused(self, tmp_path: Path) -> None:
        file = mail_files.DeviceFile("a" * 256, "text/plain", b"x")

        with pytest.raises(BaseAPIException) as refused:
            await mail_files.keep_device_file(USER, file)

        assert "invalid_request" in str(refused.value.detail)

    async def test_a_row_that_could_not_be_filed_leaves_nothing_on_the_disk(
        self, tmp_path: Path
    ) -> None:
        path, session, repository, _made = self._kept(
            tmp_path, create=AsyncMock(side_effect=RuntimeError("down"))
        )
        with path, session, repository, pytest.raises(RuntimeError):
            await mail_files.keep_device_file(
                USER, mail_files.DeviceFile("a.txt", "text/plain", b"x")
            )

        assert [item for item in tmp_path.rglob("*") if item.is_file()] == []


class TestDriveFiles:
    @staticmethod
    def _download(*sizes: int) -> AsyncMock:
        return AsyncMock(
            side_effect=[
                DriveDownload(data=b"x" * size, filename=f"f{size}", mime_type="text/plain")
                for size in sizes
            ]
        )

    async def test_each_is_read_whole_in_the_selection_s_order(self) -> None:
        with patch.object(mail_files.files_service, "download_file", self._download(2, 3)) as read:
            files = await mail_files.drive_files(USER, ["a", "b", "a"], max_bytes=10)

        assert [(file.filename, len(file.data)) for file in files] == [("f2", 2), ("f3", 3)]
        assert [call.args[1].id for call in read.await_args_list] == ["a", "b"]

    async def test_it_stops_reading_at_what_the_provider_carries(self) -> None:
        read = self._download(6, 6, 6)

        with patch.object(mail_files.files_service, "download_file", read):
            with pytest.raises(BaseAPIException) as caught:
                await mail_files.drive_files(USER, ["a", "b", "c"], max_bytes=10)

        assert caught.value.detail == {"code": TOO_LARGE, "max_bytes": 10}
        assert read.await_count == 2


class TestAttaching:
    async def test_a_selection_is_read_whole_in_its_order(self, tmp_path: Path) -> None:
        first, second = _row(tmp_path, "a.pdf", b"AAA"), _row(tmp_path, "b.pdf", b"BB")
        with _session([second, first]):
            files = await mail_files.outgoing_files(
                USER, [first.id, second.id, first.id], max_bytes=100
            )

        assert [(f.filename, f.data) for f in files] == [("a.pdf", b"AAA"), ("b.pdf", b"BB")]

    async def test_an_id_gone_since_it_was_offered_refuses_the_message(
        self, tmp_path: Path
    ) -> None:
        kept = _row(tmp_path, "a.pdf")
        with _session([kept]), pytest.raises(BaseAPIException) as refused:
            await mail_files.outgoing_files(USER, [kept.id, uuid4()], max_bytes=100)

        assert refused.value.detail == {"code": "item_gone"}

    async def test_files_beyond_what_the_provider_carries_are_refused_with_it(
        self, tmp_path: Path
    ) -> None:
        rows = [_row(tmp_path, "a.pdf", b"x" * 60), _row(tmp_path, "b.pdf", b"y" * 60)]
        with _session(rows), pytest.raises(BaseAPIException) as refused:
            await mail_files.outgoing_files(USER, [row.id for row in rows], max_bytes=100)

        assert refused.value.detail == {"code": "too_large", "max_bytes": 100}

    async def test_a_file_the_cleanup_removed_meanwhile_is_gone(self, tmp_path: Path) -> None:
        swept = _row(tmp_path, "a.pdf", on_disk=False)
        with _session([swept]), pytest.raises(BaseAPIException) as refused:
            await mail_files.outgoing_files(USER, [swept.id], max_bytes=100)

        assert refused.value.detail == {"code": "item_gone"}

    async def test_nothing_to_attach_reads_nothing(self) -> None:
        assert await mail_files.outgoing_files(USER, [], max_bytes=100) == ()


class TestTheListing:
    async def test_a_page_and_its_exact_total(self, tmp_path: Path) -> None:
        rows = [_row(tmp_path, "a.pdf"), _row(tmp_path, "b.pdf")]
        with _session(rows, total=5):
            page = await mail_files.list_attachable(USER, query="rap", offset=0)

        assert [item.filename for item in page.items] == ["a.pdf", "b.pdf"]
        assert (page.total, page.next_offset) == (5, 2)

    async def test_the_last_page_says_there_is_no_next(self, tmp_path: Path) -> None:
        with _session([_row(tmp_path, "a.pdf")], total=3):
            page = await mail_files.list_attachable(USER, query=None, offset=2)

        assert page.next_offset is None
