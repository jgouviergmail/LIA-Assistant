"""
Catalogue manifests for Google Drive tools.
Optimized for orchestration efficiency.

Architecture Simplification (2026-01):
- get_files_tool replaces search_files_tool + list_files_tool + get_file_details_tool
- Always returns full file content (metadata, content text)
- Supports query mode (search) OR ID mode (direct fetch) OR list mode (browse)
"""

from src.core.config import settings
from src.core.constants import (
    DRIVE_TOOL_DEFAULT_LIMIT,
    GOOGLE_DRIVE_SCOPES,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# 1. GET FILES (Unified - replaces search + list + details)
# ============================================================================
_get_files_desc = (
    "**Tool: get_files_tool** - Get Drive files with full details.\n"
    "\n"
    "**MODES**:\n"
    "- Query mode: get_files_tool(query='report') → search by file name (default)\n"
    "- MIME filter: get_files_tool(mime_type='application/pdf') → all PDF files\n"
    "- ID mode: get_files_tool(file_id='abc123') → fetch specific file\n"
    "- Batch mode: get_files_tool(file_ids=['abc', 'def']) → fetch multiple files\n"
    "- List mode: get_files_tool(folder_id='root') → list files in folder with full details\n"
    "\n"
    "**QUERY PARAMETER**: Plain text search term (auto-converted to Drive API syntax).\n"
    "**search_mode**: 'name_only' (default, matches file names) or 'full_text' (matches name + content).\n"
    "\n"
    "**content_type**: 'files_only' (default), 'folders_only', or 'all'\n"
    "**RETURNS**: Full file info (name, size, owners, content text, etc.)."
)

get_files_catalogue_manifest = ToolManifest(
    name="get_files_tool",
    agent="file_agent",
    description=_get_files_desc,
    # Discriminant phrases - Cloud storage file operations
    semantic_keywords=[
        # File search in cloud storage
        "find document in my Google Drive",
        "search files stored in cloud drive",
        "locate spreadsheet in my Drive folder",
        "where is my file in cloud storage",
        # File type filtering (MIME type)
        "show my PDF files in Drive",
        "list all PDF documents",
        "find images in my Google Drive",
        "show spreadsheet files",
        "get my Google Docs documents",
        # File listing and browsing
        "show all files in my Drive folder",
        "list documents in cloud storage",
        "browse files in Google Drive directory",
        "what files do I have in Drive",
        # File content and details
        "read document content from Drive",
        "get file text from cloud storage",
        "show file details and metadata from Drive",
        "download document content from Google Drive",
        # Folder navigation
        "list folders in my Google Drive",
        "browse directory structure in cloud",
        "show shared files in Drive",
    ],
    parameters=[
        # Query mode parameter
        ParameterSchema(
            name="query",
            type="string",
            required=False,
            description="Plain text search term (e.g. 'contract'). Optional for list mode.",
        ),
        ParameterSchema(
            name="search_mode",
            type="string",
            required=False,
            description="'name_only' (default): match file names. 'full_text': match name + file content.",
        ),
        # ID mode parameters
        ParameterSchema(
            name="file_id",
            type="string",
            required=False,
            description="Single file ID for direct fetch.",
        ),
        ParameterSchema(
            name="file_ids",
            type="array",
            required=False,
            description="Multiple file IDs for batch fetch.",
        ),
        # List mode parameter
        ParameterSchema(
            name="folder_id",
            type="string",
            required=False,
            description="Parent folder ID for list mode (def: root)",
        ),
        # Common options
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max files (def: {DRIVE_TOOL_DEFAULT_LIMIT}, max: {settings.drive_tool_default_max_results})",
            constraints=[
                ParameterConstraint(kind="maximum", value=settings.drive_tool_default_max_results)
            ],
        ),
        ParameterSchema(
            name="content_type",
            type="string",
            required=False,
            description="'files_only' (default), 'folders_only', or 'all'",
        ),
        ParameterSchema(
            name="mime_type",
            type="string",
            required=False,
            description="Filter by MIME type: 'application/pdf' (PDF), 'image/jpeg', 'application/vnd.google-apps.document' (Docs), 'application/vnd.google-apps.spreadsheet' (Sheets)",
        ),
        ParameterSchema(
            name="include_content",
            type="boolean",
            required=False,
            description="Also return file content text (def: True)",
        ),
    ],
    outputs=[
        # Full file outputs (merged from all tools)
        OutputFieldSchema(
            path="files", type="array", description="List of files with full details"
        ),
        OutputFieldSchema(
            path="files[].id", type="string", description="File ID", semantic_type="file_id"
        ),
        OutputFieldSchema(path="files[].name", type="string", description="File name"),
        OutputFieldSchema(
            path="files[].mimeType",
            type="string",
            description="MIME type",
            semantic_type="file_mime_type",
        ),
        OutputFieldSchema(path="files[].size", type="string", description="File size"),
        OutputFieldSchema(
            path="files[].modifiedTime",
            type="string",
            description="Last modified",
            semantic_type="datetime",
        ),
        OutputFieldSchema(path="files[].owners", type="string", description="Owner names"),
        OutputFieldSchema(path="files[].shared", type="boolean", description="Is shared"),
        OutputFieldSchema(
            path="files[].content", type="string", nullable=True, description="Text content"
        ),
        OutputFieldSchema(path="total", type="integer", description="Count"),
    ],
    cost=CostProfile(
        est_tokens_in=150, est_tokens_out=1000, est_cost_usd=0.003, est_latency_ms=700
    ),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_DRIVE_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    max_iterations=1,
    supports_dry_run=False,
    context_key="files",
    reference_examples=["files[0].id", "files[0].name", "files[0].content", "total"],
    version="2.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📁", i18n_key="get_files", visible=True, category="tool"),
)


__all__ = [
    # Unified tool (v2.0 - replaces search + list + details)
    "get_files_catalogue_manifest",
]
