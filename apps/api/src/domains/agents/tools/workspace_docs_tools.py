"""Spreadsheet and document content tools (lot F, 2026-08; ADR-369, lot 11).

"Read this spreadsheet and answer" / "summarize this doc": drive_tools handles
FILES (search, list, export), these tools their live content. They serve the
account's drive (``functional_category``): Google Sheets and Docs on the Drive
token (the Sheets/Docs APIs accept the granted ``auth/drive`` scope — no
re-consent), Excel and Word files on OneDrive. ``workspace_content`` is the one
door, and what a drive cannot do it refuses before any card.

Phase write (lot F completion): range update / row append on a spreadsheet and
text append on a document, both behind the full HITL draft flow — the preview
shows exactly what will be written, nothing touches the file before the
user confirms.

Count doctrine: a sheet's grid rowCount is a CAPACITY (default grids are
1000 rows), not a data count — the tools state how many rows they returned
and whether the read was truncated, never a derived total.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Final
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import (
    SHEETS_READ_DEFAULT_MAX_ROWS,
    SHEETS_READ_MAX_ROWS,
    SHEETS_WRITE_MAX_ROWS,
    WORKSPACE_DOC_APPEND_MAX_CHARS,
    WORKSPACE_DOC_READ_MAX_CHARS,
)
from src.core.field_names import FIELD_ERROR, FIELD_ERROR_CODE, FIELD_SUCCESS
from src.core.i18n import resolve_language
from src.domains.agents.constants import AGENT_FILE, CONTEXT_DOMAIN_FILES
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import connector_not_activated_refusal
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.clients.office_files import OfficeContentRefusedError, OfficeRefusal
from src.domains.connectors.clients.workspace_content import documents_of, spreadsheets_of
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

_FILES: Final = "files"
#: The drives a confirmed act writes to, one active at most.
_DRIVES: Final = {
    ConnectorType.GOOGLE_DRIVE: GoogleDriveClient,
    ConnectorType.MICROSOFT_ONEDRIVE: MicrosoftOneDriveClient,
}
#: What a confirmation card reads when a file refuses the write (``i18n_draft_refusals``).
FILE_CHANGED: Final = "FILE_CHANGED"
FILE_LOCKED: Final = "FILE_LOCKED"
FILE_REFUSED: Final = "FILE_REFUSED"
#: What a refusal tells the model (ADR-256: technical English).
_REFUSAL_MESSAGES: Final[dict[OfficeRefusal, str]] = {
    OfficeRefusal.NOT_THIS_FORMAT: (
        "This drive reads .xlsx and .xlsm workbooks and .docx documents, and this file is "
        "neither: nothing was read."
    ),
    OfficeRefusal.TOO_LARGE: "The file is larger than what can be read here: nothing was read.",
    OfficeRefusal.UNREADABLE: (
        "The file could not be read: it is damaged, protected, or not what its name says."
    ),
    OfficeRefusal.WRITES_NOT_HELD: (
        "A personal OneDrive holds no workbook API: this spreadsheet can be read here, not "
        "written. Nothing was changed."
    ),
    OfficeRefusal.RANGE_REFUSED: (
        "The range must be a plain A1 cell or rectangle that holds the values: nothing was changed."
    ),
    OfficeRefusal.CHANGED: "The file changed meanwhile: nothing was written.",
    OfficeRefusal.LOCKED: "The file is locked by someone: nothing was written.",
}
# Raised, not asserted, so the guard survives -O (ADR-085 pattern).
if set(_REFUSAL_MESSAGES) != set(OfficeRefusal):
    raise RuntimeError("Every OfficeRefusal must say what it tells the model")


def _office_refusal(refusal: OfficeRefusal) -> dict[str, Any]:
    """What a tool answers for a file it cannot read or prepare."""
    return {
        "success": False,
        "error": refusal.value,
        "message": _REFUSAL_MESSAGES[refusal],
    }


def _sheet_summaries(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-sheet titles and grid sizes; a size the file does not declare stays unsaid."""
    summaries = []
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties") or {}
        grid = properties.get("gridProperties") or {}
        summaries.append(
            {
                "title": properties.get("title", ""),
                "grid_rows": grid.get("rowCount"),
                "grid_columns": grid.get("columnCount"),
            }
        )
    return summaries


def _select_sheet(sheets: list[dict[str, Any]], sheet_name: str) -> dict[str, Any] | None:
    """Requested sheet (case-insensitive) or the first one; None when absent."""
    if not sheet_name:
        return sheets[0] if sheets else None
    wanted = sheet_name.casefold()
    return next((sheet for sheet in sheets if sheet["title"].casefold() == wanted), None)


class ReadSpreadsheetTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """Read the values of one sheet of a spreadsheet of the account's drive."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    functional_category = _FILES
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize read spreadsheet tool."""
        super().__init__(tool_name="read_spreadsheet_tool", operation="read")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
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

        try:
            async with spreadsheets_of(client, user_id) as spreadsheets:
                metadata = await spreadsheets.get_spreadsheet(file_id)
                sheets = _sheet_summaries(metadata)
                target = _select_sheet(sheets, sheet_name)
                if target is None:
                    return {
                        "success": False,
                        "error": "sheet_not_found",
                        "available_sheets": [sheet["title"] for sheet in sheets],
                    }
                values = await spreadsheets.read_rows(file_id, target["title"], max_rows)
        except OfficeContentRefusedError as refused:
            return _office_refusal(refused.refusal)

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


class ReadDocumentTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """Read a document of the account's drive as compact structured text."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    functional_category = _FILES
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize read document tool."""
        super().__init__(tool_name="read_document_tool", operation="read")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Fetch the document and extract its structural text."""
        file_id: str = str(kwargs.get("file_id") or "").strip()
        try:
            async with documents_of(client, user_id) as documents:
                document = await documents.read_text(file_id)
        except OfficeContentRefusedError as refused:
            return _office_refusal(refused.refusal)
        content = document["content"]
        truncated = len(content) > WORKSPACE_DOC_READ_MAX_CHARS
        if truncated:
            content = content[:WORKSPACE_DOC_READ_MAX_CHARS]

        logger.info("document_read", user_id=str(user_id), chars=len(content))
        return {
            "success": True,
            "title": document["title"],
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
    file_id: Annotated[str, "File id of the spreadsheet (from get_files_tool)"],
    sheet_name: Annotated[
        str, "Sheet (tab) name; empty = the first sheet. Matched case-insensitively."
    ] = "",
    max_rows: Annotated[
        int, f"Max rows to read (1-{SHEETS_READ_MAX_ROWS}, default {SHEETS_READ_DEFAULT_MAX_ROWS})"
    ] = SHEETS_READ_DEFAULT_MAX_ROWS,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Read the cell values of a spreadsheet ("read this sheet and answer"): a Google
    Sheet, or an Excel workbook on OneDrive.

    Returns the sheet list (with their grid sizes where known), the requested
    sheet's values (bounded page) and an explicit truncation flag.

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
    file_id: Annotated[str, "File id of the document (from get_files_tool)"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Read a document's content as structured text (headings, lists, tables): a Google
    Doc, or a Word file on OneDrive.

    Use to answer about a document's content, summarize it, or compare it
    with other data. Long documents are truncated with an explicit flag.

    Returns:
        UnifiedToolOutput with the document title and markdown-ish content.
    """
    return await _read_document_instance.execute(runtime=runtime, file_id=file_id)


# ============================================================================
# WRITE (lot F phase write — HITL drafts)
# ============================================================================


class DocumentReplaceDraftInput(BaseModel):
    """Content of a DOCUMENT_REPLACE draft (persisted until confirmation)."""

    model_config = ConfigDict(frozen=True)

    file_id: str = Field(description="File id of the text file")
    document_title: str = Field(default="", description="File name (preview)")
    text: str = Field(description="The file's complete new text")
    tag: str = Field(description="The version the card was built on")
    user_language: str = Field(
        default_factory=resolve_language, description="User language for messages"
    )


class SpreadsheetWriteDraftInput(BaseModel):
    """Content of a SPREADSHEET_WRITE draft (persisted until confirmation)."""

    model_config = ConfigDict(frozen=True)

    file_id: str = Field(description="File id of the spreadsheet")
    spreadsheet_title: str = Field(default="", description="Spreadsheet title (preview)")
    sheet_name: str = Field(description="Exact sheet (tab) title")
    mode: str = Field(description="append (rows below the table) or update (a range)")
    a1_range: str = Field(default="", description="Target A1 range (update mode)")
    values: list[list[str]] = Field(description="Row-major cell values to write")
    user_language: str = Field(
        default_factory=resolve_language, description="User language for messages"
    )


class DocumentAppendDraftInput(BaseModel):
    """Content of a DOCUMENT_APPEND draft (persisted until confirmation)."""

    model_config = ConfigDict(frozen=True)

    file_id: str = Field(description="File id of the document")
    document_title: str = Field(default="", description="Document title (preview)")
    text: str = Field(description="Text appended verbatim at the end of the body")
    user_language: str = Field(
        default_factory=resolve_language, description="User language for messages"
    )


class WriteSpreadsheetTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """Write into a spreadsheet (append rows or update a range) via HITL draft."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    functional_category = _FILES
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
        client: GoogleDriveClient,
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

        try:
            async with spreadsheets_of(client, user_id) as spreadsheets:
                refusal = await spreadsheets.write_refusal(
                    a1_range if mode == "update" else "", values
                )
                if refusal is not None:
                    return _office_refusal(refusal)
                metadata = await spreadsheets.get_spreadsheet(file_id)
        except OfficeContentRefusedError as refused:
            return _office_refusal(refused.refusal)

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
                message=result.get("message")
                or str(result.get("error", "spreadsheet write failed")).replace("_", " "),
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


class AppendDocumentTextTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """Append text to a document of the account's drive via HITL draft."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    functional_category = _FILES
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize append document text tool."""
        super().__init__(tool_name="append_document_text_tool", operation="write")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
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

        try:
            async with documents_of(client, user_id) as documents:
                title = await documents.read_title(file_id)
        except OfficeContentRefusedError as refused:
            return _office_refusal(refused.refusal)
        return {
            "success": True,
            "file_id": file_id,
            "document_title": title,
            "text": text,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create the DOCUMENT_APPEND draft (requires confirmation)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message")
                or str(result.get("error", "document append failed")).replace("_", " "),
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


class ReplaceDocumentTextTool(ToolOutputMixin, ConnectorTool[GoogleDriveClient]):
    """Rewrite a plain text file of the account's drive via HITL draft."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    client_class = GoogleDriveClient
    functional_category = _FILES
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize replace document text tool."""
        super().__init__(tool_name="replace_document_text_tool", operation="write")

    async def execute_api_call(
        self,
        client: GoogleDriveClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Read the file the words replace, prepare the draft on that version."""
        file_id: str = str(kwargs.get("file_id") or "").strip()
        text: str = str(kwargs.get("text") or "")
        if not text.strip():
            return {"success": False, "error": "text_required"}
        if len(text) > WORKSPACE_DOC_APPEND_MAX_CHARS:
            return {"success": False, "error": "text_too_long"}

        try:
            async with documents_of(client, user_id) as documents:
                read = await documents.read_version(file_id)
        except OfficeContentRefusedError as refused:
            return _office_refusal(refused.refusal)
        return {
            "success": True,
            "file_id": file_id,
            "document_title": read.name,
            "text": text,
            "tag": read.tag,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Create the DOCUMENT_REPLACE draft (requires confirmation)."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message")
                or str(result.get("error", "document rewrite failed")).replace("_", " "),
                error_code=result.get("error"),
            )
        draft_input = DocumentReplaceDraftInput(
            file_id=result["file_id"],
            document_title=result["document_title"],
            text=result["text"],
            tag=result["tag"],
            user_language=self.get_user_language(),
        )
        return DraftService().create_draft(
            draft_type=DraftType.DOCUMENT_REPLACE,
            content=draft_input.model_dump(),
            related_registry_ids=[],
            source_tool="replace_document_text_tool",
            user_language=draft_input.user_language,
        )


_write_spreadsheet_instance = WriteSpreadsheetTool()
_append_document_text_instance = AppendDocumentTextTool()
_replace_document_text_instance = ReplaceDocumentTextTool()


