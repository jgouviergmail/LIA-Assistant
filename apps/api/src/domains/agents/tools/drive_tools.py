"""
LangChain v1 tools for Google Drive operations.

LOT 9: Google Drive integration with search, list, get, download, and export operations.

Migration (2025-12-30):
    - Migrated from StandardToolOutput to UnifiedToolOutput
    - UnifiedToolOutput provides: success, message, registry_updates, structured_data, error_message, error_code, metadata
    - Factory methods: UnifiedToolOutput.data_success(), UnifiedToolOutput.failure(), UnifiedToolOutput.action_success()
    - All functions now return UnifiedToolOutput directly (no conversion needed)

Pattern:
    @tool
    async def my_tool(
        arg: str,
        runtime: ToolRuntime,  # Unified access to runtime resources
    ) -> UnifiedToolOutput:
        user_id = runtime.config.get("configurable", {}).get("user_id")
        # Use runtime.config, runtime.store, runtime.state, etc.

Data Registry Mode (LOT 5):
    - Tools return UnifiedToolOutput with registry_updates for frontend rendering
    - Data Registry mode enabled via registry_enabled=True class attribute
    - Uses ToolOutputMixin for registry item creation
    - parallel_executor detects UnifiedToolOutput and extracts registry
    - Registry propagates to state and SSE stream for frontend rendering
"""

import asyncio
import json
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel

from src.core.config import settings
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import AGENT_FILE, CONTEXT_DOMAIN_FILES
from src.domains.agents.context import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.exceptions import ConnectorNotEnabledError
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.validation_helpers import (
    require_field,
    validate_positive_int_or_default,
)
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

# ============================================================================
# CONTEXT REGISTRATION
# ============================================================================


class FileItem(BaseModel):
    """
    Standardized file item schema for context manager.

    Used for reference resolution (e.g., "the 2nd file", "the document from yesterday").
    """

    id: str  # Google Drive file ID
    name: str  # File name
    mime_type: str = ""  # MIME type
    size: int = 0  # File size in bytes


# Register file context types for context manager
# This enables contextual references like "the 2nd file", "the document"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_FILES,
        agent_name=AGENT_FILE,
        item_schema=FileItem,
        primary_id_field="id",
        display_name_field="name",
        reference_fields=[
            "name",
            "mime_type",
        ],
        icon="📁",
    )
)


# ============================================================================
# HELPERS
# ============================================================================


async def _resolve_parent_paths(client: GoogleDriveClient, files: list[dict[str, Any]]) -> None:
    """Resolve full folder paths for files and enrich them in-place.

    Uses BFS to walk up the folder hierarchy level-by-level, batching API
    calls at each depth for efficiency.  Results are cached so that shared
    ancestors are fetched only once.  Sets ``parentPath`` on each file dict
    (e.g. ``"Mon Drive / Projets / 2024"``).
    """
    # folder_id → (name, parent_id | None)
    folder_cache: dict[str, tuple[str, str | None]] = {}

    # Collect immediate parent IDs
    ids_to_resolve: set[str] = set()
    for f in files:
        parents = f.get("parents")
        if parents and isinstance(parents, list):
            ids_to_resolve.add(parents[0])

    if not ids_to_resolve:
        return

    async def _fetch_folder_info(fid: str) -> tuple[str, str, str | None]:
        try:
            meta = await client.get_file_metadata(fid, fields=["name", "parents"])
            name = meta.get("name", "")
            fparents = meta.get("parents")
            parent_id = fparents[0] if fparents and isinstance(fparents, list) else None
            return fid, name, parent_id
        except Exception as e:
            logger.debug("resolve_parent_path_failed", folder_id=fid, error=str(e))
            return fid, "", None

    # BFS: resolve parents level by level until root
    max_depth = 10  # safety limit
    for _ in range(max_depth):
        new_ids = ids_to_resolve - set(folder_cache.keys())
        if not new_ids:
            break

        results = await asyncio.gather(*[_fetch_folder_info(fid) for fid in new_ids])

        ids_to_resolve = set()
        for fid, name, parent_id in results:
            folder_cache[fid] = (name, parent_id)
            if parent_id and parent_id not in folder_cache:
                ids_to_resolve.add(parent_id)

    def _build_path(folder_id: str) -> str:
        """Build full path from root down to *folder_id*."""
        parts: list[str] = []
        current: str | None = folder_id
        visited: set[str] = set()
        while current and current not in visited:
            visited.add(current)
            info = folder_cache.get(current)
            if not info or not info[0]:
                break
            parts.append(info[0])
            current = info[1]
        parts.reverse()
        return " / ".join(parts)

    for f in files:
        parents = f.get("parents")
        if parents and isinstance(parents, list):
            path = _build_path(parents[0])
            if path:
                f["parentPath"] = path


