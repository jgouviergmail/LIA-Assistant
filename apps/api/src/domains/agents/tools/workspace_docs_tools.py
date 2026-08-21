"""Google Sheets/Docs content tools (lot F, 2026-08).

"Read this spreadsheet and answer" / "summarize this doc": until now
drive_tools handled FILES (search, list, export) but never their live
content. These tools ride the existing GOOGLE_DRIVE connector token (the
Sheets/Docs APIs accept the granted ``auth/drive`` scope — no re-consent).

Phase write (lot F completion): range update / row append on Sheets and
text append on Docs, both behind the full HITL draft flow — the preview
shows exactly what will be written, nothing touches the file before the
user confirms.

Count doctrine: a sheet's grid rowCount is a CAPACITY (default grids are
1000 rows), not a data count — the tools state how many rows they returned
and whether the read was truncated, never a derived total.
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import (
    SHEETS_READ_DEFAULT_MAX_ROWS,
    SHEETS_READ_MAX_COLUMN,
    SHEETS_READ_MAX_ROWS,
    SHEETS_WRITE_MAX_ROWS,
    WORKSPACE_DOC_APPEND_MAX_CHARS,
    WORKSPACE_DOC_READ_MAX_CHARS,
)
from src.domains.agents.constants import AGENT_FILE, CONTEXT_DOMAIN_FILES
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_docs_client import (
    GoogleDocsClient,
    docs_structure_to_text,
)
from src.domains.connectors.clients.google_sheets_client import GoogleSheetsClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


def _escape_sheet_title(title: str) -> str:
    """A1 notation doubles single quotes inside a quoted sheet name."""
    return title.replace("'", "''")


def _sheet_summaries(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-sheet titles and EXACT grid sizes from spreadsheet metadata."""
    summaries = []
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties") or {}
        grid = properties.get("gridProperties") or {}
        summaries.append(
            {
                "title": properties.get("title", ""),
                "grid_rows": grid.get("rowCount", 0),
                "grid_columns": grid.get("columnCount", 0),
            }
        )
    return summaries


def _select_sheet(sheets: list[dict[str, Any]], sheet_name: str) -> dict[str, Any] | None:
    """Requested sheet (case-insensitive) or the first one; None when absent."""
    if not sheet_name:
        return sheets[0] if sheets else None
    wanted = sheet_name.casefold()
    return next((sheet for sheet in sheets if sheet["title"].casefold() == wanted), None)


