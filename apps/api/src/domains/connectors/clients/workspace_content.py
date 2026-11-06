"""One door to what a drive's spreadsheets and documents hold (ADR-369, lot 11).

Google keeps them behind two APIs of their own, on the drive's token; OneDrive's are files of the
drive itself (``onedrive_office``); a plain text file is bytes on either (``drive_text``). The
assistant's tools ask none of them which it is.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from src.domains.connectors.clients.drive_text import TextFileDocuments
from src.domains.connectors.clients.google_docs_client import GoogleDocsClient
from src.domains.connectors.clients.google_sheets_client import GoogleSheetsClient
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.clients.onedrive_office import OneDriveDocuments, OneDriveSpreadsheets
from src.domains.connectors.clients.protocols import SpreadsheetsProtocol
from src.domains.connectors.session_scope import DetachedConnectorService


@asynccontextmanager
async def spreadsheets_of(drive: Any, user_id: UUID) -> AsyncIterator[SpreadsheetsProtocol]:
    """The spreadsheets of an open drive, closed on every path.

    Args:
        drive: The drive's open client.
        user_id: The account.

    Yields:
        What speaks the spreadsheets' vocabulary.
    """
    if isinstance(drive, MicrosoftOneDriveClient):
        yield OneDriveSpreadsheets(drive)
        return
    client = GoogleSheetsClient(user_id, drive.credentials, DetachedConnectorService())
    try:
        yield client
    finally:
        await client.close()


@asynccontextmanager
async def documents_of(drive: Any, user_id: UUID) -> AsyncIterator[TextFileDocuments]:
    """The documents of an open drive, closed on every path.

    Args:
        drive: The drive's open client.
        user_id: The account.

    Yields:
        What speaks the documents' vocabulary.
    """
    if isinstance(drive, MicrosoftOneDriveClient):
        yield TextFileDocuments(drive, OneDriveDocuments(drive))
        return
    client = GoogleDocsClient(user_id, drive.credentials, DetachedConnectorService())
    try:
        yield TextFileDocuments(drive, client)
    finally:
        await client.close()


__all__ = ["documents_of", "spreadsheets_of"]
