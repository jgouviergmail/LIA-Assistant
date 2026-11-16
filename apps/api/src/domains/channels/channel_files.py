"""Files on a channel, both ways (Telegram lot 11).

RECEIVED — a photo or a document the person sends goes through the chat's own
door (``AttachmentService.upload``): what the file IS decided from its bytes,
the instance's limits, the conversation's source. Under the ATTACHMENTS switch,
read at the act (ADR-280), and all or nothing: a message whose files cannot all
be received keeps none of them and says why (:class:`FileRefusal`).

MADE — an image or a document LIA made in a turn (the cards of its answer) is
sent where the person reads, from its own row: the person's, ready, within
Telegram's ceilings; a file Telegram cannot carry is named instead.

ADR-304: a session is open only around its queries, never around a download
from Telegram or a send to it.
"""

from __future__ import annotations

import asyncio
import html
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path, PurePath
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import UploadFile

from src.core._exceptions_base import BaseAPIException
from src.core.config import settings
from src.core.constants import (
    ATTACHMENTS_FILENAME_MAX_CHARS,
    TELEGRAM_DOCUMENT_UPLOAD_MAX_BYTES,
    TELEGRAM_FILE_DOWNLOAD_MAX_BYTES,
)
from src.core.conversation_selection import ConversationSelection
from src.domains.attachments.repository import AttachmentRepository
from src.domains.attachments.service import AttachmentService
from src.domains.attachments.urls import attachment_id_from_url
from src.domains.channels.abstractions import (
    ChannelFile,
    ChannelFileKind,
    ChannelOutboundMessage,
)
from src.domains.document_generation.document_store import GENERATED_DOCUMENTS_METADATA_KEY
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.image_generation.image_store import GENERATED_IMAGES_METADATA_KEY
from src.domains.shared.markdown_literal import markdown_literal
from src.domains.users.conversation_authority import resolve_conversation_source
from src.infrastructure.channels.telegram.bot import get_bot
from src.infrastructure.channels.telegram.files import download_file
from src.infrastructure.channels.telegram.formatter import get_bot_message
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.channels.abstractions import BaseChannelSender

logger = get_logger(__name__)

#: What a file the channel names nothing is called when stored.
_UNNAMED = {ChannelFileKind.PHOTO: "photo.jpg", ChannelFileKind.DOCUMENT: "document"}
#: The cards an answer carries its files in, in the order the chat draws them.
_MADE_FILE_CARDS = (GENERATED_IMAGES_METADATA_KEY, GENERATED_DOCUMENTS_METADATA_KEY)
#: What the chat's door answers for a file it refuses: too large, of a refused type.
_PAYLOAD_TOO_LARGE = 413
_UNSUPPORTED_MEDIA_TYPE = 415


class FileRefusal(StrEnum):
    """Why the files of a message were not received; the values key the bot's answers."""

    UNAVAILABLE = "unavailable"  # The instance takes no file (switched off).
    TOO_MANY = "too_many"  # More than one message carries.
    TOO_LARGE = "too_large"  # Past Telegram's or the instance's ceiling.
    REFUSED_TYPE = "refused_type"  # A type the instance does not read.
    UNREADABLE = "unreadable"  # Telegram did not hand it over.


