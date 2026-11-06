"""One door to a drive's spreadsheets and documents (ADR-369, lot 11).

The account's drive answers the assistant's tools: Google's on the Sheets and Docs clients that
ride its token, OneDrive's on its own files. The tools ask neither which it is.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.drive_text import TextFileDocuments
from src.domains.connectors.clients.google_docs_client import GoogleDocsClient
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.google_sheets_client import GoogleSheetsClient
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.clients.onedrive_office import OneDriveDocuments, OneDriveSpreadsheets
from src.domains.connectors.clients.protocols import DocumentsProtocol, SpreadsheetsProtocol
from src.domains.connectors.clients.workspace_content import documents_of, spreadsheets_of
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


def _inner(content: object) -> object:
    """What a door holds: documents come with the drive's plain text files around them."""
    return content._documents if isinstance(content, TextFileDocuments) else content


USER = uuid4()


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class TestGoogleDrive:
    @pytest.mark.parametrize(
        ("door", "client_class", "protocol"),
        [
            (spreadsheets_of, GoogleSheetsClient, SpreadsheetsProtocol),
            (documents_of, GoogleDocsClient, DocumentsProtocol),
        ],
    )
    async def test_its_content_rides_the_drives_token_and_is_closed(
        self, door: object, client_class: type, protocol: type
    ) -> None:
        drive = GoogleDriveClient(USER, _credentials(), MagicMock())

        with patch.object(client_class, "close", AsyncMock()) as close:
            async with door(drive, USER) as content:  # type: ignore[operator]
                assert isinstance(_inner(content), client_class)
                assert isinstance(content, protocol)
                assert _inner(content).credentials is drive.credentials
                close.assert_not_awaited()

        close.assert_awaited_once()

    async def test_a_failure_inside_still_closes_it(self) -> None:
        drive = GoogleDriveClient(USER, _credentials(), MagicMock())

        with patch.object(GoogleSheetsClient, "close", AsyncMock()) as close:
            with pytest.raises(RuntimeError):
                async with spreadsheets_of(drive, USER):
                    raise RuntimeError("provider down")

        close.assert_awaited_once()


class TestOneDrive:
    @pytest.mark.parametrize(
        ("door", "content_class", "protocol"),
        [
            (spreadsheets_of, OneDriveSpreadsheets, SpreadsheetsProtocol),
            (documents_of, OneDriveDocuments, DocumentsProtocol),
        ],
    )
    async def test_its_content_is_read_from_its_own_files(
        self, door: object, content_class: type, protocol: type
    ) -> None:
        drive = MicrosoftOneDriveClient(USER, _credentials(), MagicMock())

        async with door(drive, USER) as content:  # type: ignore[operator]
            assert isinstance(_inner(content), content_class)
            assert isinstance(content, protocol)
