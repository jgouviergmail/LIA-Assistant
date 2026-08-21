"""Google Sheets API client (lot F, 2026-08).

Rides the existing GOOGLE_DRIVE OAuth token: the Sheets API accepts the
already-granted ``auth/drive`` scope, so no new scope and no re-consent.
Reads plus range update / row append — writes are only reachable through
the HITL draft flow (workspace_docs_tools).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import structlog

from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)


class GoogleSheetsClient(BaseGoogleClient):
    """Read access to Google Sheets content (Drive-token ride-along)."""

    connector_type = ConnectorType.GOOGLE_DRIVE
    api_base_url = "https://sheets.googleapis.com/v4"

    async def get_spreadsheet(self, spreadsheet_id: str) -> dict[str, Any]:
        """Spreadsheet metadata: title + per-sheet titles and EXACT grid sizes.

        Args:
            spreadsheet_id: Drive file id of the spreadsheet.

        Returns:
            {"properties": {"title"}, "sheets": [{"properties": {"title",
            "gridProperties": {"rowCount", "columnCount"}}}]}.
        """
        return await self._make_request(
            "GET",
            f"/spreadsheets/{spreadsheet_id}",
            params={
                "fields": (
                    "properties(title),"
                    "sheets(properties(title,gridProperties(rowCount,columnCount)))"
                )
            },
        )

    async def get_values(self, spreadsheet_id: str, a1_range: str) -> dict[str, Any]:
        """Cell values for one A1 range.

        Args:
            spreadsheet_id: Drive file id of the spreadsheet.
            a1_range: A1 notation range (e.g. "'Feuille 1'!A1:ZZ50").

        Returns:
            {"values": [[...], ...]} (absent rows/cells omitted by the API).
        """
        encoded_range = quote(a1_range, safe="")
        response = await self._make_request(
            "GET", f"/spreadsheets/{spreadsheet_id}/values/{encoded_range}"
        )
        logger.info(
            "sheets_values_read",
            user_id=str(self.user_id),
            rows=len(response.get("values", [])),
        )
        return response

    async def update_values(
        self, spreadsheet_id: str, a1_range: str, values: list[list[str]]
    ) -> dict[str, Any]:
        """Overwrite the cells of one A1 range (write — always behind HITL).

        USER_ENTERED input: formulas, numbers and dates behave as if the user
        typed them (raw mode would store "=SUM(...)" as literal text).

        Args:
            spreadsheet_id: Drive file id of the spreadsheet.
            a1_range: A1 notation range to overwrite.
            values: Row-major cell values.

        Returns:
            The API update summary (updatedCells, updatedRange, ...).
        """
        encoded_range = quote(a1_range, safe="")
        response = await self._make_request(
            "PUT",
            f"/spreadsheets/{spreadsheet_id}/values/{encoded_range}",
            params={"valueInputOption": "USER_ENTERED"},
            json_data={"values": values},
        )
        logger.info(
            "sheets_values_updated",
            user_id=str(self.user_id),
            updated_cells=response.get("updatedCells", 0),
        )
        return response

    async def append_values(
        self, spreadsheet_id: str, a1_range: str, values: list[list[str]]
    ) -> dict[str, Any]:
        """Append rows after the last data row of a table (write — behind HITL).

        Google locates the table containing ``a1_range`` and appends below it —
        no manual "find the first empty row" arithmetic.

        Args:
            spreadsheet_id: Drive file id of the spreadsheet.
            a1_range: A1 range identifying the target table (e.g. "'Feuil1'!A1").
            values: Rows to append (row-major).

        Returns:
            The API append summary ({"updates": {...}}).
        """
        encoded_range = quote(a1_range, safe="")
        response = await self._make_request(
            "POST",
            f"/spreadsheets/{spreadsheet_id}/values/{encoded_range}:append",
            params={"valueInputOption": "USER_ENTERED"},
            json_data={"values": values},
        )
        logger.info(
            "sheets_values_appended",
            user_id=str(self.user_id),
            updated_rows=(response.get("updates") or {}).get("updatedRows", 0),
        )
        return response
