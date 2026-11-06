"""
Google Drive API client.

Provides read access to Google Drive for document search, listing, and content retrieval.
Uses the Google Drive API v3.

API Reference:
- https://developers.google.com/drive/api/v3/reference

Scopes required:
- https://www.googleapis.com/auth/drive.readonly (read-only access)
- https://www.googleapis.com/auth/drive.metadata.readonly (metadata only)
- https://www.googleapis.com/auth/drive (full access required for delete/write operations)
"""

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

import httpx
import structlog
from fastapi import status

from src.core.config import settings
from src.core.constants import (
    GOOGLE_DRIVE_FOLDER_MIME,
    GOOGLE_DRIVE_LIST_FIELDS,
    GOOGLE_DRIVE_UPLOAD_BASE_URL,
    RAG_DRIVE_CHANGES_PAGE_SIZE_DEFAULT,
    RAG_DRIVE_CHANGES_PAGE_SIZE_MAX,
    WORKBENCH_DRIVE_BREADCRUMB_MAX_DEPTH,
    WORKBENCH_DRIVE_FIELDS,
    WORKBENCH_UPLOAD_TIMEOUT_SECONDS,
)
from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache.redis import CacheService

logger = structlog.get_logger(__name__)

#: What each view asks Drive, and how it reads it.
_VIEWS: Final[dict[str, tuple[str, str]]] = {
    "recent": (
        f"mimeType != '{GOOGLE_DRIVE_FOLDER_MIME}' and trashed = false",
        "viewedByMeTime desc",
    ),
    "starred": ("starred = true and trashed = false", "folder,name"),
    "shared": ("sharedWithMe = true and trashed = false", "sharedWithMeTime desc"),
    "trash": ("trashed = true", "modifiedTime desc"),
}
_TRASH_VIEW: Final = "trash"
_ANYONE: Final = "anyone"
_PERMISSION_FIELDS: Final = "permissions(id,type,role,emailAddress,displayName)"
#: What a role is called on both drives; Drive's others (a commenter) read.
_KEPT_ROLES: Final = frozenset({"owner", "writer", "reader"})
_DRIVES_VIEW: Final = "drives"
#: Drive answers 404 for a shared drive's item to a call that does not say it can read them.
_ALL_DRIVES: Final = {"supportsAllDrives": "true"}
_ALL_DRIVES_LISTED: Final = {**_ALL_DRIVES, "includeItemsFromAllDrives": "true"}
#: What Drive answers of an item put in the trash, against one a trashed folder holds.
_EXPLICITLY_TRASHED: Final = "explicitlyTrashed"
#: The top of the drive: an alias, never what an item's ``parents`` name.
_ROOT = "root"
_SESSION_ADDRESS = "address"


def _file_path(file_id: str, suffix: str = "") -> str:
    """``/files/<id>``, the id quoted as ONE path segment (a folded one refused)."""
    return f"/files/{path_segment(file_id, connector_type=ConnectorType.GOOGLE_DRIVE)}{suffix}"


def _upload_session(response: httpx.Response) -> dict[str, Any]:
    """The session Drive opened: on its own upload host, or the token goes nowhere."""
    address = response.headers.get("Location", "")
    if not address.startswith(f"{GOOGLE_DRIVE_UPLOAD_BASE_URL}/"):
        raise ConnectorAPIError(
            connector_type=ConnectorType.GOOGLE_DRIVE.value,
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="google_drive API error: no upload session",
        )
    return {_SESSION_ADDRESS: address}


def _person_of(raw: dict[str, Any]) -> dict[str, Any]:
    """A permission as the contract says it; a commenter reads."""
    role = str(raw.get("role"))
    return {
        "id": str(raw.get("id")),
        "email": raw.get("emailAddress"),
        "name": raw.get("displayName"),
        "role": role if role in _KEPT_ROLES else "reader",
    }


def _item_fields() -> dict[str, str]:
    """What an act reads back: the fields the page's list shows."""
    return {**_ALL_DRIVES, "fields": ",".join(WORKBENCH_DRIVE_FIELDS)}