# ============================================================================
# TOOL 1: SEARCH FILES
# ============================================================================


class SearchFilesTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """
    Search files tool using Phase 3.2 architecture with Data Registry support.

    Data Registry Mode:
    - registry_enabled=True: Returns UnifiedToolOutput with registry items
    - Registry items contain file metadata for frontend rendering
    - Message for LLM is compact text with file names and IDs
    """

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize search files tool with Data Registry support."""
        super().__init__(tool_name="get_files_tool", operation="search")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute search files API call - business logic only."""
        from src.core.constants import (
            GOOGLE_DRIVE_DETAILS_FIELDS,
            GOOGLE_DRIVE_REQUIRED_FIELDS,
        )

        query: str = kwargs.get("query", "")
        raw_max_results = kwargs.get("max_results")
        default_max_results = settings.drive_tool_default_max_results
        max_results = validate_positive_int_or_default(raw_max_results, default=default_max_results)
        # Cap at domain-specific limit (DRIVE_TOOL_DEFAULT_MAX_RESULTS)
        security_cap = settings.drive_tool_default_max_results
        if max_results > security_cap:
            logger.warning(
                "drive_search_limit_capped",
                requested_max_results=raw_max_results,
                capped_max_results=security_cap,
                default_max_results=default_max_results,
            )
            max_results = security_cap
        mime_type: str | None = kwargs.get("mime_type")
        folder_id: str | None = kwargs.get("folder_id")
        fields: list[str] | None = kwargs.get("fields")
        content_type: str = kwargs.get("content_type", "files_only")
        search_mode: str = kwargs.get("search_mode", "name_only")

        # TOKEN EXPLOSION PREVENTION STRATEGY (Drive):
        # Unlike Emails (where date filtering is essential), Drive uses a different strategy:
        # 1. default_max_results=10 limits response size
        # 2. security_cap=50 hard limit
        # 3. Queries are typically targeted (file names, not "all my files")
        # We do NOT add default date filtering because:
        # - Files don't have the same temporal dimension as emails
        # - Users typically search for specific documents, not "recent files"
        # - modifiedTime filter syntax is more complex (RFC 3339 in query string)
        # - Current protections are sufficient

        # Apply default fields and ensure required fields are always included
        # Architecture v2.0: Always return full details (unified tool)
        fields_to_use = fields if fields else GOOGLE_DRIVE_DETAILS_FIELDS
        for required_field in GOOGLE_DRIVE_REQUIRED_FIELDS:
            if required_field not in fields_to_use:
                fields_to_use = [required_field] + list(fields_to_use)

        result = await client.search_files(
            query=query,
            max_results=max_results,
            mime_type=mime_type,
            folder_id=folder_id,
            fields=fields_to_use,
            content_type=content_type,
            search_mode=search_mode,
        )

        files = result.get("files", [])

        # Resolve parent folder names for file path display
        await _resolve_parent_paths(client, files)

        logger.info(
            "search_files_success",
            user_id=str(user_id),
            query_preview=query[:20] if query and len(query) > 20 else query,
            total_results=len(files),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "files": files,
            "query": query,
            "user_timezone": user_timezone,
            "locale": locale,
        }

    def format_response(self, result: dict[str, Any]) -> str:
        """Format using JSON (legacy mode)."""
        files = result.get("files", [])
        formatted_files = []
        for f in files:
            formatted_files.append(
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "mime_type": f.get("mimeType"),
                    "size": f.get("size"),
                    "modified_time": f.get("modifiedTime"),
                }
            )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "files": formatted_files,
                    "total": len(formatted_files),
                    "query": result.get("query", ""),
                },
            },
            ensure_ascii=False,
        )

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_file_payload() + fewshots.

        TIMEZONE: Dates are converted to user's timezone before storage.

        Returns:
            UnifiedToolOutput with registry items for frontend rendering
        """
        files = result.get("files", [])
        query = result.get("query", "")
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Use ToolOutputMixin helper with timezone conversion
        # build_files_output returns UnifiedToolOutput directly
        return self.build_files_output(
            files=files,
            query=query,
            from_cache=False,
            user_timezone=user_timezone,
            locale=locale,
        )


_search_files_tool_instance = SearchFilesTool()


@connector_tool(
    name="search_files",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="read",
)
async def search_files_tool(
    query: Annotated[str, "Search query for file names or content"],
    max_results: Annotated[
        int, "Maximum number of results (default settings.drive_tool_default_max_results, max 100)"
    ] = settings.drive_tool_default_max_results,
    mime_type: Annotated[str | None, "Filter by MIME type (e.g., 'application/pdf')"] = None,
    folder_id: Annotated[str | None, "Search within specific folder ID"] = None,
    content_type: Annotated[
        str,
        "Filter content type: 'files_only' (default, excludes folders), 'folders_only' (only folders), 'all' (both)",
    ] = "files_only",
    fields: Annotated[
        list[str] | None,
        "List of file fields to return for optimization (optional). Example: ['name', 'mimeType', 'modifiedTime']. If omitted, returns default search fields.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Search files in Google Drive by name or content.

    **Content Type Filtering:**
    - content_type="files_only" (default): Returns only files, excludes folders
    - content_type="folders_only": Returns only folders
    - content_type="all": Returns both files and folders

    Supports various MIME types:
    - application/pdf - PDF documents
    - application/vnd.google-apps.document - Google Docs
    - application/vnd.google-apps.spreadsheet - Google Sheets
    - application/vnd.google-apps.presentation - Google Slides
    - image/* - Images
    - video/* - Videos

    **Field Projection (optimization):**
    - If fields is specified, only those fields are returned (reduces latency and tokens)
    - "name" is always included to ensure file names are displayed
    - Available fields: id, name, mimeType, modifiedTime, size, owners, webViewLink, etc.

    Args:
        query: Search query (file name, content text, or both)
        max_results: Maximum number of files to return (default from settings, max 100)
        mime_type: Optional MIME type filter
        folder_id: Optional folder ID to search within
        content_type: Filter by content type (files_only, folders_only, all)
        fields: List of fields to return (optional, for optimization)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with matching files metadata (id, name, type, size, modified date)

    Examples:
        - search_files("rapport annuel") - Search files by name (excludes folders)
        - search_files("Documents", content_type="folders_only") - Search folders only
        - search_files("budget 2025", mime_type="application/vnd.google-apps.spreadsheet")
    """
    return await _search_files_tool_instance.execute(
        runtime=runtime,
        query=query,
        max_results=max_results,
        mime_type=mime_type,
        folder_id=folder_id,
        content_type=content_type,
        fields=fields,
    )