class ReadSpreadsheetTool(ToolOutputMixin, ConnectorTool[GoogleSheetsClient]):
    """Read the values of one sheet of a Google Sheets spreadsheet."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleSheetsClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize read spreadsheet tool."""
        super().__init__(tool_name="read_spreadsheet_tool", operation="read")

    async def execute_api_call(
        self,
        client: GoogleSheetsClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Resolve the sheet, read a bounded page of values."""
        file_id: str = str(kwargs.get("file_id") or "").strip()
        sheet_name: str = str(kwargs.get("sheet_name") or "").strip()
        max_rows = max(
            1,
            min(int(kwargs.get("max_rows") or SHEETS_READ_DEFAULT_MAX_ROWS), SHEETS_READ_MAX_ROWS),
        )

        metadata = await client.get_spreadsheet(file_id)
        sheets = _sheet_summaries(metadata)
        target = _select_sheet(sheets, sheet_name)
        if target is None:
            return {
                "success": False,
                "error": "sheet_not_found",
                "available_sheets": [sheet["title"] for sheet in sheets],
            }

        # An unescaped quote in the sheet name makes the API 400.
        a1_range = f"'{_escape_sheet_title(target['title'])}'!A1:{SHEETS_READ_MAX_COLUMN}{max_rows}"
        values_response = await client.get_values(file_id, a1_range)
        values = values_response.get("values", [])

        logger.info(
            "spreadsheet_read",
            user_id=str(user_id),
            returned_rows=len(values),
        )
        return {
            "success": True,
            "title": (metadata.get("properties") or {}).get("title", ""),
            "sheets": sheets,
            "sheet": target["title"],
            "values": values,
            "returned_rows": len(values),
            # A full page may hide more rows below — stated, never silent.
            "truncated": len(values) >= max_rows,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Structured data only (rendered by the response LLM)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Spreadsheet read failed"),
                error_code=result.get("error"),
                metadata={"available_sheets": result.get("available_sheets", [])},
            )
        return UnifiedToolOutput.data_success(
            message=(
                f"{result['returned_rows']} rows from sheet '{result['sheet']}'"
                + (" (truncated)" if result["truncated"] else "")
            ),
            structured_data={
                key: result[key]
                for key in ("title", "sheets", "sheet", "values", "returned_rows", "truncated")
            },
        )


class ReadDocumentTool(ToolOutputMixin, ConnectorTool[GoogleDocsClient]):
    """Read a Google Doc's content as compact structured text."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDocsClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize read document tool."""
        super().__init__(tool_name="read_document_tool", operation="read")

    async def execute_api_call(
        self,
        client: GoogleDocsClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Fetch the document and extract its structural text."""
        file_id: str = str(kwargs.get("file_id") or "").strip()
        document = await client.get_document(file_id)
        content = docs_structure_to_text(document)
        truncated = len(content) > WORKSPACE_DOC_READ_MAX_CHARS
        if truncated:
            content = content[:WORKSPACE_DOC_READ_MAX_CHARS]

        logger.info("document_read", user_id=str(user_id), chars=len(content))
        return {
            "success": True,
            "title": document.get("title", ""),
            "content": content,
            "truncated": truncated,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Structured data only (rendered by the response LLM)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Document read failed"),
                error_code=result.get("error"),
            )
        return UnifiedToolOutput.data_success(
            message=(
                f"Document '{result['title']}' read"
                + (" (truncated)" if result["truncated"] else "")
            ),
            structured_data={key: result[key] for key in ("title", "content", "truncated")},
        )


_read_spreadsheet_instance = ReadSpreadsheetTool()
_read_document_instance = ReadDocumentTool()


@connector_tool(
    name="read_spreadsheet",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="read",
)
async def read_spreadsheet_tool(
    file_id: Annotated[str, "Drive file id of the spreadsheet (from get_files_tool)"],
    sheet_name: Annotated[
        str, "Sheet (tab) name; empty = the first sheet. Matched case-insensitively."
    ] = "",
    max_rows: Annotated[
        int, f"Max rows to read (1-{SHEETS_READ_MAX_ROWS}, default {SHEETS_READ_DEFAULT_MAX_ROWS})"
    ] = SHEETS_READ_DEFAULT_MAX_ROWS,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Read the cell values of a Google Sheets spreadsheet ("read this sheet and answer").

    Returns the sheet list (with exact grid sizes), the requested sheet's
    values (bounded page) and an explicit truncation flag.

    Returns:
        UnifiedToolOutput with the spreadsheet content.
    """
    return await _read_spreadsheet_instance.execute(
        runtime=runtime, file_id=file_id, sheet_name=sheet_name, max_rows=max_rows
    )


@connector_tool(
    name="read_document",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="read",
)
async def read_document_tool(
    file_id: Annotated[str, "Drive file id of the Google Doc (from get_files_tool)"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Read a Google Doc's content as structured text (headings, lists, tables).

    Use to answer about a document's content, summarize it, or compare it
    with other data. Long documents are truncated with an explicit flag.

    Returns:
        UnifiedToolOutput with the document title and markdown-ish content.
    """
    return await _read_document_instance.execute(runtime=runtime, file_id=file_id)


# ============================================================================
# WRITE (lot F phase write — HITL drafts)
# ============================================================================


class SpreadsheetWriteDraftInput(BaseModel):
    """Content of a SPREADSHEET_WRITE draft (persisted until confirmation)."""

    model_config = ConfigDict(frozen=True)

    file_id: str = Field(description="Drive file id of the spreadsheet")
    spreadsheet_title: str = Field(default="", description="Spreadsheet title (preview)")
    sheet_name: str = Field(description="Exact sheet (tab) title")
    mode: str = Field(description="append (rows below the table) or update (a range)")
    a1_range: str = Field(default="", description="Target A1 range (update mode)")
    values: list[list[str]] = Field(description="Row-major cell values to write")
    user_language: str = Field(default="fr", description="User language for messages")


class DocumentAppendDraftInput(BaseModel):
    """Content of a DOCUMENT_APPEND draft (persisted until confirmation)."""

    model_config = ConfigDict(frozen=True)

    file_id: str = Field(description="Drive file id of the document")
    document_title: str = Field(default="", description="Document title (preview)")
    text: str = Field(description="Text appended verbatim at the end of the body")
    user_language: str = Field(default="fr", description="User language for messages")


class WriteSpreadsheetTool(ToolOutputMixin, ConnectorTool[GoogleSheetsClient]):
    """Write into a spreadsheet (append rows or update a range) via HITL draft."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleSheetsClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize write spreadsheet tool."""
        super().__init__(tool_name="write_spreadsheet_tool", operation="write")

    @staticmethod
    def _validate_write_request(
        mode: str, a1_range: str, raw_values: Any
    ) -> tuple[list[list[str]] | None, str | None]:
        """(normalized values, None) or (None, error code).

        Unrepairable inputs stay real errors the LLM must resolve; the row
        cap is a bound the manifest publishes, so exceeding it is a claim
        mismatch, not something to silently truncate (data would be lost).
        """
        if mode not in ("append", "update"):
            return None, "invalid_mode"
        if mode == "update" and not a1_range:
            return None, "range_required_for_update"
        values = [
            [str(cell) for cell in row] for row in (raw_values or []) if isinstance(row, list)
        ]
        if not values:
            return None, "values_required"
        if len(values) > SHEETS_WRITE_MAX_ROWS:
            return None, "too_many_rows"
        return values, None

    async def execute_api_call(
        self,
        client: GoogleSheetsClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Validate the request against the real spreadsheet, prepare the draft."""
        file_id: str = str(kwargs.get("file_id") or "").strip()
        sheet_name: str = str(kwargs.get("sheet_name") or "").strip()
        mode: str = str(kwargs.get("mode") or "append").strip().lower()
        a1_range: str = str(kwargs.get("a1_range") or "").strip()

        values, error = self._validate_write_request(mode, a1_range, kwargs.get("values"))
        if error is not None or values is None:
            return {"success": False, "error": error}

        metadata = await client.get_spreadsheet(file_id)
        sheets = _sheet_summaries(metadata)
        target = _select_sheet(sheets, sheet_name)
        if target is None:
            return {
                "success": False,
                "error": "sheet_not_found",
                "available_sheets": [sheet["title"] for sheet in sheets],
            }

        return {
            "success": True,
            "file_id": file_id,
            "spreadsheet_title": (metadata.get("properties") or {}).get("title", ""),
            "sheet_name": target["title"],
            "mode": mode,
            "a1_range": a1_range,
            "values": values,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create the SPREADSHEET_WRITE draft (requires confirmation)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=str(result.get("error", "spreadsheet write failed")).replace("_", " "),
                error_code=result.get("error"),
                metadata={"available_sheets": result.get("available_sheets", [])},
            )
        draft_input = SpreadsheetWriteDraftInput(
            file_id=result["file_id"],
            spreadsheet_title=result["spreadsheet_title"],
            sheet_name=result["sheet_name"],
            mode=result["mode"],
            a1_range=result["a1_range"],
            values=result["values"],
            user_language=self.get_user_language(),
        )
        return DraftService().create_draft(
            draft_type=DraftType.SPREADSHEET_WRITE,
            content=draft_input.model_dump(),
            related_registry_ids=[],
            source_tool="write_spreadsheet_tool",
            user_language=draft_input.user_language,
        )


class AppendDocumentTextTool(ToolOutputMixin, ConnectorTool[GoogleDocsClient]):
    """Append text to a Google Doc via HITL draft."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDocsClient
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize append document text tool."""
        super().__init__(tool_name="append_document_text_tool", operation="write")

    async def execute_api_call(
        self,
        client: GoogleDocsClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Validate the request against the real document, prepare the draft."""
        file_id: str = str(kwargs.get("file_id") or "").strip()
        text: str = str(kwargs.get("text") or "").strip()
        if not text:
            return {"success": False, "error": "text_required"}
        if len(text) > WORKSPACE_DOC_APPEND_MAX_CHARS:
            return {"success": False, "error": "text_too_long"}

        document = await client.get_document(file_id)
        return {
            "success": True,
            "file_id": file_id,
            "document_title": document.get("title", ""),
            "text": text,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create the DOCUMENT_APPEND draft (requires confirmation)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=str(result.get("error", "document append failed")).replace("_", " "),
                error_code=result.get("error"),
            )
        draft_input = DocumentAppendDraftInput(
            file_id=result["file_id"],
            document_title=result["document_title"],
            text=result["text"],
            user_language=self.get_user_language(),
        )
        return DraftService().create_draft(
            draft_type=DraftType.DOCUMENT_APPEND,
            content=draft_input.model_dump(),
            related_registry_ids=[],
            source_tool="append_document_text_tool",
            user_language=draft_input.user_language,
        )


_write_spreadsheet_instance = WriteSpreadsheetTool()
_append_document_text_instance = AppendDocumentTextTool()


@connector_tool(
    name="write_spreadsheet",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="write",
)
async def write_spreadsheet_tool(
    file_id: Annotated[str, "Drive file id of the spreadsheet (from get_files_tool)"],
    values: Annotated[
        list[list[str]],
        "Row-major cell values to write, e.g. [['Loyer', '1200'], ['EDF', '80']].",
    ],
    mode: Annotated[
        str,
        "'append' adds the rows below the sheet's table (default); "
        "'update' overwrites the cells of a1_range.",
    ] = "append",
    a1_range: Annotated[
        str, "Target range WITHOUT the sheet prefix, e.g. 'B2:B3' (update mode only)."
    ] = "",
    sheet_name: Annotated[
        str, "Sheet (tab) name; empty = the first sheet. Matched case-insensitively."
    ] = "",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Write into a Google Sheets spreadsheet ("add this expense to my budget sheet").

    Returns a confirmation draft showing exactly the rows/cells to be
    written — nothing is written until the user approves.

    Returns:
        UnifiedToolOutput carrying the draft (requires_confirmation=True).
    """
    return await _write_spreadsheet_instance.execute(
        runtime=runtime,
        file_id=file_id,
        values=values,
        mode=mode,
        a1_range=a1_range,
        sheet_name=sheet_name,
    )


@connector_tool(
    name="append_document_text",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="write",
)
async def append_document_text_tool(
    file_id: Annotated[str, "Drive file id of the Google Doc (from get_files_tool)"],
    text: Annotated[str, "Text appended verbatim at the end of the document."],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Append text at the end of a Google Doc ("add this note to my meeting doc").

    Returns a confirmation draft showing the full text — nothing is written
    until the user approves.

    Returns:
        UnifiedToolOutput carrying the draft (requires_confirmation=True).
    """
    return await _append_document_text_instance.execute(runtime=runtime, file_id=file_id, text=text)


# ============================================================================
# DRAFT EXECUTORS (invoked on user confirmation)
# ============================================================================


async def _drive_credentials(user_id: UUID, deps: Any) -> tuple[Any, Any] | None:
    """(credentials, connector_service) for the Drive token, or None."""
    connector_service = await deps.get_connector_service()
    credentials = await connector_service.get_connector_credentials(
        user_id, ConnectorType.GOOGLE_DRIVE
    )
    if credentials is None:
        return None
    return credentials, connector_service


async def execute_spreadsheet_write_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a confirmed SPREADSHEET_WRITE draft: perform the write.

    Registered in ``draft_executor_registry.ensure_executors_registered()``.

    Args:
        draft_content: SpreadsheetWriteDraftInput content.
        user_id: Draft owner.
        deps: ToolDependencies (Drive credentials come through it).

    Returns:
        {"success", "mode", "updated_rows"/"updated_cells"} on write.
    """
    resolved = await _drive_credentials(user_id, deps)
    if resolved is None:
        return {"success": False, "error": "connector_not_activated"}
    credentials, connector_service = resolved
    client = GoogleSheetsClient(user_id, credentials, connector_service)

    sheet_prefix = f"'{_escape_sheet_title(draft_content.get('sheet_name', ''))}'"
    values = draft_content.get("values") or []
    if draft_content.get("mode") == "update":
        response = await client.update_values(
            draft_content["file_id"],
            f"{sheet_prefix}!{draft_content.get('a1_range', '')}",
            values,
        )
        result = {
            "success": True,
            "mode": "update",
            "updated_cells": response.get("updatedCells", 0),
        }
    else:
        response = await client.append_values(
            draft_content["file_id"], f"{sheet_prefix}!A1", values
        )
        result = {
            "success": True,
            "mode": "append",
            "updated_rows": (response.get("updates") or {}).get("updatedRows", 0),
        }

    logger.info(
        "spreadsheet_write_draft_executed",
        user_id=str(user_id),
        mode=result["mode"],
    )
    return result


async def execute_document_append_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a confirmed DOCUMENT_APPEND draft: append the text.

    Registered in ``draft_executor_registry.ensure_executors_registered()``.

    Args:
        draft_content: DocumentAppendDraftInput content.
        user_id: Draft owner.
        deps: ToolDependencies (Drive credentials come through it).

    Returns:
        {"success": True} on write; typed failure otherwise.
    """
    resolved = await _drive_credentials(user_id, deps)
    if resolved is None:
        return {"success": False, "error": "connector_not_activated"}
    credentials, connector_service = resolved
    client = GoogleDocsClient(user_id, credentials, connector_service)
    await client.append_text(draft_content["file_id"], draft_content.get("text", ""))

    logger.info("document_append_draft_executed", user_id=str(user_id))
    return {"success": True}
