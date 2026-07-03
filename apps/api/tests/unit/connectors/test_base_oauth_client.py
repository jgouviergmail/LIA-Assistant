"""Unit tests for BaseOAuthClient connector invalidation.

Covers _invalidate_connector_on_auth_failure, in particular the JSONB
persistence convention: connector_metadata must be REASSIGNED to a new dict,
never mutated in place (audit wave 2, B5 — in-place JSONB mutation is
silently dropped by SQLAlchemy).
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.connectors.clients.base_oauth_client import BaseOAuthClient
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials


def _make_connector(metadata: dict | None) -> Connector:
    """Build a Connector ORM instance for invalidation tests."""
    now = datetime.now(UTC)
    return Connector(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        connector_type=ConnectorType.GOOGLE_GMAIL,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="encrypted",
        connector_metadata=metadata,
        created_at=now,
        updated_at=now,
    )


class _SessionCM:
    """Async context manager wrapping a mock db session."""

    def __init__(self, db: AsyncMock) -> None:
        self._db = db

    async def __aenter__(self) -> AsyncMock:
        return self._db

    async def __aexit__(self, *args: object) -> bool:
        return False


def _make_client(db: AsyncMock) -> BaseOAuthClient:
    """Build a BaseOAuthClient wired to a mock connector service/session."""
    connector_service = MagicMock()
    connector_service.db = _SessionCM(db)
    connector_service._invalidate_user_connectors_cache = AsyncMock()
    client = BaseOAuthClient(
        user_id=uuid.uuid4(),
        credentials=ConnectorCredentials(access_token="token"),
        connector_service=connector_service,
    )
    client.connector_type = ConnectorType.GOOGLE_GMAIL
    return client


class TestInvalidateConnectorOnAuthFailure:
    """Tests for _invalidate_connector_on_auth_failure."""

    @pytest.mark.asyncio
    async def test_metadata_reassigned_as_new_dict(self):
        """Error info must land in a NEW dict (in-place update is never flushed)."""
        db = AsyncMock()
        client = _make_client(db)
        original_metadata = {"account_email_hash": "abc123"}
        connector = _make_connector(original_metadata)

        with patch("src.domains.connectors.repository.ConnectorRepository") as repo_cls:
            repo_cls.return_value.get_by_user_and_type = AsyncMock(return_value=connector)
            await client._invalidate_connector_on_auth_failure("401 boom")

        assert connector.status == ConnectorStatus.ERROR
        # New dict object (in-place .update() would keep the same identity)
        assert connector.connector_metadata is not original_metadata
        # Existing keys preserved, error info merged
        assert connector.connector_metadata["account_email_hash"] == "abc123"
        assert connector.connector_metadata["error_type"] == "oauth_authentication_failed"
        assert connector.connector_metadata["last_error"] == "401 boom"
        # Original dict untouched
        assert "error_type" not in original_metadata
        db.flush.assert_awaited_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_set_when_previously_empty(self):
        """Error info must be written even when metadata starts empty/None."""
        db = AsyncMock()
        client = _make_client(db)
        connector = _make_connector(None)

        with patch("src.domains.connectors.repository.ConnectorRepository") as repo_cls:
            repo_cls.return_value.get_by_user_and_type = AsyncMock(return_value=connector)
            await client._invalidate_connector_on_auth_failure(None)

        assert connector.status == ConnectorStatus.ERROR
        assert connector.connector_metadata is not None
        assert connector.connector_metadata["last_error"] == "OAuth authentication failed"
        assert connector.connector_metadata["error_type"] == "oauth_authentication_failed"

    @pytest.mark.asyncio
    async def test_connector_not_found_is_noop(self):
        """No crash and no writes when the connector does not exist."""
        db = AsyncMock()
        client = _make_client(db)

        with patch("src.domains.connectors.repository.ConnectorRepository") as repo_cls:
            repo_cls.return_value.get_by_user_and_type = AsyncMock(return_value=None)
            await client._invalidate_connector_on_auth_failure("401")

        db.flush.assert_not_awaited()
        db.commit.assert_not_awaited()