# ============================================================================
# TOOL 2: LIST FILES
# ============================================================================


class ListFilesTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """List files in Google Drive with optional filtering."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="get_files_tool", operation="list")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute list files API call."""
        from src.core.constants import (
            GOOGLE_DRIVE_DETAILS_FIELDS,
            GOOGLE_DRIVE_REQUIRED_FIELDS,
        )

        folder_id: str | None = kwargs.get("folder_id")
        raw_max_results = kwargs.get("max_results")
        default_max_results = settings.drive_tool_default_max_results
        max_results = validate_positive_int_or_default(raw_max_results, default=default_max_results)
        # Cap at domain-specific limit (DRIVE_TOOL_DEFAULT_MAX_RESULTS)
        security_cap = settings.drive_tool_default_max_results
        if max_results > security_cap:
            logger.warning(
                "drive_list_limit_capped",
                requested_max_results=raw_max_results,
                capped_max_results=security_cap,
                default_max_results=default_max_results,
            )
            max_results = security_cap

        fields: list[str] | None = kwargs.get("fields")
        content_type: str = kwargs.get("content_type", "files_only")

        # Apply default fields and ensure required fields are always included
        # Architecture v2.0: Always return full details (unified tool)
        fields_to_use = fields if fields else GOOGLE_DRIVE_DETAILS_FIELDS
        for required_field in GOOGLE_DRIVE_REQUIRED_FIELDS:
            if required_field not in fields_to_use:
                fields_to_use = [required_field] + list(fields_to_use)

        result = await client.list_files(
            folder_id=folder_id or "root",
            max_results=max_results,
            fields=fields_to_use,
            content_type=content_type,
        )

        files = result.get("files", [])

        # Resolve parent folder names for file path display
        await _resolve_parent_paths(client, files)

        logger.info(
            "list_files_success",
            user_id=str(user_id),
            folder_id=folder_id,
            total_results=len(files),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "files": files,
            "folder_id": folder_id,
            "user_timezone": user_timezone,
            "locale": locale,
        }

    def format_response(self, result: dict[str, Any]) -> str:
        """Format using JSON (legacy mode)."""
        files = result.get("files", [])
        formatted_files = []
        for f in files:
            formatted_files.append(
                {
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "mime_type": f.get("mimeType"),
                    "size": f.get("size"),
                    "modified_time": f.get("modifiedTime"),
                }
            )

        return json.dumps(
            {
                "success": True,
                "data": {
                    "files": formatted_files,
                    "total": len(formatted_files),
                },
            },
            ensure_ascii=False,
        )

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_file_payload() + fewshots.

        TIMEZONE: Dates are converted to user's timezone before storage.

        Returns:
            UnifiedToolOutput with registry items for frontend rendering
        """
        files = result.get("files", [])
        folder_id = result.get("folder_id")
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Use ToolOutputMixin helper with timezone conversion
        # build_files_output returns UnifiedToolOutput directly
        return self.build_files_output(
            files=files,
            folder_id=folder_id,
            from_cache=False,
            user_timezone=user_timezone,
            locale=locale,
        )


_list_files_tool_instance = ListFilesTool()


@connector_tool(
    name="list_files",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="read",
)
async def list_files_tool(
    folder_id: Annotated[str | None, "Folder ID to list files from (default: root)"] = None,
    max_results: Annotated[
        int, "Maximum number of results (default settings.drive_tool_default_max_results)"
    ] = settings.drive_tool_default_max_results,
    content_type: Annotated[
        str,
        "Filter content type: 'files_only' (default, excludes folders), 'folders_only' (only folders), 'all' (both)",
    ] = "files_only",
    fields: Annotated[
        list[str] | None,
        "List of file fields to return for optimization (optional). If omitted, returns default list fields.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    List files in Google Drive folder.

    **Content Type Filtering:**
    - content_type="files_only" (default): Returns only files, excludes folders
    - content_type="folders_only": Returns only folders
    - content_type="all": Returns both files and folders

    **Field Projection (optimization):**
    - If fields is specified, only those fields are returned (reduces latency and tokens)
    - "name" is always included to ensure file names are displayed

    Args:
        folder_id: Folder ID to list (default: root folder)
        max_results: Maximum files to return (default from settings)
        content_type: Filter by content type (files_only, folders_only, all)
        fields: List of fields to return (optional, for optimization)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with files in the folder and metadata
    """
    return await _list_files_tool_instance.execute(
        runtime=runtime,
        folder_id=folder_id,
        max_results=max_results,
        content_type=content_type,
        fields=fields,
    )


