"""The assistant organises the person's files, on any drive (ADR-369, lot 6, D2).

What the clients gained for the « Tools » section reaches the assistant in the same lot: one
neutral tool, the active provider resolved by category. It asks no card: each act is undone
by one more call (REASON_UNDONE_BY_ONE_CALL). A copy OneDrive finishes after answering is
said as under way, never as done. A file sent to the drive is one LIA holds under a name the
model can read: the attachment hint and the generated-files lookup both show it, and the id
is never theirs to carry. Its read ends with its session, before anything leaves.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.constants import ONEDRIVE_REFUSED_NAME_CHARACTERS
from src.core.exceptions import ConnectorAPIError
from src.domains.agents.constants import AGENT_FILE, CONTEXT_DOMAIN_FILES
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.drive.organize_manifest import (
    FILE_ACTION_DESCRIPTION,
    FILE_ACTIONS,
    FILE_FOLDER_DESCRIPTION,
    FILE_ID_DESCRIPTION,
    FILE_NAME_DESCRIPTION,
    FILE_SOURCE_DESCRIPTION,
)
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.attachments.repository import AttachmentRepository
from src.domains.connectors.clients.files_management import (
    FileNameRefusedError,
    FileNameTakenError,
)
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.protocols import FilesClientProtocol
from src.domains.connectors.models import ConnectorType
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

_ROOT = "root"
_HTTP_NOT_FOUND = 404
_NEEDS_A_FILE = ("rename", "move", "copy", "restore")
_NEEDS_A_NAME = ("create_folder", "rename")
_UPLOAD = "upload"


@dataclass(frozen=True)
class StoredFile:
    """A file LIA holds, as far as a read needs it."""

    name: str
    relative_path: str
    mime_type: str
    size: int


@dataclass(frozen=True)
class _FilesRequest:
    """What the model asked, its words trimmed."""

    action: str
    file_id: str
    folder_id: str | None
    name: str | None
    source: str


class FileNotHeldError(Exception):
    """No readable file answers to that name."""


class FileTooLargeError(Exception):
    """The file passes the published ceiling."""


#: What the model is told in words: the rest is the tool's failure.
_SAID = (FileNotHeldError, FileTooLargeError, FileNameTakenError, FileNameRefusedError)


class ManageFilesTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """Create a folder, rename, move or copy an item of the active drive."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    functional_category = "files"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialise the tool."""
        super().__init__(tool_name="manage_files_tool", operation="manage")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Do one act on the drive."""
        request = _request_of(kwargs)
        action = request.action
        problem = _request_problem(request)
        if problem:
            return refusal(ToolErrorCode.INVALID_INPUT, problem)
        try:
            if action == _UPLOAD:
                item = await _upload(client, user_id, request)
            else:
                item = await _act(client, request)
        except _SAID as error:
            return _said(error)
        except ConnectorAPIError as error:
            if error.upstream_status_code == _HTTP_NOT_FOUND:
                return refusal(ToolErrorCode.NOT_FOUND, "That item is not on the drive any more.")
            raise
        logger.info("files_managed", user_id=str(user_id), action=action)
        return {"action": action, "item": item, "copying": action == "copy" and item is None}

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """What was done; a refusal is said."""
        if "error_code" in result:
            return UnifiedToolOutput.failure(
                message=str(result["message"]), error_code=str(result["error_code"])
            )
        said = "under way" if result["copying"] else "done"
        output = UnifiedToolOutput.action_success(
            message=f"[file] {result['action']}: {said}", structured_data=result
        )
        output.context_save_mode = ContextSaveMode.NONE
        return output


async def _stored_file(user_id: UUID, file_name: str) -> StoredFile | None:
    """The file a name designates; its session ends here, before anything leaves."""
    async with get_db_context() as db:
        row = await AttachmentRepository(db).newest_by_filename(
            user_id, file_name, datetime.now(UTC)
        )
        if row is None:
            return None
        return StoredFile(
            name=row.original_filename,
            relative_path=row.file_path,
            mime_type=row.mime_type,
            size=row.file_size,
        )


async def _upload(
    client: FilesClientProtocol, user_id: UUID, request: _FilesRequest
) -> dict[str, Any]:
    """Send a file LIA holds to the drive, its size checked before it is read.

    Raises:
        FileNotHeldError: No readable file answers to that name.
        FileTooLargeError: It passes the published ceiling.
    """
    stored = await _stored_file(user_id, request.source)
    if stored is None:
        raise FileNotHeldError
    if stored.size > settings.workbench_upload_max_bytes:
        raise FileTooLargeError
    path = Path(settings.attachments_storage_path) / stored.relative_path
    try:
        data = await asyncio.to_thread(path.read_bytes)
    except FileNotFoundError as gone:
        raise FileNotHeldError from gone
    return await client.upload_file(
        request.name or stored.name, data, stored.mime_type, request.folder_id or _ROOT
    )


async def _act(client: FilesClientProtocol, request: _FilesRequest) -> dict[str, Any] | None:
    """One act, through the clients' one contract."""
    action, file_id, folder_id, name = (
        request.action,
        request.file_id,
        request.folder_id,
        request.name,
    )
    if action == "create_folder":
        return await client.create_folder(str(name), folder_id or _ROOT)
    if action == "rename":
        return await client.rename_file(file_id, str(name))
    if action == "move":
        return await client.move_file(file_id, folder_id or _ROOT)
    if action == "restore":
        return await client.restore_file(file_id)
    return await client.copy_file(file_id, folder_id, name)