class _Refused(Exception):
    def __init__(self, reason: FileRefusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


async def receive_files(
    files: Sequence[ChannelFile], *, user_id: UUID
) -> tuple[UUID, ...] | FileRefusal:
    """Store the files a message carries, as the chat stores an upload.

    Args:
        files: The message's files, in order.
        user_id: The person they are stored for.

    Returns:
        The stored attachments' ids, in the files' order; the refusal when
        they cannot all be received (none is then kept).

    Raises:
        Exception: A failure that is no refusal (none of the files is kept).
    """
    if not settings.attachments_enabled or not await is_capability_enabled(
        PlatformCapability.ATTACHMENTS
    ):
        return FileRefusal.UNAVAILABLE
    if len(files) > settings.attachments_max_per_message:
        return FileRefusal.TOO_MANY
    if any((file.size_bytes or 0) > TELEGRAM_FILE_DOWNLOAD_MAX_BYTES for file in files):
        return FileRefusal.TOO_LARGE
    bot = get_bot()
    if bot is None:
        return FileRefusal.UNREADABLE
    stored: list[UUID] = []
    try:
        for file in files:
            content = await download_file(
                bot, file.file_id, max_bytes=TELEGRAM_FILE_DOWNLOAD_MAX_BYTES
            )
            if content is None:
                raise _Refused(FileRefusal.UNREADABLE)
            stored.append(await _store(user_id, file, content))
    except _Refused as refused:
        await forget_files(stored, user_id=user_id)
        logger.info("channel_files_refused", user_id=str(user_id), reason=refused.reason.value)
        return refused.reason
    except Exception:
        await forget_files(stored, user_id=user_id)
        raise
    logger.info("channel_files_received", user_id=str(user_id), files=len(stored))
    return tuple(stored)


async def _store(user_id: UUID, file: ChannelFile, content: bytes) -> UUID:
    """One file, through the chat's upload door, for the person's Main discussion."""
    upload = UploadFile(BytesIO(content), filename=_storable_name(file))
    async with get_db_context() as db:
        target = await resolve_conversation_source(db, user_id, ConversationSelection())
        try:
            attachment = await AttachmentService(db).upload(user_id, upload, target=target)
        except BaseAPIException as refused:
            if refused.status_code == _PAYLOAD_TOO_LARGE:
                raise _Refused(FileRefusal.TOO_LARGE) from refused
            if refused.status_code == _UNSUPPORTED_MEDIA_TYPE:
                raise _Refused(FileRefusal.REFUSED_TYPE) from refused
            raise
    return attachment.id


def _storable_name(file: ChannelFile) -> str:
    """The file's name as the upload door accepts it: no NUL, cut keeping its extension."""
    name = (file.filename or _UNNAMED[file.kind]).replace("\x00", "")
    if len(name) <= ATTACHMENTS_FILENAME_MAX_CHARS:
        return name
    extension = PurePath(name).suffix
    if len(extension) >= ATTACHMENTS_FILENAME_MAX_CHARS:
        extension = ""
    return name[: ATTACHMENTS_FILENAME_MAX_CHARS - len(extension)] + extension


async def forget_files(attachment_ids: Sequence[UUID], *, user_id: UUID) -> None:
    """Delete files received for a message that will not run; best effort.

    A file left behind is retired by its deadline (``attachments_ttl_hours``).

    Args:
        attachment_ids: The files stored for the message.
        user_id: Their owner.
    """
    for attachment_id in attachment_ids:
        try:
            async with get_db_context() as db:
                await AttachmentService(db).delete_for_user_single(attachment_id, user_id)
        except Exception as exc:  # noqa: BLE001 — its deadline retires it anyway
            logger.warning(
                "channel_file_unforgotten",
                attachment_id=str(attachment_id),
                error_type=type(exc).__name__,
            )


def file_words(files: Sequence[ChannelFile]) -> str:
    """The words of a message that sent files and said nothing: their names.

    Args:
        files: The message's files.

    Returns:
        « 📎 » and the names, rendering as themselves in the app.
    """
    names = (markdown_literal(file.filename or _UNNAMED[file.kind]) for file in files)
    return f"📎 {', '.join(names)}"


def generated_files_of(metadata: Mapping[str, object]) -> tuple[UUID, ...]:
    """The stored files an answer's cards show, once each, in the chat's order.

    Args:
        metadata: The turn's last chunk's metadata.

    Returns:
        The attachment ids of the images, then the documents, the turn made.
    """
    found: dict[UUID, None] = {}
    for family in _MADE_FILE_CARDS:
        cards = metadata.get(family)
        for card in cards if isinstance(cards, list) else ():
            url = card.get("url") if isinstance(card, Mapping) else None
            attachment_id = attachment_id_from_url(url) if isinstance(url, str) else None
            if attachment_id is not None:
                found[attachment_id] = None
    return tuple(found)


@dataclass(frozen=True, slots=True)
class _MadeFile:
    path: Path
    filename: str
    mime_type: str
    size: int


async def send_generated_files(
    sender: BaseChannelSender,
    channel_user_id: str,
    *,
    user_id: UUID,
    attachment_ids: Sequence[UUID],
    language: str,
) -> None:
    """Send the person the files a turn made, each from its own row.

    Only the person's ready files are sent; one past Telegram's ceiling is
    named instead; one gone from disk is skipped. Nothing raises: the answer
    already left.

    Args:
        sender: The channel's sender.
        channel_user_id: The person's chat.
        user_id: The person.
        attachment_ids: The files the turn's cards show.
        language: The person's language.
    """
    if not attachment_ids:
        return
    try:
        made = await _made_files(attachment_ids, user_id)
    except Exception:
        logger.error("channel_made_files_unread", user_id=str(user_id), exc_info=True)
        return
    for file in made:
        await _send_one(sender, channel_user_id, file, language=language, user_id=user_id)


async def _made_files(attachment_ids: Sequence[UUID], user_id: UUID) -> list[_MadeFile]:
    """The rows of the person's ready files, in the cards' order (one short session)."""
    async with get_db_context() as db:
        rows = await AttachmentRepository(db).get_batch_for_user(list(attachment_ids), user_id)
    by_id = {row.id: row for row in rows}
    root = Path(settings.attachments_storage_path)
    return [
        _MadeFile(root / row.file_path, row.original_filename, row.mime_type, row.file_size)
        for attachment_id in attachment_ids
        if (row := by_id.get(attachment_id)) is not None
    ]


async def _send_one(
    sender: BaseChannelSender, chat: str, file: _MadeFile, *, language: str, user_id: UUID
) -> None:
    if file.size > TELEGRAM_DOCUMENT_UPLOAD_MAX_BYTES:
        notice = get_bot_message("file_too_large_to_send", language).format(
            name=html.escape(file.filename)
        )
        await sender.send_message(chat, ChannelOutboundMessage(text=notice))
        return
    try:
        content = await asyncio.to_thread(file.path.read_bytes)
    except OSError as exc:
        logger.warning(
            "channel_made_file_missing", user_id=str(user_id), error_type=type(exc).__name__
        )
        return
    sent = await sender.send_file(chat, content, filename=file.filename, mime_type=file.mime_type)
    logger.info("channel_made_file_sent", user_id=str(user_id), sent=sent, size_bytes=len(content))