# ============================================================================
# TOOL 3: GET FILE DETAILS
# ============================================================================


class GetFileDetailsTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """
    Get full file details/metadata from Google Drive.

    Consistent with other domains:
    - contacts: get_contact_details_tool
    - emails: get_email_details_tool
    - calendar: get_event_details_tool
    - tasks: get_task_details_tool
    - drive: get_file_details_tool (this tool)

    MULTI-ORDINAL FIX (2026-01-01): Supports batch mode for multi-reference queries.
    - Single mode: file_id="abc123" → fetch one file
    - Batch mode: file_ids=["abc123", "def456"] → fetch multiple files in parallel
    """

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    registry_enabled = True

    def __init__(self) -> None:
        super().__init__(tool_name="get_files_tool", operation="details")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute get file content API call.

        MULTI-ORDINAL FIX (2026-01-01): Routes to single or batch mode based on parameters.
        - If file_ids is provided (non-empty list) → batch mode
        - If file_id is provided → single mode
        - Both provided → batch mode takes precedence
        """
        file_id: str | None = kwargs.get("file_id")
        file_ids: list[str] | None = kwargs.get("file_ids")
        include_content: bool = kwargs.get("include_content", True)

        # Determine mode: batch takes precedence
        if file_ids and len(file_ids) > 0:
            return await self._execute_batch(client, user_id, file_ids, include_content)
        elif file_id:
            return await self._execute_single(client, user_id, file_id, include_content)
        else:
            raise ValueError("Either file_id or file_ids must be provided")

    async def _execute_single(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        file_id: str,
        include_content: bool,
    ) -> dict[str, Any]:
        """
        Execute single file details fetch.

        FOLDER HANDLING (2025-12-19):
        If the file is a folder (mimeType = application/vnd.google-apps.folder),
        instead of trying to download content (which would fail), we list the
        folder's contents. This provides a better UX when user asks for "details
        of the first" and that item happens to be a folder.
        """
        # Get file metadata
        metadata = await client.get_file_metadata(file_id)
        mime_type = metadata.get("mimeType", "")

        content = None
        folder_contents = None  # NEW: For folder handling

        # NEW: Handle folders specially - list their contents instead of downloading
        if mime_type == "application/vnd.google-apps.folder":
            logger.info(
                "get_file_content_folder_detected",
                user_id=str(user_id),
                file_id=file_id,
                folder_name=metadata.get("name"),
            )
            # List folder contents instead of trying to download
            folder_result = await client.list_files(
                folder_id=file_id,
                max_results=20,  # Reasonable limit for folder contents
            )
            folder_contents = folder_result.get("files", [])
        elif include_content:
            # For Google Docs, export as plain text
            if "google-apps" in mime_type:
                export_mime = "text/plain"
                if "spreadsheet" in mime_type:
                    export_mime = "text/csv"
                content = await client.export_google_doc(file_id, export_mime)
            else:
                # For regular files, get content
                content = await client.get_file_content(file_id)

        logger.info(
            "get_file_details_success",
            user_id=str(user_id),
            file_id=file_id,
            name=metadata.get("name"),
            has_content=content is not None,
            is_folder=folder_contents is not None,
            folder_items_count=len(folder_contents) if folder_contents else 0,
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "metadata": metadata,
            "content": content,
            "folder_contents": folder_contents,  # NEW: Folder contents if it's a folder
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "single",
        }

    async def _execute_batch(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        file_ids: list[str],
        include_content: bool,
    ) -> dict[str, Any]:
        """Execute batch file details fetch using asyncio.gather for parallelism.

        MULTI-ORDINAL FIX (2026-01-01): Added for multi-reference queries.
        Note: Folders in batch mode are skipped (content not fetched).
        """

        # Fetch all files in parallel
        async def fetch_single(fid: str) -> tuple[str, dict[str, Any] | None, str | None]:
            """Fetch single file, return (file_id, file_data, error)."""
            try:
                metadata = await client.get_file_metadata(fid)
                mime_type = metadata.get("mimeType", "")

                content = None
                # In batch mode, skip folder contents (too complex for batch)
                if mime_type != "application/vnd.google-apps.folder" and include_content:
                    if "google-apps" in mime_type:
                        export_mime = "text/plain"
                        if "spreadsheet" in mime_type:
                            export_mime = "text/csv"
                        content = await client.export_google_doc(fid, export_mime)
                    else:
                        content = await client.get_file_content(fid)

                # Merge content into metadata for consistent output
                full_payload = {**metadata}
                if content:
                    if isinstance(content, bytes):
                        try:
                            full_payload["content"] = content.decode("utf-8")[:10000]
                        except UnicodeDecodeError:
                            full_payload["content"] = "[Contenu binaire - non affichable]"
                            full_payload["content_type"] = "binary"
                    else:
                        full_payload["content"] = content[:10000]

                return (fid, full_payload, None)
            except Exception as e:
                logger.warning("get_file_details_batch_item_failed", file_id=fid, error=str(e))
                return (fid, None, str(e))

        results = await asyncio.gather(*[fetch_single(fid) for fid in file_ids])

        # Collect successful files and errors
        files: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for fid, file_data, error in results:
            if file_data:
                files.append(file_data)
            if error:
                errors.append({"file_id": fid, "error": error})

        logger.info(
            "get_file_details_batch_success",
            user_id=str(user_id),
            requested_count=len(file_ids),
            success_count=len(files),
            error_count=len(errors),
        )

        # Get user preferences for timezone conversion
        user_timezone, locale = await self.get_user_preferences_safe()

        return {
            "files": files,
            "file_ids": file_ids,
            "user_timezone": user_timezone,
            "locale": locale,
            "mode": "batch",
            "errors": errors if errors else None,
        }

    def format_response(self, result: dict[str, Any]) -> str:
        """Format using JSON (legacy mode)."""
        metadata = result.get("metadata", {})
        content = result.get("content")
        folder_contents = result.get("folder_contents")  # NEW

        # NEW: Handle folder response differently
        if folder_contents is not None:
            # It's a folder - show folder info + contents list
            formatted_files = []
            for f in folder_contents:
                formatted_files.append(
                    {
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "mime_type": f.get("mimeType"),
                        "size": f.get("size"),
                        "modified_time": f.get("modifiedTime"),
                    }
                )
            return json.dumps(
                {
                    "success": True,
                    "data": {
                        "folder": {
                            "id": metadata.get("id"),
                            "name": metadata.get("name"),
                            "mime_type": metadata.get("mimeType"),
                        },
                        "contents": formatted_files,
                        "total_items": len(formatted_files),
                    },
                },
                ensure_ascii=False,
            )

        # Handle bytes content for regular files
        content_str = None
        if content:
            if isinstance(content, bytes):
                try:
                    content_str = content.decode("utf-8")[:5000]
                except UnicodeDecodeError:
                    content_str = "[Contenu binaire - non affichable]"
            else:
                content_str = content[:5000] if len(content) > 5000 else content

        # Regular file response
        return json.dumps(
            {
                "success": True,
                "data": {
                    "file": {
                        "id": metadata.get("id"),
                        "name": metadata.get("name"),
                        "mime_type": metadata.get("mimeType"),
                        "size": metadata.get("size"),
                        "modified_time": metadata.get("modifiedTime"),
                        "content": content_str,
                    }
                },
            },
            ensure_ascii=False,
        )

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput.

        INTELLIA v10: Simplified - only builds registry_updates.
        Formatting is handled by response_node._simplify_file_payload() + fewshots.

        TIMEZONE: Dates are converted to user's timezone before storage.

        FOLDER HANDLING (2025-12-19):
        If folder_contents is present, we build a registry output that includes
        the folder metadata AND its contents as registry items.

        MULTI-ORDINAL FIX (2026-01-01): Handles both single and batch modes.
        - Single mode: One file in registry with full details
        - Batch mode: Multiple files in registry, errors in metadata

        Returns:
            UnifiedToolOutput with registry items for frontend rendering
        """
        mode = result.get("mode", "single")
        user_timezone = result.get("user_timezone", "UTC")
        locale = result.get("locale", settings.default_language)

        # Handle batch mode
        if mode == "batch":
            files = result.get("files", [])
            file_ids = result.get("file_ids", [])
            errors = result.get("errors")

            # Build output for all files
            # build_files_output returns UnifiedToolOutput directly
            output = self.build_files_output(
                files=files,
                from_cache=False,
                user_timezone=user_timezone,
                locale=locale,
            )

            # Build batch summary
            summary_lines = [f"File details retrieved: {len(files)} file(s)"]
            for i, f in enumerate(files[:5], 1):  # Limit to 5 for summary
                name = f.get("name", "Unknown")
                mime_type = f.get("mimeType", "")
                icon = "📁" if mime_type == "application/vnd.google-apps.folder" else "📄"
                summary_lines.append(f'{i}. {icon} "{name}"')
            if len(files) > 5:
                summary_lines.append(f"... and {len(files) - 5} more")

            output.message = "\n".join(summary_lines)

            # Add batch metadata
            output.metadata["file_ids"] = file_ids
            output.metadata["mode"] = "batch"
            if errors:
                output.metadata["errors"] = errors

            return output

        # Single mode
        metadata = result.get("metadata", {})
        content = result.get("content")
        folder_contents = result.get("folder_contents")
        file_id = metadata.get("id", "")

        if not file_id:
            return UnifiedToolOutput.failure(
                message="[details] File not found",
                error_code="NOT_FOUND",
                metadata={"tool_name": "get_file_details_tool"},
            )

        # Handle folder response - return folder info + list of contents
        if folder_contents is not None:
            folder_name = metadata.get("name", "Folder")

            # Build summary with folder info
            summary_lines = [f"📁 **Dossier: {folder_name}**"]
            if folder_contents:
                summary_lines.append(f"Contient {len(folder_contents)} éléments:")
                for idx, f in enumerate(folder_contents[:10], 1):  # Show first 10
                    icon = (
                        "📁" if f.get("mimeType") == "application/vnd.google-apps.folder" else "📄"
                    )
                    summary_lines.append(f"  {idx}. {icon} {f.get('name', 'Unknown')}")
                if len(folder_contents) > 10:
                    summary_lines.append(f"  ... et {len(folder_contents) - 10} autres éléments")
            else:
                summary_lines.append("Le dossier est vide.")

            # Build registry updates with folder contents
            # build_files_output returns UnifiedToolOutput directly
            output = self.build_files_output(
                files=folder_contents,
                folder_id=file_id,
                from_cache=False,
                user_timezone=user_timezone,
                locale=locale,
            )

            # Override message to be folder-specific
            output.message = "\n".join(summary_lines)

            # Add folder-specific metadata
            output.metadata["folder_id"] = file_id
            output.metadata["folder_name"] = folder_name
            output.metadata["is_folder"] = True
            output.metadata["contents_count"] = len(folder_contents)
            output.metadata["mode"] = "single"

            return output

        # Regular file: Merge content into metadata for _simplify_file_payload
        full_payload = {**metadata}
        if content:
            # Handle bytes content (from binary files like PDFs)
            # Convert to string if possible, otherwise indicate binary content
            if isinstance(content, bytes):
                try:
                    # Try to decode as UTF-8 text
                    content_str = content.decode("utf-8")[:10000]
                    full_payload["content"] = content_str
                except UnicodeDecodeError:
                    # Binary content (PDF, images, etc.) - not displayable as text
                    full_payload["content"] = "[Contenu binaire - non affichable]"
                    full_payload["content_type"] = "binary"
            else:
                full_payload["content"] = content[:10000]  # Limit content size

        # Wrap single file in list for build_files_output
        files = [full_payload]

        # Build output - build_files_output returns UnifiedToolOutput directly
        output = self.build_files_output(
            files=files,
            from_cache=False,
            user_timezone=user_timezone,
            locale=locale,
        )

        # Add file-specific metadata
        output.metadata["file_id"] = file_id
        output.metadata["has_content"] = content is not None
        output.metadata["is_folder"] = False
        output.metadata["mode"] = "single"

        return output


