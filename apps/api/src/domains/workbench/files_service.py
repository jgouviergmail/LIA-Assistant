"""The Drive files of the « Tools » section, by the person's own hand (ADR-369).

Drive belongs to no category (F1): the door opens its connector by type, no
session held while it answers (ADR-304), under the workbench's failure contract
(``provider_call``). A folder pages by Drive's cursor, and so does a search,
Drive-wide. A file's breadcrumb walks up its first parent to My Drive, one call
per folder under a bounded depth, and says when it stopped or that the file
lives outside My Drive. A Google document downloads EXPORTED, any other file as
its bytes — one download at a time per account, never past the published
ceiling, a listed size refused before the body is read (``drive_formats``). A
link Drive hands back is handed on only when it is Google's own https address.
The trash answers each file (``selection_acts``). Shared drives are not listed:
the client never asks for them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlsplit
from uuid import UUID

from src.core.config import settings
from src.core.constants import (
    WORKBENCH_DRIVE_BREADCRUMB_MAX_DEPTH,
    WORKBENCH_DRIVE_DETAIL_FIELDS,
    WORKBENCH_DRIVE_FIELDS,
)
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.downloads import one_download
from src.domains.workbench.drive_formats import (
    EXPORTS,
    Export,
    ExportFormat,
    formats_of,
    is_downloadable,
    is_google_type,
    kind_of,
)
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, TOO_LARGE, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.files import (
    DownloadQuery,
    DriveItem,
    FileAncestor,
    FileDetail,
    FileSelection,
    FilesPage,
    FilesQuery,
)
from src.domains.workbench.selection_acts import act_outcome, settle_each

_TOOL = WorkbenchTool.FILES
#: Drive's alias of My Drive.
_ROOT: Final = "root"
#: What a breadcrumb reads of each folder it walks.
_TRAIL_FIELDS: Final = ["id", "name", "parents"]
#: What a download reads before it decides how.
_DOWNLOAD_FIELDS: Final = ["id", "name", "mimeType", "size"]
#: The hosts Drive opens a file on.
_DRIVE_HOSTS: Final = frozenset({"docs.google.com", "drive.google.com"})


@dataclass(frozen=True)
class DriveDownload:
    """A file's bytes, its name and its type, as served."""

    data: bytes
    filename: str
    mime_type: str


async def list_files(user_id: UUID, query: FilesQuery) -> FilesPage:
    """One page of a folder (My Drive when none is named), or of a Drive-wide search."""
    size = listing_page_size()
    fields = list(WORKBENCH_DRIVE_FIELDS)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: GoogleDriveClient = opened.client
        async with provider_call(_TOOL, "list", act=False):
            if query.q is not None:
                raw = await client.search_files(
                    query.q,
                    max_results=size,
                    fields=fields,
                    content_type="all",
                    search_mode="full_text" if query.full_text else "name_only",
                    page_token=query.page_token,
                )
            else:
                raw = await client.list_files(
                    folder_id=query.folder_id or _ROOT,
                    max_results=size,
                    page_token=query.page_token,
                    fields=fields,
                    content_type="all",
                )
    return FilesPage(
        items=[_item(raw_file) for raw_file in raw.get("files") or []],
        next_page_token=raw.get("nextPageToken") or None,
    )


