"""Integration: files received on a channel go through the chat's door (Telegram lot 11).

The unit tests substitute the upload door; this one runs it on real PostgreSQL
and a real disk: a photo and a document are stored as the chat stores them (type
from the bytes, ready, the person's), and a message whose second file is refused
keeps nothing of the first.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.attachments.models import Attachment, AttachmentStatus
from src.domains.channels import channel_files
from src.domains.channels.abstractions import ChannelFile, ChannelFileKind
from src.domains.channels.channel_files import FileRefusal, receive_files
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration

_PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic fixture bytes"
_TEXT = b"Meeting notes\nTwo decisions were taken.\n"
_BINARY = b"MZ\x90\x00\x03" + bytes(range(256)) * 4


@pytest.fixture
def channel_doors(
    async_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, bytes]:
    """The real upload door on the test database; Telegram's download substituted."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    served: dict[str, bytes] = {}

    async def download(_bot: object, file_id: str, *, max_bytes: int) -> bytes:
        return served[file_id]

    monkeypatch.setattr(channel_files, "get_db_context", session)
    monkeypatch.setattr(channel_files, "download_file", download)
    monkeypatch.setattr(channel_files, "get_bot", lambda: MagicMock())
    monkeypatch.setattr(channel_files, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(settings, "attachments_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    return served


async def _rows(engine: AsyncEngine, owner_id: UUID) -> list[Attachment]:
    async with AsyncSession(engine) as observer:
        return list(
            await observer.scalars(
                select(Attachment).where(Attachment.user_id == owner_id).order_by(Attachment.id)
            )
        )


async def test_a_photo_and_a_document_are_stored_as_the_chat_stores_them(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    channel_doors: dict[str, bytes],
    tmp_path: Path,
) -> None:
    owner_id = await commit_owner(async_engine, committed_user_ids)
    channel_doors.update({"photo": _PNG, "notes": _TEXT})

    received = await receive_files(
        (
            ChannelFile("photo", ChannelFileKind.PHOTO, "photo.jpg", "image/jpeg"),
            ChannelFile("notes", ChannelFileKind.DOCUMENT, "notes.txt", "text/plain"),
        ),
        user_id=owner_id,
    )

    assert isinstance(received, tuple) and len(received) == 2
    rows = {row.id: row for row in await _rows(async_engine, owner_id)}
    photo, notes = (rows[attachment_id] for attachment_id in received)
    # What the file IS comes from its bytes: Telegram's « photo.jpg » was a PNG.
    assert (photo.mime_type, photo.status) == ("image/png", AttachmentStatus.READY)
    assert (notes.original_filename, notes.status) == ("notes.txt", AttachmentStatus.READY)
    assert (tmp_path / photo.file_path).read_bytes() == _PNG


async def test_a_message_whose_second_file_is_refused_keeps_nothing(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    channel_doors: dict[str, bytes],
    tmp_path: Path,
) -> None:
    owner_id = await commit_owner(async_engine, committed_user_ids)
    channel_doors.update({"photo": _PNG, "tool": _BINARY})

    refusal = await receive_files(
        (
            ChannelFile("photo", ChannelFileKind.PHOTO, "photo.jpg"),
            ChannelFile("tool", ChannelFileKind.DOCUMENT, "tool.exe"),
        ),
        user_id=owner_id,
    )

    assert refusal is FileRefusal.REFUSED_TYPE
    # The photo stored first is deleted with its file; the refused one never was stored.
    assert await _rows(async_engine, owner_id) == []
    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []
