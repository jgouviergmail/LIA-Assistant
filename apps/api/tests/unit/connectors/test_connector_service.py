"""
Unit tests for Connector Service business logic.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 29
Created: 2025-11-21
Target: 13% → 80%+ coverage
Module: domains/connectors/service.py (343 statements, 1297 lines, 26 methods)

Test Coverage:
- Connector CRUD: get, update, delete with cache invalidation
- OAuth Flows: Gmail, Google Contacts with PKCE
- Credential Management: refresh, revoke, encryption
- API Key Connectors: activate, validate, get credentials
- Global Configs: admin management
- Cache: Redis cache with 5min TTL
- Security: Encryption, authorization, state validation

Critical Business Logic Module:
- OAuth 2.1 with PKCE (Proof Key for Code Exchange)
- Multi-connector support (OAuth + API Key)
- Token refresh with exponential backoff
- Cache management for performance
- Global admin controls
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException

from src.core.field_names import FIELD_STATUS
from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
)
from src.domains.connectors.schemas import (
    GOOGLE_CONTACTS_SCOPES,
    ConnectorCredentials,
    ConnectorGlobalConfigResponse,
    ConnectorGlobalConfigUpdate,
    ConnectorListResponse,
    ConnectorOAuthInitiate,
    ConnectorResponse,
    ConnectorUpdate,
)
from src.domains.connectors.service import ConnectorService

# Test Fixtures and Helpers


def create_encrypted_credentials(data: dict) -> str:
    """
    Create valid encrypted credentials for testing.

    Uses real encryption to generate valid Fernet tokens that can be decrypted.
    This is necessary because decrypt_data is imported locally in service methods,
    making it impossible to mock properly.

    Args:
        data: Dictionary to encrypt (e.g., {"api_key": "test", "api_secret": "secret"})

    Returns:
        Valid encrypted string compatible with decrypt_data()

    Example:
        credentials_data = {"api_key": "test_key_123", "api_secret": "secret_456"}
        encrypted = create_encrypted_credentials(credentials_data)
        connector = create_mock_connector(credentials_encrypted=encrypted)
    """
    import json

    from src.core.security import encrypt_data

    return encrypt_data(json.dumps(data))


def create_mock_connector(
    connector_id: UUID | None = None,
    user_id: UUID | None = None,
    connector_type: ConnectorType = ConnectorType.GOOGLE_GMAIL,
    status: ConnectorStatus = ConnectorStatus.ACTIVE,
    scopes: list[str] | None = None,
    credentials_encrypted: str = "encrypted_data",
    connector_metadata: dict | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Connector:
    """
    Factory function to create mock Connector with all required fields.

    Ensures all required fields from BaseModel (created_at, updated_at) are set.

    Args:
        connector_id: Connector UUID (auto-generated if None)
        user_id: User UUID (auto-generated if None)
        connector_type: Type of connector
        status: Connector status
        scopes: OAuth scopes (default: gmail readonly)
        credentials_encrypted: Encrypted credentials string
        connector_metadata: Additional metadata dict
        created_at: Creation timestamp (default: now)
        updated_at: Update timestamp (default: now)

    Returns:
        Fully initialized Connector model instance
    """
    if scopes is None:
        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    now = datetime.now(UTC)

    return Connector(
        id=connector_id or uuid4(),
        user_id=user_id or uuid4(),
        connector_type=connector_type,
        status=status,
        scopes=scopes,
        credentials_encrypted=credentials_encrypted,
        connector_metadata=connector_metadata or {},
        created_at=created_at or now,
        updated_at=updated_at or now,
    )


class TestConnectorServiceInit:
    """Tests for ConnectorService __init__."""

    def test_init_sets_db_and_repository(self):
        """Test __init__ creates repository (Line 64-66)."""
        mock_db = AsyncMock()

        service = ConnectorService(mock_db)

        assert service.db == mock_db
        assert service.repository is not None
        assert hasattr(service.repository, "get_by_id")


class TestGetUserConnectors:
    """Tests for get_user_connectors with Redis cache."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_get_user_connectors_cache_hit(self, mock_get_redis_cache):
        """Test get_user_connectors returns cached data (Lines 84-90)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis cache hit
        mock_redis = AsyncMock()
        cached_response = ConnectorListResponse(connectors=[], total=0)
        mock_redis.get = AsyncMock(return_value=cached_response.model_dump_json())
        mock_get_redis_cache.return_value = mock_redis

        # Lines 84-90 executed: Cache hit
        result = await service.get_user_connectors(user_id)

        assert result.total == 0
        mock_redis.get.assert_called_once_with(f"user_connectors:{user_id}")

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_get_user_connectors_cache_miss_queries_db(self, mock_get_redis_cache):
        """Test get_user_connectors queries DB on cache miss (Lines 87-105)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis cache miss
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()
        mock_get_redis_cache.return_value = mock_redis

        # Mock repository
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
        )
        service.repository.get_all_by_user = AsyncMock(return_value=[mock_connector])

        # Lines 87-105 executed: Cache miss → DB query → Cache set
        result = await service.get_user_connectors(user_id)

        assert result.total == 1
        assert len(result.connectors) == 1
        service.repository.get_all_by_user.assert_called_once_with(user_id)
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_invalidate_user_connectors_cache(self, mock_get_redis_cache):
        """Test _invalidate_user_connectors_cache deletes cache key (Lines 107-118)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis
        mock_redis = AsyncMock()
        mock_get_redis_cache.return_value = mock_redis

        # Lines 107-118 executed: Cache invalidation
        await service._invalidate_user_connectors_cache(user_id)

        mock_redis.delete.assert_called_once_with(f"user_connectors:{user_id}")


class TestGetConnectorById:
    """Tests for get_connector_by_id with ownership check."""

    @pytest.mark.asyncio
    @patch("src.domains.connectors.service.check_resource_ownership_by_user_id")
    async def test_get_connector_by_id_success(self, mock_check_ownership):
        """Test get_connector_by_id returns connector (Lines 120-137)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_id = uuid.uuid4()

        # Mock repository
        mock_connector = create_mock_connector(
            connector_id=connector_id,
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )
        service.repository.get_by_id = AsyncMock(return_value=mock_connector)

        # Lines 120-137 executed: Get + ownership check
        result = await service.get_connector_by_id(user_id, connector_id)

        assert result is not None
        service.repository.get_by_id.assert_called_once_with(connector_id)
        mock_check_ownership.assert_called_once_with(mock_connector, user_id, "connector")

    @pytest.mark.asyncio
    @patch("src.domains.connectors.service.check_resource_ownership_by_user_id")
    async def test_get_connector_by_id_ownership_check_raises(self, mock_check_ownership):
        """Test get_connector_by_id raises on ownership failure (Line 135)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_id = uuid.uuid4()
        other_user_id = uuid.uuid4()

        # Mock repository
        mock_connector = create_mock_connector(
            connector_id=connector_id,
            user_id=other_user_id,  # Different user
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )
        service.repository.get_by_id = AsyncMock(return_value=mock_connector)

        # Mock ownership check raises exception
        from src.core.exceptions import raise_permission_denied

        mock_check_ownership.side_effect = lambda *args, **kwargs: raise_permission_denied(
            "get", "connector", user_id
        )

        # Line 135 executed: Ownership check raises
        with pytest.raises(Exception) as exc_info:
            await service.get_connector_by_id(user_id, connector_id)

        assert exc_info.value.status_code == 403


class TestUpdateConnector:
    """Tests for update_connector with cache invalidation."""

    @pytest.mark.asyncio
    @patch("src.core.security.authorization.check_resource_ownership_by_user_id")
    async def test_update_connector_status(self, mock_check_ownership):
        """Test update_connector updates status (Lines 139-186)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_id = uuid.uuid4()

        # Mock connector
        mock_connector = create_mock_connector(
            connector_id=connector_id,
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )
        service.repository.get_by_id = AsyncMock(return_value=mock_connector)
        service.repository.update = AsyncMock(return_value=mock_connector)

        # Mock cache invalidation
        service._invalidate_user_connectors_cache = AsyncMock()

        # Lines 139-186 executed: Update status
        update_data = ConnectorUpdate(status=ConnectorStatus.REVOKED)
        result = await service.update_connector(user_id, connector_id, update_data)

        assert result is not None
        service.repository.update.assert_called_once()
        service._invalidate_user_connectors_cache.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    @patch("src.core.security.authorization.check_resource_ownership_by_user_id")
    async def test_update_connector_metadata(self, mock_check_ownership):
        """Test update_connector updates metadata (Lines 167-169)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_id = uuid.uuid4()

        # Mock connector
        mock_connector = create_mock_connector(
            connector_id=connector_id,
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            connector_metadata={"old": "data"},
        )
        service.repository.get_by_id = AsyncMock(return_value=mock_connector)
        service.repository.update = AsyncMock(return_value=mock_connector)
        service._invalidate_user_connectors_cache = AsyncMock()

        # Lines 167-169 executed: Update metadata
        new_metadata = {"new": "data", "updated": True}
        update_data = ConnectorUpdate(metadata=new_metadata)
        await service.update_connector(user_id, connector_id, update_data)

        # Verify update called with connector_metadata (not metadata)
        update_call = service.repository.update.call_args[0]
        update_dict = update_call[1]
        assert "connector_metadata" in update_dict
        assert update_dict["connector_metadata"] == new_metadata


class TestDeleteConnector:
    """Tests for delete_connector with revocation and cache invalidation."""

    @pytest.mark.asyncio
    @patch("src.core.security.authorization.check_resource_ownership_by_user_id")
    async def test_delete_connector_success(self, mock_check_ownership):
        """Test delete_connector deletes and invalidates cache (Lines 234-264)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_id = uuid.uuid4()

        # Mock connector
        mock_connector = create_mock_connector(
            connector_id=connector_id,
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )
        service.repository.get_by_id = AsyncMock(return_value=mock_connector)
        service.repository.delete = AsyncMock()
        service._revoke_oauth_token = AsyncMock()
        service._invalidate_user_connectors_cache = AsyncMock()

        # Lines 234-264 executed: Revoke + delete + cache invalidation
        await service.delete_connector(user_id, connector_id)

        service._revoke_oauth_token.assert_called_once_with(mock_connector)
        service.repository.delete.assert_called_once_with(mock_connector)
        service._invalidate_user_connectors_cache.assert_called_once_with(user_id)
        mock_db.commit.assert_called_once()


class TestOAuthFlows:
    """Tests for OAuth initiation and callback handling."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_session")
    @patch("src.core.oauth.OAuthFlowHandler")
    @patch("src.core.oauth.GoogleOAuthProvider")
    async def test_initiate_gmail_oauth(
        self, mock_provider_class, mock_flow_handler_class, mock_get_redis
    ):
        """Test initiate_gmail_oauth returns auth URL with PKCE (Lines 268-308)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()

        # Mock Redis
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        # Mock OAuth provider
        mock_provider = MagicMock()
        mock_provider_class.for_gmail.return_value = mock_provider

        # Mock flow handler
        mock_flow_handler = AsyncMock()
        mock_flow_handler.initiate_flow = AsyncMock(
            return_value=("https://accounts.google.com/o/oauth2/auth?...", "state_abc123")
        )
        mock_flow_handler_class.return_value = mock_flow_handler

        # Lines 268-308 executed: Initiate OAuth with PKCE
        result = await service.initiate_gmail_oauth(user_id)

        assert isinstance(result, ConnectorOAuthInitiate)
        assert result.authorization_url.startswith("https://accounts.google.com")
        assert result.state == "state_abc123"
        mock_flow_handler.initiate_flow.assert_called_once()

    @pytest.mark.skip(reason="Stateless method tested in TestGmailStateless")
    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_session")
    @patch("src.core.oauth.OAuthFlowHandler")
    @patch("src.core.oauth.GoogleOAuthProvider")
    async def test_handle_gmail_callback_success(
        self, mock_provider_class, mock_flow_handler_class, mock_get_redis
    ):
        """Test handle_gmail_callback creates connector (Lines 428-462)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        code = "auth_code_123"
        state = "state_abc123"

        # Mock Redis
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        # Mock OAuth provider
        mock_provider = MagicMock()
        mock_provider_class.for_gmail.return_value = mock_provider

        # Mock flow handler returns (token_response, stored_state)
        from src.core.field_names import FIELD_CONNECTOR_TYPE, FIELD_USER_ID
        from src.core.oauth import OAuthTokenResponse

        mock_token_response = OAuthTokenResponse(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_in=3600,
            scope="https://www.googleapis.com/auth/gmail.readonly",
        )

        stored_state_data = {
            FIELD_USER_ID: str(user_id),
            FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_GMAIL.value,
        }

        mock_flow_handler = AsyncMock()
        mock_flow_handler.handle_callback = AsyncMock(
            return_value=(mock_token_response, stored_state_data)
        )
        mock_flow_handler_class.return_value = mock_flow_handler

        # Mock repository
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)
        service._invalidate_user_connectors_cache = AsyncMock()

        # Mock DB refresh to populate defaults
        def populate_defaults(connector):
            if not connector.id:
                connector.id = uuid.uuid4()
            if not connector.created_at:
                connector.created_at = datetime.now(UTC)
            if not connector.updated_at:
                connector.updated_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=populate_defaults)

        # Lines 428-462 executed: OAuth callback creates connector
        result = await service.handle_gmail_callback_stateless(code, state)

        assert result is not None
        assert result.connector_type == ConnectorType.GOOGLE_GMAIL
        mock_flow_handler.handle_callback.assert_called_once()
        mock_db.commit.assert_called_once()


class TestCredentialManagement:
    """Tests for credential refresh and revocation."""

    @pytest.mark.asyncio
    @patch("src.core.security.authorization.check_resource_ownership_by_user_id")
    @patch("src.core.security.decrypt_data")
    @patch("src.core.security.encrypt_data")
    async def test_refresh_connector_credentials_success(
        self, mock_encrypt, mock_decrypt, mock_check_ownership
    ):
        """Test refresh_connector_credentials refreshes token (Lines 188-232)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_id = uuid.uuid4()

        # Mock connector
        mock_connector = create_mock_connector(
            connector_id=connector_id,
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted="old_encrypted",
        )
        service.repository.get_by_id = AsyncMock(return_value=mock_connector)

        # Mock credentials
        old_credentials = ConnectorCredentials(
            access_token="old_access",
            refresh_token="refresh_token_123",
            token_type="Bearer",
            expires_at=datetime.now(UTC),
        )
        new_credentials = ConnectorCredentials(
            access_token="new_access",
            refresh_token="refresh_token_123",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        mock_decrypt.return_value = old_credentials.model_dump_json()
        mock_encrypt.return_value = "new_encrypted"
        service._refresh_oauth_token = AsyncMock(return_value=new_credentials)

        # Lines 188-232 executed: Decrypt → refresh → encrypt
        result = await service.refresh_connector_credentials(user_id, connector_id)

        assert result is not None
        service._refresh_oauth_token.assert_called_once()
        mock_decrypt.assert_called_once()
        mock_encrypt.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_revoke_oauth_token_success(self, mock_httpx_client):
        """Test _revoke_oauth_token revokes at provider (Lines 642-666)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Create real encrypted credentials (decrypt_data is locally imported, can't mock)
        credentials_data = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "token_type": "Bearer",
            "expires_at": datetime.now(UTC).isoformat(),
        }
        encrypted_creds = create_encrypted_credentials(credentials_data)

        # Mock connector with real encrypted credentials
        mock_connector = create_mock_connector(
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted=encrypted_creds,
        )

        # No other active Google connectors → safe to revoke
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)

        # Mock HTTP client
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client

        # Lines 642-666 executed: Revoke token at provider
        await service._revoke_oauth_token(mock_connector)

        mock_client.post.assert_called_once()
        # Verify revoke URL called
        call_args = mock_client.post.call_args
        assert "revoke" in str(call_args)


class TestAPIKeyConnectors:
    """Tests for API key connector activation and management."""

    @pytest.mark.asyncio
    @patch("src.core.security.encrypt_data")
    async def test_activate_api_key_connector_new(self, mock_encrypt):
        """Test activate_api_key_connector creates new connector (Lines 1099-1201)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL
        api_key = "test_api_key_12345"
        api_secret = "secret_67890"

        # Mock DB refresh to populate defaults (id, created_at, updated_at)
        def populate_defaults(connector):
            if not connector.id:
                connector.id = uuid.uuid4()
            if not connector.created_at:
                connector.created_at = datetime.now(UTC)
            if not connector.updated_at:
                connector.updated_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=populate_defaults)

        # Mock repository
        service.repository.get_global_config_by_type = AsyncMock(return_value=None)
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)
        service._invalidate_user_connectors_cache = AsyncMock()

        mock_encrypt.return_value = "encrypted_credentials"

        # Lines 1099-1201 executed: Create new API key connector
        result = await service.activate_api_key_connector(
            user_id, connector_type, api_key, api_secret, key_name="Test Key"
        )

        assert result is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        service._invalidate_user_connectors_cache.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    @patch("src.core.security.encrypt_data")
    async def test_activate_api_key_connector_update_existing(self, mock_encrypt):
        """Test activate_api_key_connector updates existing (Lines 1160-1174)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL
        api_key = "new_api_key_12345"

        # Mock existing connector
        existing_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.REVOKED,
            scopes=[],
            credentials_encrypted="old_encrypted",
        )
        service.repository.get_global_config_by_type = AsyncMock(return_value=None)
        service.repository.get_by_user_and_type = AsyncMock(return_value=existing_connector)
        service._invalidate_user_connectors_cache = AsyncMock()

        mock_encrypt.return_value = "new_encrypted_credentials"

        # Lines 1160-1174 executed: Update existing connector
        result = await service.activate_api_key_connector(user_id, connector_type, api_key)

        assert result is not None
        assert existing_connector.status == ConnectorStatus.ACTIVE
        # Note: encrypt_data is locally imported, so mock doesn't apply - real encryption happens
        assert existing_connector.credentials_encrypted != "old_encrypted"  # Verify it was updated
        mock_db.flush.assert_called()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_api_key_valid(self):
        """Test validate_api_key validates format (Lines 1203-1235)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Lines 1203-1235 executed: Valid key
        is_valid, message = await service.validate_api_key(
            ConnectorType.GOOGLE_GMAIL, "valid_api_key_12345"
        )

        assert is_valid is True
        assert "valid" in message.lower()

    @pytest.mark.asyncio
    async def test_validate_api_key_too_short(self):
        """Test validate_api_key rejects short key (Lines 1224-1225)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Lines 1224-1225 executed: Too short
        is_valid, message = await service.validate_api_key(ConnectorType.GOOGLE_GMAIL, "short")

        assert is_valid is False
        assert "8 characters" in message

    @pytest.mark.asyncio
    async def test_validate_api_key_placeholder(self):
        """Test validate_api_key rejects placeholder (Lines 1228-1230)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Lines 1228-1230 executed: Placeholder pattern
        is_valid, message = await service.validate_api_key(
            ConnectorType.GOOGLE_GMAIL, "your_api_key_here"
        )

        assert is_valid is False
        assert "valid" in message.lower()

    @pytest.mark.asyncio
    async def test_get_api_key_credentials_success(self):
        """Test get_api_key_credentials returns decrypted credentials (Lines 1237-1283)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Create real encrypted credentials (decrypt_data is locally imported, can't mock)
        credentials_data = {
            "api_key": "test_key_123",
            "api_secret": "secret_456",
            "key_name": "Test Key",
            "expires_at": None,
        }
        encrypted_creds = create_encrypted_credentials(credentials_data)

        # Mock active connector with real encrypted credentials
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            connector_metadata={},
            credentials_encrypted=encrypted_creds,
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Lines 1237-1283 executed: Get + decrypt
        result = await service.get_api_key_credentials(user_id, connector_type)

        assert result is not None
        assert result.api_key == "test_key_123"
        assert result.api_secret == "secret_456"

    @pytest.mark.asyncio
    async def test_get_api_key_credentials_not_found(self):
        """Test get_api_key_credentials returns None when not found (Lines 1254-1255)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Mock no connector
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)

        # Lines 1254-1255 executed: Not found
        result = await service.get_api_key_credentials(user_id, connector_type)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_api_key_credentials_revoked_raises(self):
        """Test get_api_key_credentials raises for revoked connector (Lines 1257-1262)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Mock revoked connector
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.REVOKED,
            scopes=[],
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Lines 1257-1262 executed: Revoked raises 403
        with pytest.raises(Exception) as exc_info:
            await service.get_api_key_credentials(user_id, connector_type)

        assert exc_info.value.status_code == 403


class TestGlobalConfigs:
    """Tests for global connector configuration (admin)."""

    @pytest.mark.asyncio
    async def test_get_global_config_all(self):
        """Test get_global_config_all returns all configs (Lines 935-943)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        now = datetime.now(UTC)

        # Mock repository - ConnectorGlobalConfig inherits BaseModel (requires id, created_at, updated_at)
        mock_configs = [
            ConnectorGlobalConfig(
                id=uuid.uuid4(),
                connector_type=ConnectorType.GOOGLE_GMAIL,
                is_enabled=True,
                disabled_reason=None,
                created_at=now,
                updated_at=now,
            ),
            ConnectorGlobalConfig(
                id=uuid.uuid4(),
                connector_type=ConnectorType.GOOGLE_CONTACTS,
                is_enabled=False,
                disabled_reason="Under maintenance",
                created_at=now,
                updated_at=now,
            ),
        ]
        service.repository.get_all_global_configs = AsyncMock(return_value=mock_configs)

        # Lines 935-943 executed: Get all configs
        result = await service.get_global_config_all()

        assert len(result) == 2
        assert isinstance(result[0], ConnectorGlobalConfigResponse)

    @pytest.mark.asyncio
    async def test_get_global_config_by_type(self):
        """Test get_global_config returns specific config (Lines 945-958)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        now = datetime.now(UTC)

        # Mock repository - ConnectorGlobalConfig inherits BaseModel
        mock_config = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_GMAIL,
            is_enabled=True,
            disabled_reason=None,
            created_at=now,
            updated_at=now,
        )
        service.repository.get_global_config_by_type = AsyncMock(return_value=mock_config)

        # Lines 945-958 executed: Get specific config
        result = await service.get_global_config(ConnectorType.GOOGLE_GMAIL)

        assert result.is_enabled is True
        assert result.connector_type == ConnectorType.GOOGLE_GMAIL

    @pytest.mark.asyncio
    async def test_update_global_config_disable(self):
        """Test update_global_config disables connector type (Lines 960-1012)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        now = datetime.now(UTC)

        # Mock repository - ConnectorGlobalConfig inherits BaseModel
        mock_config = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=ConnectorType.GOOGLE_GMAIL,
            is_enabled=True,
            disabled_reason=None,
            created_at=now,
            updated_at=now,
        )
        service.repository.get_global_config_by_type = AsyncMock(return_value=mock_config)
        service.repository.update_global_config = AsyncMock(return_value=mock_config)
        service._revoke_all_connectors_by_type = AsyncMock()

        # Lines 960-1012 executed: Disable + revoke all
        from src.domains.connectors.schemas import ConnectorGlobalConfigUpdate

        admin_user_id = uuid.uuid4()

        update_data = ConnectorGlobalConfigUpdate(
            is_enabled=False, disabled_reason="Security issue"
        )
        await service.update_global_config(ConnectorType.GOOGLE_GMAIL, update_data, admin_user_id)

        service._revoke_all_connectors_by_type.assert_called_once_with(ConnectorType.GOOGLE_GMAIL)
        service.repository.update_global_config.assert_called_once()


# Additional edge case tests
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    @patch("src.core.security.decrypt_data")
    async def test_get_api_key_credentials_decryption_fails(self, mock_decrypt):
        """Test get_api_key_credentials handles decryption error (Lines 1285-1294)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Mock active connector
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted="corrupted_data",
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Mock decryption failure
        mock_decrypt.side_effect = Exception("Decryption failed")

        # Lines 1285-1294 executed: Exception caught and raised as invalid_input
        with pytest.raises(Exception) as exc_info:
            await service.get_api_key_credentials(user_id, connector_type)

        # Verify proper error raised
        assert exc_info.value.status_code == 400  # invalid_input

    @pytest.mark.asyncio
    async def test_get_api_key_credentials_inactive_returns_none(self):
        """Test get_api_key_credentials returns None for inactive (Lines 1264-1271)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Mock inactive connector (not ACTIVE or REVOKED)
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.INACTIVE,  # Inactive
            scopes=[],
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Lines 1264-1271 executed: Inactive → None
        result = await service.get_api_key_credentials(user_id, connector_type)

        assert result is None

    @pytest.mark.asyncio
    @patch("src.core.security.encrypt_data")
    async def test_activate_api_key_connector_disabled_globally(self, mock_encrypt):
        """Test activate_api_key_connector raises when globally disabled (Lines 1131-1137)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL
        now = datetime.now(UTC)

        # Mock global config disabled - ConnectorGlobalConfig inherits BaseModel
        disabled_config = ConnectorGlobalConfig(
            id=uuid.uuid4(),
            connector_type=connector_type,
            is_enabled=False,
            disabled_reason="Maintenance",
            created_at=now,
            updated_at=now,
        )
        service.repository.get_global_config_by_type = AsyncMock(return_value=disabled_config)

        # Lines 1131-1137 executed: Disabled globally → raises 403
        with pytest.raises(Exception) as exc_info:
            await service.activate_api_key_connector(user_id, connector_type, "test_key_123")

        assert exc_info.value.status_code == 403


# ========================================================================
# SESSION 35a - PHASE 1: QUICK WINS (P5-P7) - 4 tests
# ========================================================================


class TestOAuthCallbackErrors:
    """Tests for OAuth callback error handling edge cases."""

    @pytest.mark.skip(reason="Stateless method tested in separate test class")
    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_session")
    @patch("src.core.oauth.OAuthFlowHandler")
    @patch("src.core.oauth.GoogleOAuthProvider")
    async def test_handle_oauth_callback_exception_raises(
        self, mock_provider_class, mock_flow_handler_class, mock_get_redis
    ):
        """Test OAuth callback exception handling (Lines 357-363)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        code = "auth_code_123"
        state = "state_abc123"

        # Mock Redis
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        # Mock OAuth provider
        mock_provider = MagicMock()
        mock_provider_class.for_gmail.return_value = mock_provider

        # Mock flow handler to raise exception during callback
        mock_flow_handler = AsyncMock()
        mock_flow_handler.handle_callback = AsyncMock(side_effect=Exception("OAuth flow failed"))
        mock_flow_handler_class.return_value = mock_flow_handler

        # Lines 357-363 executed: Exception handling
        with pytest.raises(Exception) as exc_info:
            await service.handle_gmail_callback_stateless(code, state)

        # Verify raise_oauth_flow_failed called
        assert "oauth" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()

    @pytest.mark.skip(reason="Stateless flow does not have user_id parameter to compare against")
    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_session")
    @patch("src.core.oauth.OAuthFlowHandler")
    @patch("src.core.oauth.GoogleOAuthProvider")
    async def test_handle_oauth_callback_state_mismatch_raises(
        self, mock_provider_class, mock_flow_handler_class, mock_get_redis
    ):
        """Test state mismatch raises error (Lines 369-370)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        different_user_id = uuid.uuid4()  # Different user ID
        code = "auth_code_123"
        state = "state_abc123"

        # Mock Redis
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        # Mock OAuth provider
        mock_provider = MagicMock()
        mock_provider_class.for_gmail.return_value = mock_provider

        # Mock flow handler with different user_id in stored state
        from src.core.field_names import FIELD_CONNECTOR_TYPE, FIELD_USER_ID
        from src.core.oauth import OAuthTokenResponse

        mock_token_response = OAuthTokenResponse(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_in=3600,
            scope="https://www.googleapis.com/auth/gmail.readonly",
        )

        stored_state_data = {
            FIELD_USER_ID: str(different_user_id),  # MISMATCH: Different user
            FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_GMAIL.value,
        }

        mock_flow_handler = AsyncMock()
        mock_flow_handler.handle_callback = AsyncMock(
            return_value=(mock_token_response, stored_state_data)
        )
        mock_flow_handler_class.return_value = mock_flow_handler

        # Lines 369-370 executed: State mismatch validation
        with pytest.raises(Exception) as exc_info:
            await service.handle_gmail_callback(user_id, code, state)

        # Verify raise_oauth_state_mismatch called
        assert exc_info.value.status_code == 400  # Bad request for state mismatch


class TestGmailStateless:
    """Tests for Gmail stateless OAuth callback wrapper."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.cache.redis.get_redis_session")
    async def test_handle_gmail_callback_stateless_delegates(self, mock_get_redis):
        """Test Gmail stateless callback delegates correctly (Lines 481-491)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        code = "auth_code_123"
        state = "state_abc123"

        # Mock Redis
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis

        # Mock the internal stateless handler
        service._handle_oauth_connector_callback_stateless = AsyncMock(
            return_value=create_mock_connector(
                connector_type=ConnectorType.GOOGLE_GMAIL,
                status=ConnectorStatus.ACTIVE,
                scopes=[],
            )
        )

        # Lines 481-491 executed: Delegation to stateless handler
        result = await service.handle_gmail_callback_stateless(code, state)

        assert result is not None
        # Verify call with ALL keyword arguments including metadata
        from src.core.oauth import GoogleOAuthProvider

        service._handle_oauth_connector_callback_stateless.assert_called_once_with(
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            provider_factory_method=GoogleOAuthProvider.for_gmail,
            default_scopes=None,
            metadata={"last_synced": None, "created_via": "oauth_flow_stateless"},
        )


class TestAPIKeyMetadata:
    """Tests for API key connector metadata management."""

    @pytest.mark.asyncio
    async def test_get_api_key_credentials_updates_last_used(self):
        """Test get_api_key_credentials updates last_used_at (Lines 1279-1281)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Create real encrypted credentials
        credentials_data = {
            "api_key": "test_key_123",
            "api_secret": "secret_456",
            "key_name": "Test Key",
            "expires_at": None,
        }
        encrypted_creds = create_encrypted_credentials(credentials_data)

        # Mock active connector with metadata (last_used_at)
        old_last_used = datetime.now(UTC) - timedelta(hours=24)
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            connector_metadata={"last_used_at": old_last_used.isoformat()},
            credentials_encrypted=encrypted_creds,
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Lines 1279-1281 executed: last_used_at update
        result = await service.get_api_key_credentials(user_id, connector_type)

        assert result is not None
        # Verify last_used_at was updated (should be more recent)
        updated_last_used = datetime.fromisoformat(
            mock_connector.connector_metadata["last_used_at"]
        )
        assert updated_last_used > old_last_used
        # Line 1281: Uses flush(), not commit()
        mock_db.flush.assert_called_once()


# ========================================================================
# SESSION 35a - PHASE 2: OAUTH CREDENTIALS (P1) - 9 tests
# ========================================================================


class TestGetConnectorCredentialsEdgeCases:
    """Tests for get_connector_credentials edge cases."""

    @pytest.mark.asyncio
    async def test_get_connector_credentials_token_expired_refreshes(self):
        """Test expired token triggers refresh (Lines 536-537)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Create real encrypted credentials with expired token
        credentials_data = {
            "access_token": "old_access_token",
            "refresh_token": "refresh_token_123",
            "token_type": "Bearer",
            "expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),  # EXPIRED
        }
        encrypted_creds = create_encrypted_credentials(credentials_data)

        # Mock connector with expired credentials
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted=encrypted_creds,
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Mock refresh to return new credentials
        new_credentials = ConnectorCredentials(
            access_token="new_access_token",
            refresh_token="refresh_token_123",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        service._refresh_oauth_token = AsyncMock(return_value=new_credentials)

        # Lines 536-537 executed: Token expiration check → refresh
        result = await service.get_connector_credentials(user_id, connector_type)

        assert result is not None
        service._refresh_oauth_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_connector_credentials_not_active_returns_none(self):
        """Test inactive connector returns None (Lines 521-528)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Mock connector with INACTIVE status
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.INACTIVE,  # NOT ACTIVE
            scopes=[],
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Lines 521-528 executed: Status check → None
        result = await service.get_connector_credentials(user_id, connector_type)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_connector_credentials_decryption_error(self):
        """Test decryption failure raises exception (Lines 541-550)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid.uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Mock connector with corrupted encrypted credentials
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted="CORRUPTED_INVALID_BASE64!!!",  # Invalid encryption
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Lines 541-550 executed: Decryption error handling
        with pytest.raises(Exception) as exc_info:
            await service.get_connector_credentials(user_id, connector_type)

        # Verify proper error raised (invalid_input or internal_server_error)
        assert exc_info.value.status_code in [400, 500]


class TestRefreshOAuthToken:
    """Tests for _refresh_oauth_token error paths."""

    @pytest.mark.asyncio
    async def test_refresh_oauth_token_no_refresh_token_raises(self):
        """Test refresh fails when no refresh token (Lines 558-566)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Mock connector
        mock_connector = create_mock_connector(
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )

        # Create credentials WITHOUT refresh_token
        credentials = ConnectorCredentials(
            access_token="access_token_123",
            refresh_token=None,  # NO REFRESH TOKEN
            token_type="Bearer",
            expires_at=datetime.now(UTC),
        )

        # Lines 558-566 executed: No refresh token → raise invalid_input
        with pytest.raises(Exception) as exc_info:
            await service._refresh_oauth_token(mock_connector, credentials)

        assert exc_info.value.status_code == 400  # invalid_input

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_refresh_oauth_token_network_error_retries_then_fails(self, mock_httpx_client):
        """Test network error triggers retries then fails (Lines 588-601)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Mock connector
        mock_connector = create_mock_connector(
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )

        # Create credentials with refresh_token
        credentials = ConnectorCredentials(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_at=datetime.now(UTC),
        )

        # Mock HTTP client to raise network error (triggers tenacity retry)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Network unreachable"))
        mock_httpx_client.return_value.__aenter__.return_value = mock_client

        # Mock repository update for ERROR marking
        service.repository.update = AsyncMock()

        # Lines 588-601 executed: Network error → retry → fail
        with pytest.raises(Exception) as exc_info:
            await service._refresh_oauth_token(mock_connector, credentials)

        # Verify retries occurred and status marked as ERROR
        assert mock_client.post.call_count >= 2  # At least 2 attempts
        assert exc_info.value.status_code == 400  # invalid_input

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_refresh_oauth_token_http_status_error_retries(self, mock_httpx_client):
        """Test HTTP error triggers retries (Lines 588-601)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Mock connector
        mock_connector = create_mock_connector(
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )

        # Create credentials with refresh_token
        credentials = ConnectorCredentials(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_at=datetime.now(UTC),
        )

        # Mock HTTP client to raise HTTPStatusError (triggers tenacity retry)
        mock_response = MagicMock()
        mock_response.status_code = 503  # Service unavailable
        mock_response.request = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Service unavailable", request=mock_response.request, response=mock_response
            )
        )
        mock_httpx_client.return_value.__aenter__.return_value = mock_client

        # Mock repository update
        service.repository.update = AsyncMock()

        # Lines 588-601 executed: HTTP error → retry → fail
        with pytest.raises(Exception) as exc_info:
            await service._refresh_oauth_token(mock_connector, credentials)

        # Verify retries occurred
        assert mock_client.post.call_count >= 2
        assert exc_info.value.status_code == 400  # invalid_input

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_refresh_oauth_token_non_200_status_marks_error(self, mock_httpx_client):
        """Test non-200 status marks connector as ERROR (Lines 603-617)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Mock connector
        mock_connector = create_mock_connector(
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )

        # Create credentials with refresh_token
        credentials = ConnectorCredentials(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_at=datetime.now(UTC),
        )

        # Mock HTTP client to return 401 Unauthorized (invalid refresh token)
        mock_response = MagicMock()  # Use MagicMock, not AsyncMock for response
        mock_response.status_code = 401
        mock_response.text = "Invalid refresh token"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client

        # Mock repository update
        service.repository.update = AsyncMock()

        # Lines 603-617 executed: Non-200 → mark ERROR + commit
        with pytest.raises((HTTPException, ValueError, RuntimeError)):
            await service._refresh_oauth_token(mock_connector, credentials)

        # Verify connector marked as ERROR and repository updated
        service.repository.update.assert_called_once()
        # Verify commit was called (once for ERROR status update)
        assert mock_db.commit.call_count >= 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_refresh_oauth_token_success_updates_credentials(self, mock_httpx_client):
        """Test successful refresh updates credentials (Lines 619-640)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Mock connector
        mock_connector = create_mock_connector(
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )

        # Create credentials with refresh_token
        credentials = ConnectorCredentials(
            access_token="old_access_token",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_at=datetime.now(UTC),
        )

        # Mock HTTP client to return successful token response
        mock_response = MagicMock()  # Use MagicMock for sync response
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={
                "access_token": "new_access_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
            }
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client

        # Mock repository update_credentials
        service.repository.update_credentials = AsyncMock()

        # Lines 619-640 executed: Success → update credentials + commit
        result = await service._refresh_oauth_token(mock_connector, credentials)

        assert result is not None
        assert result.access_token == "new_access_token"
        assert result.refresh_token == "refresh_token_456"  # Preserved
        service.repository.update_credentials.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient")
    async def test_refresh_oauth_token_updates_expires_at(self, mock_httpx_client):
        """Test refresh updates expires_at correctly (Lines 622-625)."""
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Mock connector
        mock_connector = create_mock_connector(
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
        )

        # Create credentials with refresh_token
        credentials = ConnectorCredentials(
            access_token="old_access_token",
            refresh_token="refresh_token_456",
            token_type="Bearer",
            expires_at=datetime.now(UTC),
        )

        # Mock HTTP client to return token response with expires_in
        expires_in_seconds = 7200  # 2 hours
        mock_response = MagicMock()  # Use MagicMock for sync response
        mock_response.status_code = 200
        mock_response.json = MagicMock(
            return_value={
                "access_token": "new_access_token",
                "token_type": "Bearer",
                "expires_in": expires_in_seconds,
                "scope": "https://www.googleapis.com/auth/gmail.readonly",
            }
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx_client.return_value.__aenter__.return_value = mock_client

        # Mock repository update_credentials
        service.repository.update_credentials = AsyncMock()

        # Lines 622-625 executed: expires_at calculation
        before_refresh = datetime.now(UTC)
        result = await service._refresh_oauth_token(mock_connector, credentials)
        datetime.now(UTC)

        assert result is not None
        assert result.expires_at is not None

        # Verify expires_at is approximately now + expires_in (within 10 seconds tolerance)
        expected_expiry = before_refresh + timedelta(seconds=expires_in_seconds)
        assert abs((result.expires_at - expected_expiry).total_seconds()) < 10


# ========================================
# SESSION 35b - PHASE 2: GOOGLE CONTACTS OAUTH FLOW (5 tests)
# Target: Lines 684-717, 746-756, 921-931, 1021-1028
# ========================================


@pytest.mark.asyncio
class TestGoogleContactsOAuthFlow:
    """Test Google Contacts OAuth initiation and callbacks (Priority 2)."""

    async def test_initiate_google_contacts_oauth_success(self):
        """
        Test successful Google Contacts OAuth initiation.

        Coverage:
        - Lines 684-717: Full initiate_google_contacts_oauth method
        - Validates OAuth flow handler integration
        - Verifies PKCE parameters (access_type=offline, prompt=consent)
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        expected_auth_url = "https://accounts.google.com/o/oauth2/v2/auth?client_id=..."
        expected_state = "secure_state_token_123"

        # Mock _check_connector_enabled (always passes)
        service._check_connector_enabled = AsyncMock()

        # Mock Redis session
        mock_redis = AsyncMock()
        with patch("src.domains.connectors.service.get_redis_session", return_value=mock_redis):
            # Mock OAuthFlowHandler at source module
            with patch("src.core.oauth.OAuthFlowHandler") as mock_flow_handler_class:
                mock_flow_instance = AsyncMock()
                mock_flow_instance.initiate_flow = AsyncMock(
                    return_value=(expected_auth_url, expected_state)
                )
                mock_flow_handler_class.return_value = mock_flow_instance

                # Act
                result = await service.initiate_google_contacts_oauth(user_id)

        # Assert
        assert isinstance(result, ConnectorOAuthInitiate)
        assert result.authorization_url == expected_auth_url
        assert result.state == expected_state

        # Verify _check_connector_enabled called with GOOGLE_CONTACTS
        service._check_connector_enabled.assert_called_once_with(ConnectorType.GOOGLE_CONTACTS)

        # Verify initiate_flow called with correct params
        mock_flow_instance.initiate_flow.assert_called_once()
        call_kwargs = mock_flow_instance.initiate_flow.call_args.kwargs
        assert call_kwargs["additional_params"]["access_type"] == "offline"
        assert call_kwargs["additional_params"]["prompt"] == "consent"
        assert call_kwargs["metadata"]["user_id"] == str(user_id)
        assert call_kwargs["metadata"]["connector_type"] == ConnectorType.GOOGLE_CONTACTS.value

    async def test_initiate_google_contacts_oauth_disabled_raises(self):
        """
        Test OAuth initiation fails when Google Contacts connector is disabled.

        Coverage:
        - Line 684: _check_connector_enabled raises exception
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)
        user_id = uuid4()

        # Mock _check_connector_enabled to raise permission denied
        from src.core.exceptions import raise_permission_denied

        service._check_connector_enabled = AsyncMock(
            side_effect=lambda ct: raise_permission_denied(
                action="use", resource_type=f"{ct.value} connector"
            )
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service.initiate_google_contacts_oauth(user_id)

        assert exc_info.value.status_code == 403
        service._check_connector_enabled.assert_called_once_with(ConnectorType.GOOGLE_CONTACTS)

    @pytest.mark.skip(reason="Deprecated method handle_google_contacts_callback was removed")
    async def test_handle_google_contacts_callback_stateful_delegates(self):
        """
        Test deprecated stateful Google Contacts callback delegates correctly.

        Coverage:
        - Lines 746-756: handle_google_contacts_callback (deprecated wrapper)
        - Verifies delegation to _handle_oauth_connector_callback
        - Validates metadata created_via = oauth_flow
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        code = "auth_code_123"
        state = "state_token_456"

        expected_response = ConnectorResponse(
            id=uuid4(),
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/contacts.readonly"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock internal handler
        service._handle_oauth_connector_callback = AsyncMock(return_value=expected_response)

        # Act
        result = await service.handle_google_contacts_callback(user_id, code, state)

        # Assert
        assert result == expected_response

        # Verify delegation with correct parameters
        from src.core.oauth import GoogleOAuthProvider

        service._handle_oauth_connector_callback.assert_called_once_with(
            user_id=user_id,
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            provider_factory_method=GoogleOAuthProvider.for_contacts,
            default_scopes=GOOGLE_CONTACTS_SCOPES,
            metadata={"created_via": "oauth_flow"},
        )

    async def test_handle_google_contacts_callback_stateless_success(self):
        """
        Test Google Contacts stateless callback delegates correctly.

        Coverage:
        - Lines 921-931: handle_google_contacts_callback_stateless
        - Verifies delegation to _handle_oauth_connector_callback_stateless
        - Validates metadata created_via = oauth_flow_stateless
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        code = "auth_code_789"
        state = "state_token_abc"

        expected_response = ConnectorResponse(
            id=uuid4(),
            user_id=uuid4(),
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/contacts.readonly"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock internal stateless handler
        service._handle_oauth_connector_callback_stateless = AsyncMock(
            return_value=expected_response
        )

        # Act
        result = await service.handle_google_contacts_callback_stateless(code, state)

        # Assert
        assert result == expected_response

        # Verify delegation with correct parameters
        from src.core.oauth import GoogleOAuthProvider

        service._handle_oauth_connector_callback_stateless.assert_called_once_with(
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            provider_factory_method=GoogleOAuthProvider.for_contacts,
            default_scopes=GOOGLE_CONTACTS_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    async def test_check_connector_enabled_disabled_raises(self):
        """
        Test _check_connector_enabled raises exception when connector is disabled.

        Coverage:
        - Lines 1021-1028: _check_connector_enabled method
        - Validates global config enforcement
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        # Mock get_global_config to return disabled config
        from src.domains.connectors.models import ConnectorGlobalConfig

        disabled_config = ConnectorGlobalConfig(
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            is_enabled=False,
        )
        service.get_global_config = AsyncMock(return_value=disabled_config)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await service._check_connector_enabled(ConnectorType.GOOGLE_CONTACTS)

        assert exc_info.value.status_code == 403
        service.get_global_config.assert_called_once_with(ConnectorType.GOOGLE_CONTACTS)


# ========================================
# SESSION 35b - PHASE 3: STATELESS OAUTH CALLBACK VALIDATION (6 tests)
# Target: Lines 809-892 (stateless callback security validations)
# ========================================


@pytest.mark.asyncio
class TestStatelessOAuthCallbackValidation:
    """Test stateless OAuth callback security validations (Priority 3)."""

    async def test_stateless_callback_invalid_state_raises(self):
        """
        Test stateless callback fails when state is invalid/expired.

        Coverage:
        - Lines 818-827: State validation (not found in Redis)
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        code = "auth_code_123"
        state = "invalid_state_token"

        # Mock Redis to return None (state not found)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("src.domains.connectors.service.get_redis_session", return_value=mock_redis):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service._handle_oauth_connector_callback_stateless(
                    code=code,
                    state=state,
                    connector_type=ConnectorType.GOOGLE_CONTACTS,
                    provider_factory_method=lambda s: None,
                    default_scopes=None,
                    metadata=None,
                )

        assert exc_info.value.status_code == 400
        assert "Invalid or expired OAuth state" in exc_info.value.detail
        mock_redis.get.assert_called_once_with(f"oauth:state:{state}")

    async def test_stateless_callback_missing_user_id_raises(self):
        """
        Test stateless callback fails when state data missing user_id.

        Coverage:
        - Lines 835-844: user_id extraction validation
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        code = "auth_code_456"
        state = "valid_state_without_user_id"

        # Mock Redis to return state data without user_id
        import json

        state_data = {"connector_type": "google_contacts"}  # Missing user_id!
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(state_data))

        with patch("src.domains.connectors.service.get_redis_session", return_value=mock_redis):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service._handle_oauth_connector_callback_stateless(
                    code=code,
                    state=state,
                    connector_type=ConnectorType.GOOGLE_CONTACTS,
                    provider_factory_method=lambda s: None,
                    default_scopes=None,
                    metadata=None,
                )

        assert exc_info.value.status_code == 400
        assert "missing user_id" in exc_info.value.detail

    async def test_stateless_callback_invalid_user_id_format_raises(self):
        """
        Test stateless callback fails when user_id is not a valid UUID.

        Coverage:
        - Lines 847-858: UUID format validation
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        code = "auth_code_789"
        state = "valid_state_invalid_uuid"

        # Mock Redis to return state data with invalid UUID
        import json

        state_data = {"user_id": "not-a-valid-uuid", "connector_type": "google_contacts"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(state_data))

        with patch("src.domains.connectors.service.get_redis_session", return_value=mock_redis):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await service._handle_oauth_connector_callback_stateless(
                    code=code,
                    state=state,
                    connector_type=ConnectorType.GOOGLE_CONTACTS,
                    provider_factory_method=lambda s: None,
                    default_scopes=None,
                    metadata=None,
                )

        assert exc_info.value.status_code == 400
        assert "Invalid user_id format" in exc_info.value.detail

    async def test_stateless_callback_user_not_found_raises(self):
        """
        Test stateless callback fails when user does not exist in database.

        Coverage:
        - Lines 866-872: User existence validation
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        code = "auth_code_abc"
        state = "valid_state_missing_user"

        # Mock Redis to return valid state data
        import json

        state_data = {"user_id": str(user_id), "connector_type": "google_contacts"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(state_data))

        # Mock UserRepository to return None (user not found)
        with patch("src.domains.connectors.service.get_redis_session", return_value=mock_redis):
            with patch("src.domains.users.repository.UserRepository") as mock_user_repo_class:
                mock_user_repo = MagicMock()
                mock_user_repo.get_by_id = AsyncMock(return_value=None)
                mock_user_repo_class.return_value = mock_user_repo

                # Act & Assert
                with pytest.raises(HTTPException) as exc_info:
                    await service._handle_oauth_connector_callback_stateless(
                        code=code,
                        state=state,
                        connector_type=ConnectorType.GOOGLE_CONTACTS,
                        provider_factory_method=lambda s: None,
                        default_scopes=None,
                        metadata=None,
                    )

        assert exc_info.value.status_code == 404
        mock_user_repo.get_by_id.assert_called_once_with(user_id)

    async def test_stateless_callback_user_inactive_raises(self):
        """
        Test stateless callback fails when user exists but is inactive.

        Coverage:
        - Lines 874-882: User active status validation
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        code = "auth_code_def"
        state = "valid_state_inactive_user"

        # Mock Redis to return valid state data
        import json

        state_data = {"user_id": str(user_id), "connector_type": "google_contacts"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(state_data))

        # Mock UserRepository to return inactive user
        from src.domains.users.models import User

        inactive_user = User(
            id=user_id,
            email="inactive@example.com",
            hashed_password="hashed",
            is_active=False,  # Inactive!
        )

        with patch("src.domains.connectors.service.get_redis_session", return_value=mock_redis):
            with patch("src.domains.users.repository.UserRepository") as mock_user_repo_class:
                mock_user_repo = MagicMock()
                mock_user_repo.get_by_id = AsyncMock(return_value=inactive_user)
                mock_user_repo_class.return_value = mock_user_repo

                # Act & Assert
                with pytest.raises(HTTPException) as exc_info:
                    await service._handle_oauth_connector_callback_stateless(
                        code=code,
                        state=state,
                        connector_type=ConnectorType.GOOGLE_CONTACTS,
                        provider_factory_method=lambda s: None,
                        default_scopes=None,
                        metadata=None,
                    )

        assert exc_info.value.status_code == 403
        mock_user_repo.get_by_id.assert_called_once_with(user_id)

    async def test_stateless_callback_success_delegates(self):
        """
        Test stateless callback successfully delegates after all validations pass.

        Coverage:
        - Lines 884-900: Successful validation delegates to _handle_oauth_connector_callback
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        code = "auth_code_success"
        state = "valid_state_success"

        # Mock Redis to return valid state data
        import json

        state_data = {"user_id": str(user_id), "connector_type": "google_contacts"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(state_data))

        # Mock UserRepository to return active user
        from src.domains.users.models import User

        active_user = User(
            id=user_id,
            email="active@example.com",
            hashed_password="hashed",
            is_active=True,
        )

        expected_response = ConnectorResponse(
            id=uuid4(),
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/contacts.readonly"],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock _handle_oauth_connector_callback
        service._handle_oauth_connector_callback = AsyncMock(return_value=expected_response)

        from src.core.oauth import GoogleOAuthProvider

        with patch("src.domains.connectors.service.get_redis_session", return_value=mock_redis):
            with patch("src.domains.users.repository.UserRepository") as mock_user_repo_class:
                mock_user_repo = MagicMock()
                mock_user_repo.get_by_id = AsyncMock(return_value=active_user)
                mock_user_repo_class.return_value = mock_user_repo

                # Act
                result = await service._handle_oauth_connector_callback_stateless(
                    code=code,
                    state=state,
                    connector_type=ConnectorType.GOOGLE_CONTACTS,
                    provider_factory_method=GoogleOAuthProvider.for_contacts,
                    default_scopes=GOOGLE_CONTACTS_SCOPES,
                    metadata={"created_via": "oauth_flow_stateless"},
                )

        # Assert
        assert result == expected_response

        # Verify delegation with extracted user_id
        service._handle_oauth_connector_callback.assert_called_once_with(
            user_id=user_id,
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            provider_factory_method=GoogleOAuthProvider.for_contacts,
            default_scopes=GOOGLE_CONTACTS_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
            user_email="active@example.com",
        )
        mock_user_repo.get_by_id.assert_called_once_with(user_id)


# ============================================================================
# SESSION 35c: PHASE 4 - GLOBAL CONFIG & REVOCATION TESTS (4 TESTS)
# ============================================================================
# Coverage target: 90.4% → 94-96%
# Lines covered: 989-995, 1043-1048, 1050-1095, 1079-1087


class TestGlobalConfigAndRevocation:
    """
    Tests for global connector configuration and bulk revocation.

    Coverage focus:
    - Lines 989-995: Global config creation path (when no existing config)
    - Lines 1043-1048: Empty revocation list handling
    - Lines 1050-1095: Bulk revocation with email notifications
    - Lines 1079-1087: Email sending with failure handling
    """

    # Test 1: Global config creation path (lines 989-995)
    async def test_update_global_config_create_new(self):
        """
        Test global config creation when no existing config exists.

        Coverage: Lines 989-995 (create new path in update_global_config)
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)
        admin_user_id = uuid4()
        connector_type = ConnectorType.GOOGLE_CONTACTS
        update_data = ConnectorGlobalConfigUpdate(is_enabled=False, disabled_reason="Maintenance")

        # Mock repository methods
        service.repository.get_global_config_by_type = AsyncMock(
            return_value=None
        )  # No existing config
        mock_config = MagicMock()
        mock_config.id = uuid4()  # UUID required by Pydantic
        mock_config.connector_type = connector_type
        mock_config.is_enabled = False
        mock_config.disabled_reason = "Maintenance"
        mock_config.created_at = datetime.now(UTC)
        mock_config.updated_at = datetime.now(UTC)
        service.repository.create_global_config = AsyncMock(return_value=mock_config)
        service.repository.update_global_config = AsyncMock()  # Mock to verify not called
        service._revoke_all_connectors_by_type = AsyncMock()

        # Act
        result = await service.update_global_config(
            admin_user_id=admin_user_id,
            connector_type=connector_type,
            update_data=update_data,
        )

        # Assert
        assert isinstance(result, ConnectorGlobalConfigResponse)
        assert result.is_enabled is False
        assert result.disabled_reason == "Maintenance"

        # Verify create_global_config was called (not update)
        service.repository.create_global_config.assert_called_once_with(
            connector_type=connector_type,
            is_enabled=False,
            disabled_reason="Maintenance",
        )
        service.repository.update_global_config.assert_not_called()

        # Verify revocation was triggered (is_enabled=False)
        service._revoke_all_connectors_by_type.assert_called_once_with(connector_type)

    # Test 2: Empty connector list (lines 1043-1048)
    async def test_revoke_all_connectors_by_type_empty(self):
        """
        Test revocation when no active connectors exist.

        Coverage: Lines 1043-1048 (early return path)
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)
        connector_type = ConnectorType.GOOGLE_CONTACTS

        # Mock repository to return empty list
        service.repository.get_all_connectors_by_type = AsyncMock(return_value=[])
        service.repository.update = AsyncMock()  # Mock to track calls

        # Act
        await service._revoke_all_connectors_by_type(connector_type)

        # Assert
        service.repository.get_all_connectors_by_type.assert_called_once_with(
            connector_type, status=ConnectorStatus.ACTIVE
        )
        # Verify no revocation or email operations occurred (early return)
        service.repository.update.assert_not_called()
        mock_db.commit.assert_not_called()

    # Test 3: Bulk revocation with multiple users (lines 1050-1095)
    @patch("src.domains.connectors.service.get_email_service")
    async def test_revoke_all_connectors_by_type_multiple_users(self, mock_get_email_service):
        """
        Test bulk revocation with email notifications to multiple users.

        Coverage: Lines 1050-1095 (bulk revocation loop + email notifications)
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)
        connector_type = ConnectorType.GOOGLE_CONTACTS

        # Create mock users
        user1_id = uuid4()
        user2_id = uuid4()
        mock_user1 = MagicMock()
        mock_user1.email = "user1@example.com"
        mock_user1.full_name = "User One"
        mock_user2 = MagicMock()
        mock_user2.email = "user2@example.com"
        mock_user2.full_name = "User Two"

        # Create mock connectors
        mock_connector1 = MagicMock()
        mock_connector1.user_id = user1_id
        mock_connector1.user = mock_user1
        mock_connector2 = MagicMock()
        mock_connector2.user_id = user2_id
        mock_connector2.user = mock_user2
        mock_connector3 = MagicMock()  # Same user as connector1
        mock_connector3.user_id = user1_id
        mock_connector3.user = mock_user1

        connectors = [mock_connector1, mock_connector2, mock_connector3]

        # Mock repository methods
        service.repository.get_all_connectors_by_type = AsyncMock(return_value=connectors)
        service.repository.update = AsyncMock()
        mock_global_config = MagicMock()
        mock_global_config.disabled_reason = "Security update"
        service.repository.get_global_config_by_type = AsyncMock(return_value=mock_global_config)

        # Mock _revoke_oauth_token
        service._revoke_oauth_token = AsyncMock()

        # Mock email service
        mock_email_service = AsyncMock()
        mock_email_service.send_connector_disabled_notification = AsyncMock(return_value=True)
        mock_get_email_service.return_value = mock_email_service

        # Act
        await service._revoke_all_connectors_by_type(connector_type)

        # Assert
        # Verify 3 connectors revoked
        assert service._revoke_oauth_token.call_count == 3
        assert service.repository.update.call_count == 3

        # Verify all connectors updated to REVOKED status
        for call_args in service.repository.update.call_args_list:
            # call_args is Call object, args[1] is the update dict (second positional arg)
            assert call_args.args[1] == {FIELD_STATUS: ConnectorStatus.REVOKED}

        # Verify commit called
        mock_db.commit.assert_called_once()

        # Verify 2 emails sent (user1 and user2, not 3 emails for 3 connectors)
        assert mock_email_service.send_connector_disabled_notification.call_count == 2

        # Verify email content
        email_calls = mock_email_service.send_connector_disabled_notification.call_args_list
        emails_sent_to = {call[1]["user_email"] for call in email_calls}
        assert emails_sent_to == {"user1@example.com", "user2@example.com"}

        # Verify reason passed to emails
        for call in email_calls:
            assert call[1]["reason"] == "Security update"
            assert call[1]["connector_type"] == connector_type.value

    # Test 4: Email failure handling (lines 1079-1087)
    @patch("src.domains.connectors.service.get_email_service")
    async def test_revoke_all_connectors_by_type_email_failure_continues(
        self, mock_get_email_service
    ):
        """
        Test that email failures don't stop revocation process.

        Coverage: Lines 1079-1087 (email sending with failure tracking)
        """
        # Arrange
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)
        connector_type = ConnectorType.GOOGLE_CONTACTS

        # Create mock user
        user_id = uuid4()
        mock_user = MagicMock()
        mock_user.email = "user@example.com"
        mock_user.full_name = "User Name"

        # Create mock connector
        mock_connector = MagicMock()
        mock_connector.user_id = user_id
        mock_connector.user = mock_user

        # Mock repository methods
        service.repository.get_all_connectors_by_type = AsyncMock(return_value=[mock_connector])
        service.repository.update = AsyncMock()
        mock_global_config = MagicMock()
        mock_global_config.disabled_reason = "Admin disabled"
        service.repository.get_global_config_by_type = AsyncMock(return_value=mock_global_config)

        # Mock _revoke_oauth_token
        service._revoke_oauth_token = AsyncMock()

        # Mock email service to fail
        mock_email_service = AsyncMock()
        mock_email_service.send_connector_disabled_notification = AsyncMock(
            return_value=False  # Email failed
        )
        mock_get_email_service.return_value = mock_email_service

        # Act
        await service._revoke_all_connectors_by_type(connector_type)

        # Assert
        # Verify connector still revoked despite email failure
        service._revoke_oauth_token.assert_called_once_with(mock_connector)
        service.repository.update.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify email was attempted
        mock_email_service.send_connector_disabled_notification.assert_called_once_with(
            user_email="user@example.com",
            user_name="User Name",
            connector_type=connector_type.value,
            reason="Admin disabled",
        )


# ============================================================================
# BUG #2 FIX VERIFICATION: Safety margin in get_connector_credentials
# ============================================================================


class TestGetConnectorCredentialsSafetyMargin:
    """
    Tests for Bug #2 fix: get_connector_credentials should use safety margin
    (OAUTH_TOKEN_REFRESH_MARGIN_SECONDS) when checking token expiration.
    """

    @pytest.mark.asyncio
    async def test_get_connector_credentials_refreshes_with_safety_margin(self):
        """
        Test that get_connector_credentials triggers refresh when token expires
        within the safety margin (5 minutes), even if not yet expired.

        Bug #2 fix verification: The token should be refreshed preemptively
        when expires_at is less than now + OAUTH_TOKEN_REFRESH_MARGIN_SECONDS.
        """
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Create token that expires in 3 minutes (within 5-minute margin)
        # This should trigger refresh even though token is not yet expired
        credentials_data = {
            "access_token": "about_to_expire_access_token",
            "refresh_token": "refresh_token_123",
            "token_type": "Bearer",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=3)).isoformat(),  # NOT EXPIRED
        }
        encrypted_creds = create_encrypted_credentials(credentials_data)

        # Mock connector with soon-to-expire credentials
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted=encrypted_creds,
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Mock refresh to return new credentials
        new_credentials = ConnectorCredentials(
            access_token="new_access_token",
            refresh_token="refresh_token_123",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        service._refresh_oauth_token = AsyncMock(return_value=new_credentials)

        # Act: Get credentials (should trigger refresh due to safety margin)
        result = await service.get_connector_credentials(user_id, connector_type)

        # Assert: Refresh was triggered (Bug #2 fix)
        assert result is not None
        service._refresh_oauth_token.assert_called_once()
        assert result.access_token == "new_access_token"

    @pytest.mark.asyncio
    async def test_get_connector_credentials_no_refresh_when_valid(self):
        """
        Test that get_connector_credentials does NOT refresh when token
        is valid and outside the safety margin.
        """
        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Create token that expires in 30 minutes (outside 5-minute margin)
        # This should NOT trigger refresh
        credentials_data = {
            "access_token": "valid_access_token",
            "refresh_token": "refresh_token_123",
            "token_type": "Bearer",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        }
        encrypted_creds = create_encrypted_credentials(credentials_data)

        # Mock connector with valid credentials
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted=encrypted_creds,
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Mock refresh (should NOT be called)
        service._refresh_oauth_token = AsyncMock()

        # Act: Get credentials (should NOT trigger refresh)
        result = await service.get_connector_credentials(user_id, connector_type)

        # Assert: No refresh triggered
        assert result is not None
        service._refresh_oauth_token.assert_not_called()
        assert result.access_token == "valid_access_token"

    @pytest.mark.asyncio
    async def test_get_connector_credentials_refreshes_exactly_at_margin_boundary(self):
        """
        Test edge case: token expires exactly at the margin boundary (5 minutes).
        Should still trigger refresh.
        """
        from src.core.constants import OAUTH_TOKEN_REFRESH_MARGIN_SECONDS

        mock_db = AsyncMock()
        service = ConnectorService(mock_db)

        user_id = uuid4()
        connector_type = ConnectorType.GOOGLE_GMAIL

        # Create token that expires exactly at margin boundary (should trigger refresh)
        credentials_data = {
            "access_token": "boundary_access_token",
            "refresh_token": "refresh_token_123",
            "token_type": "Bearer",
            "expires_at": (
                datetime.now(UTC) + timedelta(seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS - 1)
            ).isoformat(),
        }
        encrypted_creds = create_encrypted_credentials(credentials_data)

        # Mock connector
        mock_connector = create_mock_connector(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted=encrypted_creds,
        )
        service.repository.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Mock refresh
        new_credentials = ConnectorCredentials(
            access_token="new_access_token",
            refresh_token="refresh_token_123",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        service._refresh_oauth_token = AsyncMock(return_value=new_credentials)

        # Act
        result = await service.get_connector_credentials(user_id, connector_type)

        # Assert: Refresh triggered at boundary
        assert result is not None
        service._refresh_oauth_token.assert_called_once()
