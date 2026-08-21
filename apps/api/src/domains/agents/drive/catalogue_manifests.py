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
            semantic_type="search_mode",
        ),
        # ID mode parameters
        ParameterSchema(
            name="file_id",
            type="string",
            required=False,
            description="Single file ID for direct fetch.",
            semantic_type="file_id",
        ),
        ParameterSchema(
            name="file_ids",
            type="array",
            required=False,
            description="Multiple file IDs for batch fetch.",
            semantic_type="file_id",
        ),
        # List mode parameter
        ParameterSchema(
            name="folder_id",
            type="string",
            required=False,
            description="Parent folder ID for list mode (def: root)",
            semantic_type="folder_id",
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
            semantic_type="content_type_filter",
        ),
        ParameterSchema(
            name="mime_type",
            type="string",
            required=False,
            description="Filter by MIME type: 'application/pdf' (PDF), 'image/jpeg', 'application/vnd.google-apps.document' (Docs), 'application/vnd.google-apps.spreadsheet' (Sheets)",
            semantic_type="file_mime_type",
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
        OutputFieldSchema(
            path="files[].size",
            type="string",
            description="File size",
            semantic_type="file_size",
        ),
        OutputFieldSchema(
            path="files[].modifiedTime",
            type="string",
            description="Last modified",
            semantic_type="datetime",
        ),
        OutputFieldSchema(path="files[].owners", type="string", description="Owner names"),
        OutputFieldSchema(
            path="files[].shared",
            type="boolean",
            description="Is shared",
            semantic_type="shared_status",
        ),
        OutputFieldSchema(
            path="files[].content",
            type="string",
            nullable=True,
            description="Text content",
            semantic_type="file_content",
        ),
        OutputFieldSchema(path="count", type="integer", description="Count"),
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
    reference_examples=["files[0].id", "files[0].name", "files[0].content", "count"],
    version="2.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📁", i18n_key="get_files", visible=True, category="tool"),
)


# ============================================================================
# SHEETS / DOCS CONTENT READ (lot F phase read, 2026-08 — Drive token)
# ============================================================================

read_spreadsheet_catalogue_manifest = ToolManifest(
    name="read_spreadsheet_tool",
    agent="file_agent",
    description=(
        "**Tool: read_spreadsheet_tool** - Read the CELL VALUES of a Google "
        "Sheets spreadsheet ('read this sheet and answer', budgets, lists, "
        "trackers). Chain from get_files_tool: pass files[].id as file_id. "
        "Returns the sheet list, one sheet's values (bounded page) and an "
        "explicit truncation flag. Use get_files_tool for file METADATA."
    ),
    semantic_keywords=[
        "read the values of my google sheet",
        "what does this spreadsheet contain",
        "answer from my budget tracking sheet",
        "look up a number in my spreadsheet",
    ],
    parameters=[
        ParameterSchema(
            name="file_id",
            type="string",
            required=True,
            description="Drive file id of the spreadsheet (from get_files_tool)",
            semantic_type="file_id",
        ),
        ParameterSchema(
            name="sheet_name",
            type="string",
            required=False,
            description="Sheet (tab) name; empty = first sheet. Case-insensitive.",
        ),
        ParameterSchema(
            name="max_rows",
            type="integer",
            required=False,
            description="Max rows to read (default 50)",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=200),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="title", type="string", description="Spreadsheet title"),
        OutputFieldSchema(path="sheet", type="string", description="Sheet actually read"),
        OutputFieldSchema(path="sheets", type="array", description="Available sheets"),
        OutputFieldSchema(path="values", type="array", description="Rows of cell values"),
        OutputFieldSchema(path="returned_rows", type="integer", description="Exact rows returned"),
        OutputFieldSchema(
            path="truncated", type="boolean", description="True when more rows may exist"
        ),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=600, est_cost_usd=0.002, est_latency_ms=700),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_DRIVE_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="files",
    reference_examples=["values[0]", "sheet", "returned_rows"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📊", i18n_key="read_spreadsheet", visible=True, category="tool"),
)