_get_file_details_tool_instance = GetFileDetailsTool()


@connector_tool(
    name="get_file_details",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="read",
)
async def get_file_details_tool(
    file_id: Annotated[str | None, "Google Drive file ID to retrieve (single mode)"] = None,
    file_ids: Annotated[
        list[str] | None,
        "List of Google Drive file IDs to retrieve (batch mode for multi-ordinal queries)",
    ] = None,
    include_content: Annotated[bool, "Include file content (default True)"] = True,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get full file details and metadata from Google Drive.

    Supports both single and batch modes:
    - Single: file_id="abc123" → fetch one file
    - Batch: file_ids=["abc123", "def456"] → fetch multiple files in parallel

    MULTI-ORDINAL FIX (2026-01-01): Added batch mode for multi-reference queries.
    Example: "detail du 1 et du 2" → file_ids=["id1", "id2"]

    Returns comprehensive file information including:
    - File metadata (name, size, mimeType, owners, etc.)
    - File content (for text-based files)
    - Folder contents (if file_id points to a folder, single mode only)

    Consistent with other domains:
    - contacts: get_contact_details_tool
    - emails: get_email_details_tool
    - calendar: get_event_details_tool
    - tasks: get_task_details_tool
    - drive: get_file_details_tool (this tool)

    Args:
        file_id: Google Drive file ID for single mode
        file_ids: List of Google Drive file IDs for batch mode
        include_content: Whether to include file content (default True)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with full file details including metadata and optionally content
    """
    return await _get_file_details_tool_instance.execute(
        runtime=runtime,
        file_id=file_id,
        file_ids=file_ids,
        include_content=include_content,
    )


# ============================================================================
# TOOL 4: DELETE FILE (with HITL confirmation)
# ============================================================================


class DeleteFileDraftTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """
    Delete file tool with Draft/HITL integration.

    Data Registry LOT 5.4: Destructive operations require explicit confirmation.
    """

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize delete file draft tool."""
        super().__init__(tool_name="delete_file_tool", operation="delete_draft")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare file deletion draft data.

        First fetches file metadata to show user what will be deleted.
        """
        file_id: str = require_field(kwargs, "file_id")

        # Fetch file metadata to show user what will be deleted
        metadata = await client.get_file_metadata(file_id)

        logger.info(
            "delete_file_draft_prepared",
            user_id=str(user_id),
            file_id=file_id,
            name=metadata.get("name"),
        )

        return {
            "file_id": file_id,
            "name": metadata.get("name"),
            "mime_type": metadata.get("mimeType"),
            "size": metadata.get("size"),
            "modified_time": metadata.get("modifiedTime"),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create file deletion draft via DraftService.

        Returns UnifiedToolOutput with HITL metadata (requires_confirmation=True).
        """
        from src.domains.agents.drafts import create_file_delete_draft

        # create_file_delete_draft returns UnifiedToolOutput directly
        return create_file_delete_draft(
            file_id=result["file_id"],
            file={
                "name": result.get("name"),
                "mime_type": result.get("mime_type"),
                "size": result.get("size"),
                "modified_time": result.get("modified_time"),
            },
            source_tool="delete_file_tool",
        )


# Direct delete tool for execute_fn callback
class DeleteFileDirectTool(ConnectorTool[GoogleDriveClient]):
    """Delete file that executes immediately (for HITL callback)."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient

    def __init__(self) -> None:
        super().__init__(tool_name="delete_file_direct_tool", operation="delete")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute delete file API call - business logic only."""
        file_id: str = kwargs["file_id"]

        await client.delete_file(file_id)

        logger.info(
            "file_deleted_via_tool",
            user_id=str(user_id),
            file_id=file_id,
        )

        return {
            "success": True,
            "file_id": file_id,
            "message": APIMessages.file_deleted_successfully(),
        }


_delete_file_draft_tool_instance = DeleteFileDraftTool()


@connector_tool(
    name="delete_file",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="write",
)
async def delete_file_tool(
    file_id: Annotated[str, "Google Drive file ID to delete (required)"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Delete a file from Google Drive (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The file is NOT deleted until the user confirms via HITL.

    This is a destructive operation that cannot be undone.
    Files are permanently deleted, not moved to trash.

    Args:
        file_id: Google Drive file ID to delete (required)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and HITL metadata (requires_confirmation=True)
    """
    return await _delete_file_draft_tool_instance.execute(
        runtime=runtime,
        file_id=file_id,
    )


# ============================================================================
# DRAFT EXECUTION HELPER (LOT 5.4)
# ============================================================================


async def execute_file_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a file delete draft: actually delete the file.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    connector_service = await deps.get_connector_service()
    credentials = await connector_service.get_connector_credentials(
        user_id, ConnectorType.GOOGLE_DRIVE
    )

    if not credentials:
        raise ConnectorNotEnabledError(
            APIMessages.connector_not_enabled("Google Drive"),
            connector_name="Google Drive",
        )

    client = GoogleDriveClient(user_id, credentials, connector_service)

    await client.delete_file(draft_content["file_id"])

    file_data = draft_content.get("file", {})
    name = file_data.get("name", "")

    logger.info(
        "file_delete_draft_executed",
        user_id=str(user_id),
        file_id=draft_content["file_id"],
        name=name,
    )

    return {
        "success": True,
        "file_id": draft_content["file_id"],
        "message": APIMessages.file_deleted_successfully(name),
    }


# ============================================================================
# UNIFIED TOOL: GET FILES (v2.0 - replaces search + list + details)
# ============================================================================


@connector_tool(
    name="get_files",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="read",
)
async def get_files_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    query: str | None = None,
    file_id: str | None = None,
    file_ids: list[str] | None = None,
    folder_id: str | None = None,
    max_results: int | None = None,
    include_content: bool = False,
    force_refresh: bool = False,
    content_type: Annotated[
        str,
        "Filter content type: 'files_only' (default), 'folders_only' (only folders/directories), 'all' (both)",
    ] = "files_only",
    mime_type: Annotated[
        str | None,
        "Filter by MIME type. Common values: 'application/pdf' (PDF), 'image/jpeg' (JPEG), "
        "'application/vnd.google-apps.document' (Google Docs), 'application/vnd.google-apps.spreadsheet' (Sheets)",
    ] = None,
    search_mode: Annotated[
        str,
        "Search scope: 'name_only' (default, matches file names) or 'full_text' (matches name + content)",
    ] = "name_only",
) -> UnifiedToolOutput:
    """
    Get Drive files with full details - unified search, list and retrieval.

    Architecture Simplification (2026-01):
    - Replaces search_files_tool + list_files_tool + get_file_details_tool
    - Always returns FULL file details (name, type, size, content)
    - Supports query mode (search) OR ID mode (direct fetch) OR list mode

    **Content Type Filtering:**
    - content_type="files_only" (default): Returns only files, excludes folders
    - content_type="folders_only": Returns only folders/directories
    - content_type="all": Returns both files and folders

    **MIME Type Filtering:**
    - mime_type="application/pdf": PDF files only
    - mime_type="image/jpeg" or "image/png": Images
    - mime_type="application/vnd.google-apps.document": Google Docs
    - mime_type="application/vnd.google-apps.spreadsheet": Google Sheets

    Modes:
    - Query mode: get_files_tool(query="report") → search + return full details
    - MIME filter: get_files_tool(mime_type="application/pdf") → all PDF files
    - ID mode: get_files_tool(file_id="abc123") → fetch specific file
    - Batch mode: get_files_tool(file_ids=["abc", "def"]) → fetch multiple
    - Folder mode: get_files_tool(folder_id="xyz") → list folder contents
    - List mode: get_files_tool() → return recent files

    Args:
        runtime: Runtime dependencies injected automatically.
        query: Search term - triggers search mode.
        file_id: Single file ID for direct fetch.
        file_ids: Multiple file IDs for batch fetch.
        folder_id: Folder ID to list contents.
        max_results: Maximum results (default 10, max 50).
        include_content: Include file content (default False).
        force_refresh: Bypass cache (default False).
        content_type: Filter by content type (files_only, folders_only, all).
        mime_type: Filter by MIME type (e.g., 'application/pdf' for PDFs).
        search_mode: Search scope - 'name_only' (default) or 'full_text'.

    Returns:
        UnifiedToolOutput with registry items containing file data.
    """
    # Route to appropriate implementation based on parameters
    if file_id or file_ids:
        # ID mode: direct fetch with full details (content_type N/A for specific IDs)
        return await _get_file_details_tool_instance.execute(
            runtime=runtime,
            file_id=file_id,
            file_ids=file_ids,
            include_content=include_content,
            force_refresh=force_refresh,
        )
    elif query or mime_type:
        # Query/MIME filter mode: search + full details
        return await _search_files_tool_instance.execute(
            runtime=runtime,
            query=query,
            mime_type=mime_type,
            max_results=max_results,
            force_refresh=force_refresh,
            content_type=content_type,
            search_mode=search_mode,
        )
    else:
        # List mode: return recent files or folder contents
        return await _list_files_tool_instance.execute(
            runtime=runtime,
            folder_id=folder_id,
            max_results=max_results,
            force_refresh=force_refresh,
            content_type=content_type,
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Unified tool (v2.0 - replaces search + list + details)
    "get_files_tool",
    # Tool classes
    "SearchFilesTool",
    "ListFilesTool",
    "GetFileDetailsTool",
    "DeleteFileDraftTool",
    "DeleteFileDirectTool",
    # Draft execution
    "execute_file_delete_draft",
]
