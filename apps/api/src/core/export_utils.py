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
        writer.writerows(data)

    csv_content = output.getvalue()
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename_prefix}_{timestamp}.csv"',
        },
    )
