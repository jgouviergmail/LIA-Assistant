"""
CSV export utilities for GDPR data portability.

Provides reusable functions for generating CSV exports with proper
encoding for Excel compatibility.

Usage:
    from src.core.export_utils import create_csv_response

    return create_csv_response(
        data=[{"id": "1", "name": "Test"}],
        filename_prefix="interests",
    )
"""

import csv
import io
from datetime import UTC, datetime
from typing import Any

from fastapi.responses import StreamingResponse


def _opens_a_formula(text: str) -> bool:
    """Whether a spreadsheet would run ``text`` instead of showing it."""
    return text.startswith(("\t", "\r", "\n")) or text.lstrip().startswith(("=", "+", "-", "@"))


def spreadsheet_safe_cell(value: Any) -> Any:
    """Only text is escaped: numeric negative values remain numeric CSV values."""
    if isinstance(value, str) and _opens_a_formula(value):
        return "'" + value
    return value


def spreadsheet_cell_text(cell: str) -> str:
    """The text a protected cell held: :func:`spreadsheet_safe_cell`, read the other way.

    An import of an export restores what the export protected. One text is not
    restored: a text that already opened on a quote followed by a formula sign was
    exported as it was, so it reads back without its quote.

    Args:
        cell: A text cell of an exported CSV.

    Returns:
        The cell without the protection mark, or the cell itself when it carries none.
    """
    return cell[1:] if cell.startswith("'") and _opens_a_formula(cell[1:]) else cell


def create_csv_response(
    data: list[dict[str, Any]],
    filename_prefix: str,
) -> StreamingResponse:
    """
    Create a StreamingResponse with CSV content.

    Includes UTF-8 BOM for Excel compatibility with accented characters.

    Args:
        data: List of dictionaries to export (all dicts must have same keys)
        filename_prefix: Prefix for the filename (e.g., "interests", "memories")

    Returns:
        StreamingResponse with CSV content and proper headers
    """
    output = io.StringIO()

    # UTF-8 BOM for Excel compatibility with accented characters
    output.write("\ufeff")

    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(
            {key: spreadsheet_safe_cell(value) for key, value in row.items()} for row in data
        )

    csv_content = output.getvalue()
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_prefix}_{timestamp}.csv"',
        },
    )