async def read_file(user_id: UUID, file_id: str) -> FileDetail:
    """One item, and the folders it lives in up to My Drive."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: GoogleDriveClient = opened.client
        async with provider_call(_TOOL, "read", act=False):
            raw = await client.get_file_metadata(
                file_id, fields=list(WORKBENCH_DRIVE_DETAIL_FIELDS)
            )
            ancestors, in_my_drive, cut = await _trail(client, raw)
    return FileDetail(
        **_item(raw).model_dump(),
        owners=[
            str(owner.get("displayName"))
            for owner in raw.get("owners") or []
            if isinstance(owner, Mapping) and owner.get("displayName")
        ],
        description=raw.get("description") or None,
        created_at=raw.get("createdTime") or None,
        ancestors=ancestors,
        in_my_drive=in_my_drive,
        ancestors_truncated=cut,
    )


async def download_file(user_id: UUID, query: DownloadQuery) -> DriveDownload:
    """A file's bytes — a Google document exported — never past the published ceiling.

    Raises:
        BaseAPIException: ``too_large`` with the ceiling; ``not_supported_by_provider``
            for what the file cannot become (a folder, a form, a format its type
            has not); ``provider_rate_limited`` while another download runs.
    """
    ceiling = settings.workbench_download_max_bytes
    async with one_download(user_id), open_tool_client(_TOOL, user_id) as opened:
        client: GoogleDriveClient = opened.client
        async with provider_call(_TOOL, "download", act=False):
            raw = await client.get_file_metadata(query.id, fields=_DOWNLOAD_FIELDS)
            mime_type = str(raw.get("mimeType") or "")
            name = str(raw.get("name") or "")
            if is_google_type(mime_type):
                export = _export_of(mime_type, query.format)
                data = await client.export_google_doc(query.id, export.mime_type)
                _within(len(data or b""), ceiling)
                return DriveDownload(data or b"", f"{name}.{export.extension}", export.mime_type)
            if query.format is not None:
                refuse(NOT_SUPPORTED_BY_PROVIDER)
            listed = _size(raw)
            if listed is not None:
                _within(listed, ceiling)
            data = await client.get_file_content(
                query.id, max_size_bytes=ceiling, known_size=listed
            )
            if data is None:
                refuse(TOO_LARGE, max_bytes=ceiling)
            _within(len(data), ceiling)
            return DriveDownload(data, name, mime_type)


async def trash_files(user_id: UUID, selection: FileSelection) -> ActOutcome:
    """Move a selection to Drive's trash; each file answered."""
    ids = list(dict.fromkeys(selection.file_ids))
    async with open_tool_client(_TOOL, user_id) as opened:
        client: GoogleDriveClient = opened.client
        async with provider_call(_TOOL, "trash", act=False):
            settled = await settle_each(ids, client.delete_file)
            return act_outcome(ids, settled, tool=_TOOL.value)


async def _trail(
    client: GoogleDriveClient, raw: Mapping[str, Any]
) -> tuple[list[FileAncestor], bool, bool]:
    """The folders above ``raw`` from the top down; whether My Drive was reached; whether cut."""
    current = _first_parent(raw)
    if current is None:
        return [], False, False
    root = (await client.get_file_metadata(_ROOT, fields=["id"])).get("id")
    walked: list[FileAncestor] = []
    for _ in range(WORKBENCH_DRIVE_BREADCRUMB_MAX_DEPTH):
        if current == root:
            return walked[::-1], True, False
        folder = await client.get_file_metadata(current, fields=_TRAIL_FIELDS)
        walked.append(FileAncestor(id=current, name=str(folder.get("name") or "")))
        current = _first_parent(folder)
        if current is None:
            return walked[::-1], False, False
    return walked[::-1], current == root, current != root


def _first_parent(raw: Mapping[str, Any]) -> str | None:
    parents = raw.get("parents")
    return str(parents[0]) if isinstance(parents, list) and parents else None


def _export_of(mime_type: str, asked: ExportFormat | None) -> Export:
    """The export a Google document leaves as, or a refusal (no export, or not that one)."""
    offered = EXPORTS.get(mime_type)
    if not offered:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    if asked is None:
        return next(iter(offered.values()))
    if asked not in offered:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    return offered[asked]


def _within(size: int, ceiling: int) -> None:
    if size > ceiling:
        refuse(TOO_LARGE, max_bytes=ceiling)


def _size(raw: Mapping[str, Any]) -> int | None:
    value = raw.get("size")
    return int(value) if isinstance(value, str | int) and str(value).isdecimal() else None


def _web_url(value: object) -> str | None:
    """Drive's own https address, or nothing — never a link another host could serve."""
    if not isinstance(value, str):
        return None
    parts = urlsplit(value)
    on_drive = parts.scheme == "https" and parts.hostname in _DRIVE_HOSTS and not parts.username
    return value if on_drive else None


def _item(raw: Mapping[str, Any]) -> DriveItem:
    mime_type = str(raw.get("mimeType") or "")
    shortcut = raw.get("shortcutDetails")
    target = shortcut if isinstance(shortcut, Mapping) else {}
    target_mime = target.get("targetMimeType")
    return DriveItem(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        kind=kind_of(mime_type),
        mime_type=mime_type,
        modified_at=raw.get("modifiedTime") or None,
        size=_size(raw),
        web_url=_web_url(raw.get("webViewLink")),
        target_id=str(target["targetId"]) if target.get("targetId") else None,
        target_kind=kind_of(str(target_mime)) if target_mime else None,
        formats=formats_of(mime_type),
        downloadable=kind_of(mime_type) == "file" and is_downloadable(mime_type),
    )