def _request_of(arguments: dict[str, Any]) -> _FilesRequest:
    """A request as the model wrote it, its words trimmed."""
    return _FilesRequest(
        action=str(arguments.get("action") or ""),
        file_id=str(arguments.get("file_id") or "").strip(),
        folder_id=str(arguments.get("folder_id") or "").strip() or None,
        name=str(arguments.get("name") or "").strip() or None,
        source=str(arguments.get("file_name") or "").strip(),
    )


def _request_problem(request: _FilesRequest) -> str | None:
    """What a request lacks; None when it can be acted on."""
    action, name = request.action, request.name
    if action not in FILE_ACTIONS:
        return f"action is one of {FILE_ACTIONS}."
    if action in _NEEDS_A_FILE and not request.file_id:
        return "`file_id` is required: name the item."
    if action == _UPLOAD and not request.source:
        return "`file_name` is required: the name of the attached or generated file."
    if action in _NEEDS_A_NAME and not name:
        return "`name` is required."
    if name and ("/" in name or "\\" in name):
        return "A name is one name, never a path."
    return None


def _said(error: Exception) -> dict[str, Any]:
    """What the model is told of a refusal it can act on."""
    if isinstance(error, FileNotHeldError):
        return refusal(
            ToolErrorCode.NOT_FOUND,
            "No attached or generated file has that exact name, or it can no longer be read.",
        )
    if isinstance(error, FileTooLargeError):
        return refusal(
            ToolErrorCode.CONSTRAINT_VIOLATION,
            f"That file is larger than the {settings.workbench_upload_max_bytes} bytes a "
            "drive is sent.",
        )
    if isinstance(error, FileNameTakenError):
        return refusal(
            ToolErrorCode.CONSTRAINT_VIOLATION,
            "An item of this folder already has that name: nothing was changed.",
        )
    return refusal(
        ToolErrorCode.INVALID_INPUT,
        f"The drive refuses these characters in a name: {ONEDRIVE_REFUSED_NAME_CHARACTERS}",
    )


_manage_files_tool_instance = ManageFilesTool()


@connector_tool(
    name="manage_files",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def manage_files_tool(
    action: Annotated[str, FILE_ACTION_DESCRIPTION],
    file_id: Annotated[str | None, FILE_ID_DESCRIPTION] = None,
    folder_id: Annotated[str | None, FILE_FOLDER_DESCRIPTION] = None,
    name: Annotated[str | None, FILE_NAME_DESCRIPTION] = None,
    file_name: Annotated[str | None, FILE_SOURCE_DESCRIPTION] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Organise the person's files, on Google Drive or OneDrive.

    Args:
        action: What to do.
        file_id: The item.
        folder_id: The folder.
        name: The name.
        file_name: The attached or generated file sent to the drive.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput saying what was done.
    """
    return await _manage_files_tool_instance.execute(
        runtime=runtime,
        action=action,
        file_id=file_id,
        folder_id=folder_id,
        name=name,
        file_name=file_name,
    )


__all__ = ["ManageFilesTool", "manage_files_tool"]
