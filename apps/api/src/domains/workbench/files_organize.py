"""Organising a drive by the person's own hand (ADR-369, lot 6).

A new folder, a file sent, a rename, a move, a copy, on Google Drive and OneDrive alike. What
adds an item runs once per submission (a second press creates nothing), a move answers each file
(``selection_acts``), and a copy that Graph finishes after answering is said as under way:
nothing waits for it, and the page reads the folder again.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from src.core.config import settings
from src.core.content_disposition import served_media_type
from src.domains.connectors.clients.protocols import FilesClientProtocol, FileViewsProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NAME_REFUSED, TOO_LARGE, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.files_service import drive_item, require_file_views
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.mail_attachments import download_attachment
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.files import (
    DriveItem,
    FileCopied,
    FileCopy,
    FileFromMail,
    FileMove,
    FileName,
    FileRename,
    FileSelection,
    FileStar,
    NewFolder,
)
from src.domains.workbench.schemas.mail import AttachmentRequest
from src.domains.workbench.selection_acts import act_outcome, settle_each

_TOOL = WorkbenchTool.FILES
#: The top of the drive, as both clients name it.
_ROOT: Final = "root"
_FILE_NAME: Final = TypeAdapter(FileName)


@dataclass(frozen=True)
class DriveUpload:
    """A file going to a drive, under one submission."""

    name: str
    data: bytes
    mime_type: str
    folder_id: str | None
    key: UUID


async def upload_file(user_id: UUID, upload: DriveUpload) -> DriveItem:
    """Send a file to a folder, once per submission.

    Args:
        user_id: The account.
        upload: The file, where it goes and the submission's key.

    Returns:
        The file.
    """

    async def send() -> DriveItem:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: FilesClientProtocol = opened.client
            async with provider_call(_TOOL, "upload", act=True):
                raw = await client.upload_file(
                    upload.name, upload.data, upload.mime_type, upload.folder_id or _ROOT
                )
        return drive_item(raw)

    return await run_once(
        user_id, upload.key, send, tool=_TOOL.value, record=lambda made: {"file_id": made.id}
    )


async def save_mail_attachment(user_id: UUID, request: FileFromMail) -> DriveItem:
    """Send a mail's attachment to a folder, once per submission.

    Its name is the sender's: one no drive takes is refused, never rewritten.

    Args:
        user_id: The account.
        request: The attachment, and where it goes.

    Returns:
        The file.
    """
    content = await download_attachment(
        user_id,
        AttachmentRequest(
            message_id=request.message_id,
            attachment_id=request.attachment_id,
            filename=request.filename,
        ),
    )
    ceiling = settings.workbench_upload_max_bytes
    if len(content.data) > ceiling:
        refuse(TOO_LARGE, max_bytes=ceiling)
    try:
        name = _FILE_NAME.validate_python(content.filename)
    except ValidationError:
        refuse(NAME_REFUSED)
    return await upload_file(
        user_id,
        DriveUpload(
            name=name,
            data=content.data,
            mime_type=served_media_type(content.mime_type),
            folder_id=request.folder_id,
            key=request.idempotency_key,
        ),
    )


async def create_folder(user_id: UUID, request: NewFolder) -> DriveItem:
    """Create a folder, once per submission.

    Args:
        user_id: The account.
        request: Its name, its parent and the submission's key.

    Returns:
        The folder.
    """

    async def create() -> DriveItem:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: FilesClientProtocol = opened.client
            async with provider_call(_TOOL, "create_folder", act=True):
                raw = await client.create_folder(request.name, request.folder_id or _ROOT)
        return drive_item(raw)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"file_id": made.id},
    )


async def star_file(user_id: UUID, request: FileStar) -> DriveItem:
    """Star an item, or take its star back, on a drive that keeps stars.

    Args:
        user_id: The account.
        request: The item and its star.

    Returns:
        The item.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        require_file_views(opened)
        client: FileViewsProtocol = opened.client
        async with provider_call(_TOOL, "star", act=True):
            raw = await client.set_starred(request.file_id, request.starred)
    return drive_item(raw)


async def restore_files(user_id: UUID, selection: FileSelection) -> ActOutcome:
    """Take a selection out of the trash; each file answered.

    Args:
        user_id: The account.
        selection: The files.

    Returns:
        What came back, and why the others did not.
    """
    ids = list(dict.fromkeys(selection.file_ids))
    async with open_tool_client(_TOOL, user_id) as opened:
        client: FilesClientProtocol = opened.client
        async with provider_call(_TOOL, "restore", act=False):
            settled = await settle_each(ids, client.restore_file)
            return act_outcome(ids, settled, tool=_TOOL.value)


async def delete_files(user_id: UUID, selection: FileSelection) -> ActOutcome:
    """Delete a selection for good, by the person's own hand (owner decision A2).

    Args:
        user_id: The account.
        selection: The files.

    Returns:
        What went, and why the others did not.
    """
    ids = list(dict.fromkeys(selection.file_ids))
    async with open_tool_client(_TOOL, user_id) as opened:
        require_file_views(opened)
        client: FileViewsProtocol = opened.client
        async with provider_call(_TOOL, "delete_forever", act=False):
            settled = await settle_each(ids, client.delete_file_forever)
            return act_outcome(ids, settled, tool=_TOOL.value)


async def empty_trash(user_id: UUID) -> None:
    """Delete for good all that the trash holds, by the person's own hand (A2).

    Args:
        user_id: The account.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        require_file_views(opened)
        client: FileViewsProtocol = opened.client
        async with provider_call(_TOOL, "empty_trash", act=True):
            await client.empty_trash()


async def rename_file(user_id: UUID, request: FileRename) -> DriveItem:
    """Give an item another name.

    Args:
        user_id: The account.
        request: The item and its new name.

    Returns:
        The item.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        client: FilesClientProtocol = opened.client
        async with provider_call(_TOOL, "rename", act=True):
            raw = await client.rename_file(request.file_id, request.name)
    return drive_item(raw)


async def move_files(user_id: UUID, request: FileMove) -> ActOutcome:
    """Move a selection to a folder; each file answered.

    Args:
        user_id: The account.
        request: The files, and the folder they go to.

    Returns:
        What was moved, and why the others were not.
    """
    ids = list(dict.fromkeys(request.file_ids))
    target = request.folder_id or _ROOT
    async with open_tool_client(_TOOL, user_id) as opened:
        client: FilesClientProtocol = opened.client
        async with provider_call(_TOOL, "move", act=False):
            settled = await settle_each(ids, lambda file_id: client.move_file(file_id, target))
            return act_outcome(ids, settled, tool=_TOOL.value)


async def copy_file(user_id: UUID, request: FileCopy) -> FileCopied:
    """Copy a file, once per submission; a copy the provider finishes later answers no item.

    Args:
        user_id: The account.
        request: The file, the folder it goes to and the submission's key.

    Returns:
        The copy, or None in it while the provider works.
    """

    async def copy() -> FileCopied:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: FilesClientProtocol = opened.client
            async with provider_call(_TOOL, "copy", act=True):
                raw = await client.copy_file(request.file_id, request.folder_id, request.name)
        return FileCopied(item=drive_item(raw) if raw is not None else None)

    return await run_once(
        user_id,
        request.idempotency_key,
        copy,
        tool=_TOOL.value,
        record=lambda made: {"file_id": made.item.id} if made.item else {},
    )


__all__ = [
    "DriveUpload",
    "copy_file",
    "create_folder",
    "delete_files",
    "empty_trash",
    "move_files",
    "rename_file",
    "restore_files",
    "save_mail_attachment",
    "star_file",
    "upload_file",
]