@connector_tool(
    name="write_spreadsheet",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="write",
)
async def write_spreadsheet_tool(
    file_id: Annotated[str, "File id of the spreadsheet (from get_files_tool)"],
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
    Write into a spreadsheet ("add this expense to my budget sheet"): a Google Sheet, or an
    Excel workbook on a work OneDrive (a personal OneDrive refuses: it holds no workbook API).

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
    file_id: Annotated[str, "File id of the document (from get_files_tool)"],
    text: Annotated[str, "Text appended verbatim at the end of the document."],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Append text at the end of a document ("add this note to my meeting doc"): a Google Doc,
    or a Word file on OneDrive.

    Returns a confirmation draft showing the full text — nothing is written
    until the user approves.

    Returns:
        UnifiedToolOutput carrying the draft (requires_confirmation=True).
    """
    return await _append_document_text_instance.execute(runtime=runtime, file_id=file_id, text=text)


@connector_tool(
    name="replace_document_text",
    agent_name=AGENT_FILE,
    context_domain=CONTEXT_DOMAIN_FILES,
    category="write",
)
async def replace_document_text_tool(
    file_id: Annotated[str, "File id of the plain text file (from get_files_tool)"],
    text: Annotated[str, "The file's complete new text, written verbatim."],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Rewrite the whole text of a plain text file on the drive ("fix the typo in notes.txt").
    Read it first, then pass the complete new text.

    Returns a confirmation draft showing the full text — nothing is written
    until the user approves, and a file changed meanwhile is refused.

    Returns:
        UnifiedToolOutput carrying the draft (requires_confirmation=True).
    """
    return await _replace_document_text_instance.execute(
        runtime=runtime, file_id=file_id, text=text
    )


# ============================================================================
# DRAFT EXECUTORS (invoked on user confirmation)
# ============================================================================


@asynccontextmanager
async def _confirmed_drive(user_id: UUID, deps: Any) -> AsyncIterator[Any | None]:
    """What a confirmed act writes to: the drive active NOW, or nothing to say so."""
    connector_service = await deps.get_connector_service()
    for connector_type, client_class in _DRIVES.items():
        credentials = await connector_service.get_connector_credentials(user_id, connector_type)
        if credentials is None:
            continue
        drive = client_class(user_id, credentials, connector_service)
        try:
            yield drive
        finally:
            await drive.close()
        return
    yield None


def _refused(code: str, message: str) -> dict[str, Any]:
    """A confirmed write the file refused — nothing was written."""
    return {FIELD_SUCCESS: False, FIELD_ERROR_CODE: code, FIELD_ERROR: message}


def _card_refusal(refused: OfficeContentRefusedError) -> dict[str, Any]:
    """What a confirmation card reads for a file that refused the write."""
    message = _REFUSAL_MESSAGES[refused.refusal]
    if refused.refusal is OfficeRefusal.CHANGED:
        return _refused(FILE_CHANGED, message)
    if refused.refusal is OfficeRefusal.LOCKED:
        return _refused(FILE_LOCKED, message)
    return _refused(FILE_REFUSED, message)


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
        deps: ToolDependencies (the drive's credentials come through it).

    Returns:
        {"success", "mode", "updated_rows"/"updated_cells"} on write; a typed
        refusal when no drive is active any more, or the file refuses.
    """
    file_id = draft_content["file_id"]
    sheet = draft_content.get("sheet_name", "")
    values = draft_content.get("values") or []
    async with _confirmed_drive(user_id, deps) as drive:
        if drive is None:
            return connector_not_activated_refusal(ConnectorType.GOOGLE_DRIVE)
        try:
            async with spreadsheets_of(drive, user_id) as spreadsheets:
                if draft_content.get("mode") == "update":
                    cells = await spreadsheets.write_range(
                        file_id, sheet, draft_content.get("a1_range", ""), values
                    )
                    result = {"success": True, "mode": "update", "updated_cells": cells}
                else:
                    rows = await spreadsheets.append_rows(file_id, sheet, values)
                    result = {"success": True, "mode": "append", "updated_rows": rows}
        except OfficeContentRefusedError as refused:
            return _card_refusal(refused)

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
        deps: ToolDependencies (the drive's credentials come through it).

    Returns:
        {"success": True} on write; typed failure otherwise.
    """
    async with _confirmed_drive(user_id, deps) as drive:
        if drive is None:
            return connector_not_activated_refusal(ConnectorType.GOOGLE_DRIVE)
        try:
            async with documents_of(drive, user_id) as documents:
                await documents.append_text(draft_content["file_id"], draft_content.get("text", ""))
        except OfficeContentRefusedError as refused:
            return _card_refusal(refused)

    logger.info("document_append_draft_executed", user_id=str(user_id))
    return {"success": True}


async def execute_document_replace_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a confirmed DOCUMENT_REPLACE draft: write the text the card showed.

    Registered in ``draft_executor_registry.ensure_executors_registered()``.

    Args:
        draft_content: DocumentReplaceDraftInput content.
        user_id: Draft owner.
        deps: ToolDependencies (the drive's credentials come through it).

    Returns:
        {"success": True} on write; typed failure otherwise, a file changed since the card among
        them.
    """
    async with _confirmed_drive(user_id, deps) as drive:
        if drive is None:
            return connector_not_activated_refusal(ConnectorType.GOOGLE_DRIVE)
        try:
            async with documents_of(drive, user_id) as documents:
                await documents.replace_text(
                    draft_content["file_id"], draft_content.get("text", ""), draft_content["tag"]
                )
        except OfficeContentRefusedError as refused:
            return _card_refusal(refused)

    logger.info("document_replace_draft_executed", user_id=str(user_id))
    return {"success": True}