read_document_catalogue_manifest = ToolManifest(
    name="read_document_tool",
    agent="file_agent",
    description=(
        "**Tool: read_document_tool** - Read a Google Doc's CONTENT as "
        "structured text (headings, lists, tables). Chain from "
        "get_files_tool: pass files[].id as file_id. Use to answer about, "
        "summarize or compare a document's content."
    ),
    semantic_keywords=[
        "read the content of my google doc",
        "summarize this document from drive",
        "what does the meeting notes doc say",
        "compare information inside a document",
    ],
    parameters=[
        ParameterSchema(
            name="file_id",
            type="string",
            required=True,
            description="Drive file id of the Google Doc (from get_files_tool)",
            semantic_type="file_id",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="title", type="string", description="Document title"),
        OutputFieldSchema(path="content", type="string", description="Structured text content"),
        OutputFieldSchema(
            path="truncated", type="boolean", description="True when the content was cut"
        ),
    ],
    cost=CostProfile(est_tokens_in=80, est_tokens_out=800, est_cost_usd=0.003, est_latency_ms=700),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_DRIVE_SCOPES, hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="files",
    reference_examples=["title", "content"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📄", i18n_key="read_document", visible=True, category="tool"),
)

write_spreadsheet_catalogue_manifest = ToolManifest(
    name="write_spreadsheet_tool",
    agent="file_agent",
    description=(
        "**Tool: write_spreadsheet_tool** - WRITE into a Google Sheets "
        "spreadsheet ('add this expense to my budget sheet'). mode='append' "
        "adds rows below the table (default); mode='update' overwrites the "
        "cells of a1_range. Chain from get_files_tool (files[].id as "
        "file_id). Returns a confirmation draft: nothing is written until "
        "the user approves the exact rows/cells shown."
    ),
    semantic_keywords=[
        "add a row to my google sheet",
        "write this expense into my budget spreadsheet",
        "update a cell in my tracking sheet",
        "record these values in the spreadsheet",
    ],
    parameters=[
        ParameterSchema(
            name="file_id",
            type="string",
            required=True,
            description="Drive file id of the spreadsheet (from get_files_tool)",
            semantic_type="file_id",
        ),
        ParameterSchema(
            name="values",
            type="array",
            required=True,
            description="Row-major cell values, e.g. [['Loyer','1200']]. Max 50 rows.",
        ),
        ParameterSchema(
            name="mode",
            type="string",
            required=False,
            description="'append' (default) or 'update'",
            constraints=[ParameterConstraint(kind="enum", value=["append", "update"])],
        ),
        ParameterSchema(
            name="a1_range",
            type="string",
            required=False,
            description="Target range WITHOUT sheet prefix, e.g. 'B2:B3' (update mode)",
        ),
        ParameterSchema(
            name="sheet_name",
            type="string",
            required=False,
            description="Sheet (tab) name; empty = first sheet. Case-insensitive.",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=80, est_cost_usd=0.005, est_latency_ms=700),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_DRIVE_SCOPES,
        # Draft-based: HITL is handled by draft_critique (preview before
        # writing), like send_email. hitl_required MUST stay False — the flag
        # only drives ReAct's pre-execution interrupt, redundant for drafts.
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["success"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📊", i18n_key="write_spreadsheet", visible=True, category="tool"
    ),
)

append_document_text_catalogue_manifest = ToolManifest(
    name="append_document_text_tool",
    agent="file_agent",
    description=(
        "**Tool: append_document_text_tool** - APPEND text at the end of a "
        "Google Doc ('add this note to my meeting doc'). Chain from "
        "get_files_tool (files[].id as file_id). Returns a confirmation "
        "draft: nothing is written until the user approves the full text."
    ),
    semantic_keywords=[
        "add a note to my google doc",
        "append this text to the meeting document",
        "write a paragraph into my doc",
    ],
    parameters=[
        ParameterSchema(
            name="file_id",
            type="string",
            required=True,
            description="Drive file id of the Google Doc (from get_files_tool)",
            semantic_type="file_id",
        ),
        ParameterSchema(
            name="text",
            type="string",
            required=True,
            description="Text appended verbatim at the end of the document",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=60, est_cost_usd=0.004, est_latency_ms=700),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_DRIVE_SCOPES,
        # Draft-based (see write_spreadsheet_tool above).
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_examples=["success"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📝", i18n_key="append_document_text", visible=True, category="tool"
    ),
)


# Registration collection for the catalogue loader (lot F family)
WORKSPACE_DOCS_TOOL_MANIFESTS: tuple[ToolManifest, ...] = (
    read_spreadsheet_catalogue_manifest,
    read_document_catalogue_manifest,
    write_spreadsheet_catalogue_manifest,
    append_document_text_catalogue_manifest,
)

__all__ = [
    # Unified tool (v2.0 - replaces search + list + details)
    "get_files_catalogue_manifest",
    # Sheets/Docs content read (lot F)
    "read_spreadsheet_catalogue_manifest",
    "read_document_catalogue_manifest",
    "write_spreadsheet_catalogue_manifest",
    "append_document_text_catalogue_manifest",
    "WORKSPACE_DOCS_TOOL_MANIFESTS",
]
