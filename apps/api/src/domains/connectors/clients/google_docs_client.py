"""Google Docs API client + structural text extraction (lot F phase read).

Rides the existing GOOGLE_DRIVE OAuth token (the Docs API accepts the
``auth/drive`` scope — no re-consent). The parser turns the Docs body into
compact markdown-ish text: headings, paragraphs, bullet lists and tables —
what the LLM needs to answer about a document's content.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

_HEADING_LEVELS: dict[str, str] = {
    "HEADING_1": "# ",
    "HEADING_2": "## ",
    "HEADING_3": "### ",
    "HEADING_4": "#### ",
    "HEADING_5": "##### ",
    "HEADING_6": "###### ",
    "TITLE": "# ",
    "SUBTITLE": "## ",
}


def _paragraph_text(paragraph: dict[str, Any]) -> str:
    """Concatenated text runs of one paragraph (trailing newline stripped)."""
    parts = [
        element.get("textRun", {}).get("content", "") for element in paragraph.get("elements", [])
    ]
    return "".join(parts).rstrip("\n")


def _paragraph_line(paragraph: dict[str, Any]) -> str | None:
    """One markdown-ish line for a paragraph (None for empty paragraphs)."""
    text = _paragraph_text(paragraph)
    if not text.strip():
        return None
    style = (paragraph.get("paragraphStyle") or {}).get("namedStyleType", "")
    prefix = _HEADING_LEVELS.get(style, "")
    if not prefix and paragraph.get("bullet"):
        prefix = "- "
    return f"{prefix}{text}"


def _table_lines(table: dict[str, Any]) -> list[str]:
    """Pipe-separated rows for a Docs table."""
    lines = []
    for row in table.get("tableRows", []):
        cells = []
        for cell in row.get("tableCells", []):
            cell_texts = [
                line
                for element in cell.get("content", [])
                if "paragraph" in element
                and (line := _paragraph_line(element["paragraph"])) is not None
            ]
            cells.append(" ".join(cell_texts))
        lines.append(" | ".join(cells))
    return lines


def docs_structure_to_text(document: dict[str, Any]) -> str:
    """Compact markdown-ish text from a Docs API document payload.

    Args:
        document: Raw Docs API document (with "body.content").

    Returns:
        Headings as #-prefixed lines, bullets as "- ", tables as
        pipe-separated rows, paragraphs as plain lines.
    """
    lines: list[str] = []
    for element in (document.get("body") or {}).get("content", []):
        if "paragraph" in element:
            line = _paragraph_line(element["paragraph"])
            if line is not None:
                lines.append(line)
        elif "table" in element:
            lines.extend(_table_lines(element["table"]))
    return "\n".join(lines)


class GoogleDocsClient(BaseGoogleClient):
    """Read access to Google Docs content (Drive-token ride-along)."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    api_base_url = "https://docs.googleapis.com/v1"

    async def get_document(self, document_id: str) -> dict[str, Any]:
        """Fetch one document (title + structured body).

        Args:
            document_id: Drive file id of the document.

        Returns:
            Raw Docs API document payload.
        """
        response = await self._make_request("GET", f"/documents/{document_id}")
        logger.info("docs_document_read", user_id=str(self.user_id))
        return response

    async def append_text(self, document_id: str, text: str) -> dict[str, Any]:
        """Append text at the end of the document body (write — behind HITL).

        ``endOfSegmentLocation`` targets the body end without index
        arithmetic (indices shift on every edit — computing them is the
        classic Docs API foot-gun). A leading newline separates the appended
        text from the existing content.

        Args:
            document_id: Drive file id of the document.
            text: Plain text to append.

        Returns:
            The batchUpdate response.
        """
        response = await self._make_request(
            "POST",
            f"/documents/{document_id}:batchUpdate",
            json_data={
                "requests": [
                    {
                        "insertText": {
                            "endOfSegmentLocation": {},
                            "text": f"\n{text}",
                        }
                    }
                ]
            },
        )
        logger.info("docs_text_appended", user_id=str(self.user_id), chars=len(text))
        return response
