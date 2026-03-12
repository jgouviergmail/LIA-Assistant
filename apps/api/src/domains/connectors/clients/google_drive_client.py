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

from typing import Any
from uuid import UUID

import structlog

from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache.redis import CacheService

logger = structlog.get_logger(__name__)


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
    ) -> dict[str, Any]:
        """
        Search for files in Google Drive.

        Args:
            query: Search query text
            max_results: Maximum number of results to return (default: 10, max: 100)
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
                   - "full_text": Search in file name AND content

        Returns:
            Dict with 'files' list containing file metadata

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
            escaped_query = query.replace("'", "\\'")
            if search_mode == "full_text":
                q_parts.append(f"fullText contains '{escaped_query}'")
            else:
                q_parts.append(f"name contains '{escaped_query}'")

        # Filter by MIME type
        if mime_type:
            q_parts.append(f"mimeType = '{mime_type}'")

        # Filter by content type (files vs folders)
        if content_type == "files_only":
            q_parts.append("mimeType != 'application/vnd.google-apps.folder'")
        elif content_type == "folders_only":
            q_parts.append("mimeType = 'application/vnd.google-apps.folder'")
        # "all" or None: no filtering

        # Filter by folder
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")

        # Only include non-trashed files
        q_parts.append("trashed = false")

        q = " and ".join(q_parts)

        # Limit max results
        max_results = apply_max_items_limit(max_results)

        # Field projection for optimization
        fields_to_use = fields if fields else GOOGLE_DRIVE_SEARCH_FIELDS
        fields_str = ",".join(fields_to_use)

        params = {
            "q": q,
            "pageSize": max_results,
            "fields": f"files({fields_str})",
            "orderBy": "modifiedTime desc",
        }

        response = await self._make_request("GET", "/files", params)

        logger.info(
            "drive_search_completed",
            user_id=str(self.user_id),
            query=query,
            search_mode=search_mode,
            results_count=len(response.get("files", [])),
            fields_projected=bool(fields),
        )

        return response

    async def list_files(
        self,
        folder_id: str = "root",
        max_results: int = 20,
        page_token: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
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
        from src.core.constants import GOOGLE_DRIVE_LIST_FIELDS

        # Limit max results
        max_results = apply_max_items_limit(max_results)

        # Field projection for optimization
        fields_to_use = fields if fields else GOOGLE_DRIVE_LIST_FIELDS
        fields_str = ",".join(fields_to_use)

        # Build query with content type filter
        q_parts = [f"'{folder_id}' in parents", "trashed = false"]
        if content_type == "files_only":
            q_parts.append("mimeType != 'application/vnd.google-apps.folder'")
        elif content_type == "folders_only":
            q_parts.append("mimeType = 'application/vnd.google-apps.folder'")
        # "all" or None: no filtering

        params = {
            "q": " and ".join(q_parts),
            "pageSize": max_results,
            "fields": f"nextPageToken,files({fields_str})",
            "orderBy": "folder,name",
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

        params = {
            "fields": fields_str,
        }

        response = await self._make_request("GET", f"/files/{file_id}", params)

        logger.info(
            "drive_get_file_metadata",
            user_id=str(self.user_id),
            file_id=file_id,
            file_name=response.get("name"),
            fields_projected=bool(fields),
        )

        return response

    async def get_file_content(
        self,
        file_id: str,
        max_size_bytes: int = 10 * 1024 * 1024,  # 10 MB default limit
    ) -> bytes | None:
        """
        Download file content.

        Only works for non-Google Docs files (PDFs, images, etc.).
        For Google Docs, use export_google_doc() instead.

        Args:
            file_id: Google Drive file ID
            max_size_bytes: Maximum file size to download (default: 10 MB)

        Returns:
            File content as bytes, or None if file is too large

        Example:
            >>> content = await client.get_file_content("1abc123...")
            >>> if content:
            ...     with open("downloaded.pdf", "wb") as f:
            ...         f.write(content)
        """
        # First check file size
        metadata = await self.get_file_metadata(file_id)
        file_size = int(metadata.get("size", 0))

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
            f"/files/{file_id}",
            {"alt": "media"},
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
            f"/files/{file_id}/export",
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
            f"/files/{file_id}",
            json_data={"trashed": True},
        )

        logger.info(
            "drive_file_deleted",
            user_id=str(self.user_id),
            file_id=file_id,
        )

        return True
