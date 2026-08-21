"""Client-cache key collision guard (lot I review, 2026-08).

Several client classes can ride the SAME connector token: GoogleDriveClient /
GoogleSheetsClient / GoogleDocsClient on GOOGLE_DRIVE, GoogleGmailClient /
GoogleGmailSettingsClient on GOOGLE_GMAIL. A cache key of (user, connector_type)
alone would hand tool B a cached instance of client A — an AttributeError at
best, a silently wrong API surface at worst. The key must be class-qualified.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.domains.agents.tools.base import ConnectorTool
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.google_sheets_client import GoogleSheetsClient
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit


class TestClientCacheKey:
    def test_same_connector_different_client_classes_get_distinct_keys(self) -> None:
        user_id = uuid4()
        drive_key = ConnectorTool._client_cache_key(
            user_id, ConnectorType.GOOGLE_DRIVE, GoogleDriveClient
        )
        sheets_key = ConnectorTool._client_cache_key(
            user_id, ConnectorType.GOOGLE_DRIVE, GoogleSheetsClient
        )
        assert drive_key != sheets_key

    def test_key_keeps_connector_type_in_second_position_for_metrics(self) -> None:
        # ToolDependencies._get_cache_type reads cache_key[1] to label the
        # Prometheus cache counters — the class qualifier must not move it.
        key = ConnectorTool._client_cache_key(
            uuid4(), ConnectorType.GOOGLE_DRIVE, GoogleSheetsClient
        )
        assert key[1] is ConnectorType.GOOGLE_DRIVE

    def test_same_class_same_user_is_stable(self) -> None:
        user_id = uuid4()
        first = ConnectorTool._client_cache_key(
            user_id, ConnectorType.GOOGLE_DRIVE, GoogleSheetsClient
        )
        second = ConnectorTool._client_cache_key(
            user_id, ConnectorType.GOOGLE_DRIVE, GoogleSheetsClient
        )
        assert first == second