def _q_literal(value: str) -> str:
    r"""``value`` as a string literal of Drive's ``q`` grammar.

    The backslash is escaped BEFORE the quote: escaping only the quote turns
    ``a\'`` into an escaped backslash followed by a quote that closes the string.
    """
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def changes_feed_timeout() -> httpx.Timeout:
    """The changes feed's budget: the bulk-read budget to read, the standard one to connect.

    Measured on 2026-10-26: a page of a long feed waited for its headers past the
    generic 5 s read budget, three attempts in a row, and the whole drain was lost
    (3 wakes of 1 292 in seven days, Google slow while the feed was long). A page of
    1 000 changes is a bulk read; reaching Google is not.
    """
    return httpx.Timeout(
        settings.http_timeout_connector_long, connect=settings.http_timeout_external_api
    )


class GoogleDriveClient(BaseGoogleClient):
    """
    Client for Google Drive API.

    Provides read-only access to:
    - Search files and folders
    - List files in folders
    - Get file metadata and content
    - Download file content

    Example:
        >>> client = GoogleDriveClient(user_id, credentials, connector_service)
        >>> results = await client.search_files(query="report 2024")
        >>> print(f"Found {len(results['files'])} files")
    """

    connector_type = ConnectorType.GOOGLE_DRIVE
    api_base_url = "https://www.googleapis.com/drive/v3"

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
        cache_service: CacheService | None = None,
        rate_limit_per_second: int = 10,
    ) -> None:
        """
        Initialize Google Drive client.

        Args:
            user_id: User UUID
            credentials: OAuth credentials
            connector_service: ConnectorService instance for token refresh
            cache_service: Optional cache service for caching results
            rate_limit_per_second: Max requests per second (default: 10)
        """
        super().__init__(user_id, credentials, connector_service, rate_limit_per_second)
        self._cache_service = cache_service

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    async def search_files(
        self,
        query: str,
        max_results: int = 10,
        mime_type: str | None = None,
        folder_id: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
        search_mode: str = "name_only",
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """
        Search for files in Google Drive.

        Args:
            query: Search query text
            max_results: Maximum number of results per page (default: 10, max: 100)
            mime_type: Filter by MIME type (e.g., "application/pdf")
            folder_id: Search within a specific folder
            fields: List of file fields to return (optional, for optimization).
                   If None, returns default search fields.
                   Example: ["id", "name", "mimeType", "modifiedTime"]
            content_type: Filter by content type:
                   - "files_only" (default): Exclude folders, return only files
                   - "folders_only": Return only folders
                   - "all" or None: Return both files and folders
            search_mode: Search scope:
                   - "name_only" (default): Search by file name only
                   - "full_text": Search in file name AND content (relevance
                     order: Drive refuses a sort beside a fullText term)
            page_token: The next page's token, from a previous answer.

        Returns:
            Dict with 'files' list containing file metadata, and
            'nextPageToken' while Drive holds more (a page may be partial
            before the end — only the token says more).

        Example:
            >>> results = await client.search_files("budget 2024", max_results=5)
            >>> for file in results["files"]:
            ...     print(f"{file['name']} ({file['mimeType']})")
        """
        from src.core.constants import GOOGLE_DRIVE_SEARCH_FIELDS

        # Build query string for Drive API
        q_parts = []

        # Search by name or full text depending on mode
        if query:
            if search_mode == "full_text":
                q_parts.append(f"fullText contains {_q_literal(query)}")
            else:
                q_parts.append(f"name contains {_q_literal(query)}")

        # Filter by MIME type
        if mime_type:
            q_parts.append(f"mimeType = {_q_literal(mime_type)}")

        # Filter by content type (files vs folders)
        if content_type == "files_only":
            q_parts.append("mimeType != 'application/vnd.google-apps.folder'")
        elif content_type == "folders_only":
            q_parts.append("mimeType = 'application/vnd.google-apps.folder'")
        # "all" or None: no filtering

        # Filter by folder
        if folder_id:
            q_parts.append(f"{_q_literal(folder_id)} in parents")

        # Only include non-trashed files
        q_parts.append("trashed = false")

        q = " and ".join(q_parts)

        # Limit max results
        max_results = apply_max_items_limit(max_results)

        # Field projection for optimization
        fields_to_use = fields if fields else GOOGLE_DRIVE_SEARCH_FIELDS
        fields_str = ",".join(fields_to_use)

        params = {
            **_ALL_DRIVES_LISTED,
            "q": q,
            "pageSize": max_results,
            "fields": f"nextPageToken,files({fields_str})",
        }
        if search_mode != "full_text":
            # Drive refuses a sort beside a fullText term (relevance order only).
            params["orderBy"] = "modifiedTime desc"
        if page_token:
            params["pageToken"] = page_token

        response = await self._make_request("GET", "/files", params)

        logger.info(
            "drive_search_completed",
            user_id=str(self.user_id),
            query_length=len(query),
            search_mode=search_mode,
            results_count=len(response.get("files", [])),
            fields_projected=bool(fields),
        )

        return response

    async def recent_files(self, max_results: int) -> dict[str, Any]:
        """The files changed last, across the drive.

        Args:
            max_results: How many files to keep.

        Returns:
            ``files``, newest first; never a folder.
        """
        return await self.search_files(
            query="",
            max_results=max_results,
            fields=["id", "name", "mimeType", "modifiedTime", "webViewLink", "parents"],
        )

    async def folder_path(self, file: Mapping[str, Any], known: dict[str, Any]) -> str | None:
        """A file's folders from the top of the drive, named by walking up its parents.

        Args:
            file: The file, with its ``parents``.
            known: The folders read so far: a card's files share theirs, read once.

        Returns:
            The path, empty at the top of the drive, My Drive left out; None for a file with no
            parent (shared with the person) or a tree past the bound.
        """
        parents = file.get("parents") or []
        if not parents:
            return None
        names: list[str] = []
        current = str(parents[0])
        for _ in range(WORKBENCH_DRIVE_BREADCRUMB_MAX_DEPTH):
            if current not in known:
                known[current] = await self.get_file_metadata(
                    current, fields=["id", "name", "parents"]
                )
            folder = known[current]
            above = folder.get("parents") or []
            if not above:
                return "/".join(reversed(names))
            names.append(str(folder.get("name") or ""))
            current = str(above[0])
        return None

    async def list_files(
        self,
        folder_id: str = "root",
        max_results: int = 20,
        page_token: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
        order_by: str = "folder,name",
    ) -> dict[str, Any]:
        """
        List files in a folder.

        Args:
            folder_id: Folder ID to list files from (default: "root" for root folder)
            max_results: Maximum number of results per page (default: 20, max: 100)
            page_token: Token for pagination (from previous response)
            fields: List of file fields to return (optional, for optimization).
                   If None, returns default list fields.
            content_type: Filter by content type:
                   - "files_only" (default): Exclude folders, return only files
                   - "folders_only": Return only folders
                   - "all" or None: Return both files and folders

        Returns:
            Dict with 'files' list and optional 'nextPageToken'

        Example:
            >>> results = await client.list_files(folder_id="root")
            >>> for file in results["files"]:
            ...     print(f"{file['name']} - {file['mimeType']}")
        """

        # Limit max results
        max_results = apply_max_items_limit(max_results)

        # Field projection for optimization
        fields_to_use = fields if fields else GOOGLE_DRIVE_LIST_FIELDS
        fields_str = ",".join(fields_to_use)

        # Build query with content type filter
        q_parts = [f"{_q_literal(folder_id)} in parents", "trashed = false"]
        if content_type == "files_only":
            q_parts.append("mimeType != 'application/vnd.google-apps.folder'")
        elif content_type == "folders_only":
            q_parts.append("mimeType = 'application/vnd.google-apps.folder'")
        # "all" or None: no filtering

        params = {
            **_ALL_DRIVES_LISTED,
            "q": " and ".join(q_parts),
            "pageSize": max_results,
            "fields": f"nextPageToken,files({fields_str})",
            "orderBy": order_by,
        }

        if page_token:
            params["pageToken"] = page_token

        response = await self._make_request("GET", "/files", params)

        logger.info(
            "drive_list_files_completed",
            user_id=str(self.user_id),
            folder_id=folder_id,
            results_count=len(response.get("files", [])),
            has_next_page=bool(response.get("nextPageToken")),
            fields_projected=bool(fields),
        )

        return response

    async def get_file_metadata(
        self,
        file_id: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Get detailed metadata for a file.

        Args:
            file_id: Google Drive file ID
            fields: List of file fields to return (optional, for optimization).
                   If None, returns all detail fields.

        Returns:
            File metadata including name, type, size, sharing info, etc.

        Example:
            >>> file = await client.get_file_metadata("1abc123...")
            >>> print(f"Name: {file['name']}, Size: {file.get('size', 'N/A')}")
        """
        from src.core.constants import GOOGLE_DRIVE_DETAILS_FIELDS

        # Field projection for optimization
        fields_to_use = fields if fields else GOOGLE_DRIVE_DETAILS_FIELDS
        fields_str = ",".join(fields_to_use)

        params = {**_ALL_DRIVES, "fields": fields_str}

        response = await self._make_request("GET", _file_path(file_id), params)

        logger.info(
            "drive_get_file_metadata",
            user_id=str(self.user_id),
            file_id=file_id,
            fields_projected=bool(fields),
        )

        return response

    async def get_file_content(
        self,
        file_id: str,
        max_size_bytes: int = 10 * 1024 * 1024,  # 10 MB default limit
        known_size: int | None = None,
    ) -> bytes | None:
        """
        Download file content.

        Only works for non-Google Docs files (PDFs, images, etc.).
        For Google Docs, use export_google_doc() instead.

        Args:
            file_id: Google Drive file ID
            max_size_bytes: Maximum file size to download (default: 10 MB)
            known_size: The size the caller already read from the metadata —
                then the metadata is not read a second time.

        Returns:
            File content as bytes, or None if file is too large

        Example:
            >>> content = await client.get_file_content("1abc123...")
            >>> if content:
            ...     with open("downloaded.pdf", "wb") as f:
            ...         f.write(content)
        """
        # First check file size
        if known_size is None:
            metadata = await self.get_file_metadata(file_id)
            file_size = int(metadata.get("size", 0))
        else:
            file_size = known_size

        if file_size > max_size_bytes:
            logger.warning(
                "drive_file_too_large",
                user_id=str(self.user_id),
                file_id=file_id,
                file_size=file_size,
                max_size=max_size_bytes,
            )
            return None

        # Download file content
        response = await self._make_raw_request(
            "GET",
            _file_path(file_id),
            {**_ALL_DRIVES, "alt": "media"},
        )

        logger.info(
            "drive_file_downloaded",
            user_id=str(self.user_id),
            file_id=file_id,
            content_length=len(response) if response else 0,
        )

        return response

    async def export_google_doc(
        self,
        file_id: str,
        export_mime_type: str = "text/plain",
    ) -> bytes | None:
        """
        Export a Google Docs file (Docs, Sheets, Slides) to a different format.

        Args:
            file_id: Google Drive file ID
            export_mime_type: Target MIME type for export. Options:
                - "text/plain" (plain text)
                - "text/html" (HTML)
                - "application/pdf" (PDF)
                - "application/vnd.openxmlformats-officedocument.wordprocessingml.document" (DOCX)
                - "text/csv" (CSV for Sheets)
                - "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" (XLSX)

        Returns:
            Exported content as bytes

        Example:
            >>> content = await client.export_google_doc("1abc123...", "text/plain")
            >>> print(content.decode("utf-8"))
        """
        response = await self._make_raw_request(
            "GET",
            _file_path(file_id, "/export"),
            {"mimeType": export_mime_type},
        )

        logger.info(
            "drive_doc_exported",
            user_id=str(self.user_id),
            file_id=file_id,
            export_mime_type=export_mime_type,
            content_length=len(response) if response else 0,
        )

        return response

    # =========================================================================
    # WRITE OPERATIONS (Requires broader scope)
    # =========================================================================

    async def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from Google Drive (move to trash).

        Requires https://www.googleapis.com/auth/drive scope.

        Args:
            file_id: Google Drive file ID to delete

        Returns:
            True if successful

        Example:
            >>> success = await client.delete_file("1abc123...")
            >>> print("File deleted" if success else "Delete failed")
        """
        # Move to trash instead of permanent delete (safer, recoverable)
        await self._make_request(
            "PATCH",
            _file_path(file_id),
            _ALL_DRIVES,
            json_data={"trashed": True},
        )

        logger.info(
            "drive_file_deleted",
            user_id=str(self.user_id),
            file_id=file_id,
        )

        return True

    async def create_folder(self, name: str, parent_id: str = "root") -> dict[str, Any]:
        """Create a folder.

        Args:
            name: Its name.
            parent_id: Its parent, ``root`` for the top of the drive.

        Returns:
            The folder.
        """
        return await self._make_request(
            "POST",
            "/files",
            _item_fields(),
            json_data={"name": name, "mimeType": GOOGLE_DRIVE_FOLDER_MIME, "parents": [parent_id]},
        )

    async def rename_file(self, file_id: str, name: str) -> dict[str, Any]:
        """Give an item another name.

        Args:
            file_id: The item.
            name: Its new name.

        Returns:
            The item.
        """
        return await self._make_request(
            "PATCH", _file_path(file_id), _item_fields(), json_data={"name": name}
        )

    async def move_file(self, file_id: str, parent_id: str) -> dict[str, Any]:
        """Move an item, leaving every parent it had.

        Args:
            file_id: The item.
            parent_id: Its new parent, ``root`` for the top of the drive.

        Returns:
            The item.
        """
        current = await self.get_file_metadata(file_id, fields=["id", "parents"])
        target = await self._real_parent(parent_id)
        leaving = [parent for parent in current.get("parents") or [] if parent != target]
        params = {**_item_fields(), "addParents": target}
        if leaving:
            params["removeParents"] = ",".join(leaving)
        return await self._make_request("PATCH", _file_path(file_id), params, json_data={})

    async def _real_parent(self, parent_id: str) -> str:
        """A parent as an item's ``parents`` name it: ``root`` is an alias, never an id."""
        if parent_id != _ROOT:
            return parent_id
        return str((await self.get_file_metadata(_ROOT, fields=["id"])).get("id"))

    async def list_view(
        self,
        view: str,
        *,
        max_results: int,
        page_token: str | None,
        fields: list[str],
    ) -> dict[str, Any]:
        """One page of what Drive holds under a view.

        The trash lists what the person put there: what a trashed folder holds went with it
        and returns with it, so a page may come back shorter than asked, or empty. A shared
        drive is listed as a folder: its id opens it like one.

        Args:
            view: ``recent``, ``starred``, ``shared``, ``trash`` or ``drives``.
            max_results: The page's size.
            page_token: The next page's token.
            fields: The fields each item carries.

        Returns:
            Dict with ``files`` and an optional ``nextPageToken``.
        """
        if view == _DRIVES_VIEW:
            return await self._shared_drives(max_results, page_token)
        term, order = _VIEWS[view]
        asked = [*fields, _EXPLICITLY_TRASHED] if view == _TRASH_VIEW else fields
        params: dict[str, Any] = {
            **_ALL_DRIVES_LISTED,
            "q": term,
            "orderBy": order,
            "pageSize": apply_max_items_limit(max_results),
            "fields": f"nextPageToken,files({','.join(asked)})",
        }
        if page_token:
            params["pageToken"] = page_token
        page = await self._make_request("GET", "/files", params)
        if view == _TRASH_VIEW:
            files = page.get("files") or []
            page["files"] = [item for item in files if item.get(_EXPLICITLY_TRASHED) is True]
        return page

    async def _shared_drives(self, max_results: int, page_token: str | None) -> dict[str, Any]:
        """One page of the shared drives the person reaches, each as a folder."""
        params: dict[str, Any] = {"pageSize": apply_max_items_limit(max_results)}
        if page_token:
            params["pageToken"] = page_token
        page = await self._make_request("GET", "/drives", params)
        files = [
            {"id": drive.get("id"), "name": drive.get("name"), "mimeType": GOOGLE_DRIVE_FOLDER_MIME}
            for drive in page.get("drives") or []
        ]
        return {"files": files, "nextPageToken": page.get("nextPageToken")}

    async def read_sharing(self, file_id: str) -> dict[str, Any]:
        """Who reaches an item, and the link anyone can follow, if it has one.

        Args:
            file_id: The item.

        Returns:
            ``people`` and ``link``.
        """
        answer = await self._make_request(
            "GET",
            _file_path(file_id, "/permissions"),
            {**_ALL_DRIVES, "fields": _PERMISSION_FIELDS},
        )
        permissions = answer.get("permissions") or []
        people = [_person_of(raw) for raw in permissions if raw.get("type") != _ANYONE]
        anyone = next((raw for raw in permissions if raw.get("type") == _ANYONE), None)
        link = await self._link_of(file_id, anyone) if anyone else None
        return {"people": people, "link": link}

    async def _link_of(self, file_id: str, permission: dict[str, Any]) -> dict[str, Any]:
        """A link's address: Drive keeps it on the file."""
        item = await self.get_file_metadata(file_id, fields=["webViewLink"])
        return {"id": str(permission.get("id")), "url": item.get("webViewLink")}

    async def share_with(self, file_id: str, email: str, role: str) -> None:
        """Give a person access; Drive tells them.

        Args:
            file_id: The item.
            email: Their address.
            role: ``reader`` or ``writer``.
        """
        await self._make_request(
            "POST",
            _file_path(file_id, "/permissions"),
            {**_ALL_DRIVES, "sendNotificationEmail": "true"},
            {"type": "user", "role": role, "emailAddress": email},
            max_retries=1,
        )

    async def open_link(self, file_id: str) -> dict[str, Any]:
        """Let anyone with the link read an item.

        Args:
            file_id: The item.

        Returns:
            The link: its ``id`` and its ``url``.
        """
        permission = await self._make_request(
            "POST",
            _file_path(file_id, "/permissions"),
            _ALL_DRIVES,
            {"type": _ANYONE, "role": "reader"},
            max_retries=1,
        )
        return await self._link_of(file_id, permission)

    async def remove_share(self, file_id: str, permission_id: str) -> None:
        """Take an access back.

        Args:
            file_id: The item.
            permission_id: The access.
        """
        segment = path_segment(permission_id, connector_type=ConnectorType.GOOGLE_DRIVE)
        await self._make_request(
            "DELETE", _file_path(file_id, f"/permissions/{segment}"), _ALL_DRIVES
        )

    async def storage_quota(self) -> dict[str, int | None]:
        """What the account uses of what it has; an unlimited one has no total.

        Returns:
            ``used`` and ``total``, in bytes.
        """
        answer = await self._make_request("GET", "/about", {"fields": "storageQuota"})
        quota = answer.get("storageQuota") or {}
        limit = quota.get("limit")
        return {"used": int(quota.get("usage") or 0), "total": int(limit) if limit else None}

    async def restore_file(self, file_id: str) -> dict[str, Any]:
        """Take an item out of the trash.

        Args:
            file_id: The item.

        Returns:
            The item.
        """
        return await self._make_request(
            "PATCH", _file_path(file_id), _item_fields(), {"trashed": False}
        )

    async def delete_file_forever(self, file_id: str) -> None:
        """Delete an item for good: nothing brings it back.

        Args:
            file_id: The item.
        """
        await self._make_request("DELETE", _file_path(file_id), _ALL_DRIVES)

    async def empty_trash(self) -> None:
        """Delete for good all that the trash holds."""
        await self._make_request("DELETE", "/files/trash")

    async def set_starred(self, file_id: str, starred: bool) -> dict[str, Any]:
        """Star an item, or take its star back.

        Args:
            file_id: The item.
            starred: Its star.

        Returns:
            The item.
        """
        return await self._make_request(
            "PATCH", _file_path(file_id), _item_fields(), {"starred": starred}
        )

    async def upload_file(
        self, name: str, data: bytes, mime_type: str, parent_id: str = _ROOT
    ) -> dict[str, Any]:
        """Add a file to a folder; Drive keeps several under one name.

        Drive keeps its one-shot bodies for 5 MB or less, so the bytes go through a session.
        Opening one creates nothing and may be repeated; the bytes are sent once, a lost
        answer leaving the file unknown rather than sent twice.

        Args:
            name: Its name.
            data: Its bytes.
            mime_type: Its type.
            parent_id: Its folder, ``root`` for the top of the drive.

        Returns:
            The file.
        """
        session = await self._make_request(
            "POST",
            "/files",
            {**_item_fields(), "uploadType": "resumable"},
            {"name": name, "parents": [parent_id]},
            extra_headers={
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(len(data)),
            },
            base_url=GOOGLE_DRIVE_UPLOAD_BASE_URL,
            idempotent=True,
            answer=_upload_session,
        )
        return await self._make_request(
            "PUT",
            "",
            max_retries=1,
            extra_headers={"Content-Type": mime_type},
            content=data,
            base_url=session[_SESSION_ADDRESS],
            timeout=httpx.Timeout(WORKBENCH_UPLOAD_TIMEOUT_SECONDS),
        )

    async def replace_content(
        self, file_id: str, data: bytes, mime_type: str, expected_tag: str
    ) -> dict[str, Any]:
        """Replace a file's bytes, only as it was when read.

        Drive holds no condition on a write: the revision is read just before, so a change
        landing between the two calls is the one this cannot refuse. Sent once: a lost answer
        leaves the file unknown.

        Args:
            file_id: The file.
            data: Its new bytes (a text: well under the 5 MB of a one-shot body).
            mime_type: Its type.
            expected_tag: The head revision it was read at.

        Returns:
            The file as Drive answers it.

        Raises:
            OfficeContentRefusedError: It changed since it was read.
        """
        current = await self.get_file_metadata(file_id, fields=["headRevisionId"])
        if current.get("headRevisionId") != expected_tag:
            raise OfficeContentRefusedError(OfficeRefusal.CHANGED)
        return await self._make_request(
            "PATCH",
            _file_path(file_id),
            {**_item_fields(), "uploadType": "media"},
            max_retries=1,
            extra_headers={"Content-Type": mime_type},
            content=data,
            base_url=GOOGLE_DRIVE_UPLOAD_BASE_URL,
            timeout=httpx.Timeout(WORKBENCH_UPLOAD_TIMEOUT_SECONDS),
        )

    async def copy_file(
        self, file_id: str, parent_id: str | None = None, name: str | None = None
    ) -> dict[str, Any] | None:
        """Copy a file.

        Args:
            file_id: The file.
            parent_id: The folder it goes to; left out, beside the original.
            name: Its name; left out, Drive's own (« Copy of … »).

        Returns:
            The copy.
        """
        body: dict[str, Any] = {}
        if parent_id:
            body["parents"] = [parent_id]
        if name:
            body["name"] = name
        return await self._make_request(
            "POST", _file_path(file_id, "/copy"), _item_fields(), json_data=body
        )

    async def get_changes_start_page_token(self) -> str:
        """Current changes baseline — the pageToken future changes start from."""
        response = await self._make_request("GET", "/changes/startPageToken")
        return str(response.get("startPageToken", ""))

    async def list_changes(
        self, page_token: str, page_size: int = RAG_DRIVE_CHANGES_PAGE_SIZE_DEFAULT
    ) -> dict[str, Any]:
        """One page of the changes feed since ``page_token`` (ADR-261 P2, ADR-304).

        An INTERNAL pagination: the feed is drained by the push reindex, never
        handed to an agent, so the agent-facing item ceiling
        (``apply_max_items_limit``, 25) does not apply — applied here it made the
        feed 40 times chattier (measured 2026-09-22). The size is clamped to
        Google's own maximum instead.

        Args:
            page_token: The token stored with the watch channel (or the
                ``nextPageToken`` of the previous page).
            page_size: Changes per page, at most Google's 1000.

        Returns:
            ``{"changes": [...], "nextPageToken"?: ..., "newStartPageToken"?: ...}``
            — the presence of ``newStartPageToken`` means the feed is drained
            and that token is the next baseline.
        """
        return await self._make_request(
            "GET",
            "/changes",
            params={
                "pageToken": page_token,
                "pageSize": max(1, min(page_size, RAG_DRIVE_CHANGES_PAGE_SIZE_MAX)),
                "fields": (
                    "nextPageToken,newStartPageToken,"
                    "changes(fileId,removed,changeType,"
                    "file(id,name,mimeType,modifiedTime,parents,trashed))"
                ),
                "includeRemoved": "true",
            },
            timeout=changes_feed_timeout(),
        )

    async def watch_changes(
        self,
        channel_id: str,
        token: str,
        address: str,
        ttl_seconds: int,
        page_token: str,
    ) -> dict[str, Any]:
        """Open a push channel on the user's Drive changes feed (lot H phase 1).

        Args:
            channel_id: Our channel identifier (echoed in X-Goog-Channel-ID).
            token: Opaque secret echoed in X-Goog-Channel-Token.
            address: Public HTTPS webhook URL (domain must be verified).
            ttl_seconds: Requested channel lifetime (Google may shorten it).
            page_token: Changes baseline from :meth:`get_changes_start_page_token`.

        Returns:
            The channel resource returned by Google (resourceId, expiration).
        """
        return await self._make_request(
            "POST",
            "/changes/watch",
            params={"pageToken": page_token},
            json_data={
                "id": channel_id,
                "type": "web_hook",
                "address": address,
                "token": token,
                "params": {"ttl": str(ttl_seconds)},
            },
        )

    async def stop_channel(self, channel_id: str, resource_id: str) -> dict[str, Any]:
        """Close a push channel (API-wide /channels/stop endpoint)."""
        return await self._make_request(
            "POST",
            "/channels/stop",
            json_data={"id": channel_id, "resourceId": resource_id},
        )
