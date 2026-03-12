"""Tests for UserMCPServerService business logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServerStatus
from src.domains.user_mcp.schemas import UserMCPServerCreate
from src.domains.user_mcp.service import UserMCPServerService


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create service with mocked dependencies."""
    svc = UserMCPServerService(mock_db)
    svc.repository = AsyncMock()
    # Default: no existing server with same name (uniqueness check passes)
    svc.repository.get_by_name_for_user = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def sample_server():
    """Create a mock UserMCPServer instance."""
    server = MagicMock()
    server.id = uuid4()
    server.user_id = uuid4()
    server.name = "Test Server"
    server.url = "https://mcp.example.com/sse"
    server.auth_type = UserMCPAuthType.NONE.value
    server.credentials_encrypted = None
    server.status = UserMCPServerStatus.ACTIVE.value
    server.is_enabled = True
    server.timeout_seconds = 30
    server.hitl_required = None
    return server


class TestOwnershipCheck:
    """Tests for ownership verification."""

    @pytest.mark.asyncio
    async def test_valid_ownership(self, service, sample_server) -> None:
        """Should return server when user matches."""
        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        result = await service.get_with_ownership_check(sample_server.id, sample_server.user_id)
        assert result == sample_server

    @pytest.mark.asyncio
    async def test_wrong_user_raises(self, service, sample_server) -> None:
        """Should raise ResourceNotFoundError for wrong user."""
        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        from src.core.exceptions import ResourceNotFoundError

        with pytest.raises(ResourceNotFoundError):
            await service.get_with_ownership_check(sample_server.id, uuid4())

    @pytest.mark.asyncio
    async def test_nonexistent_server_raises(self, service) -> None:
        """Should raise ResourceNotFoundError for missing server."""
        service.repository.get_by_id = AsyncMock(return_value=None)
        from src.core.exceptions import ResourceNotFoundError

        with pytest.raises(ResourceNotFoundError):
            await service.get_with_ownership_check(uuid4(), uuid4())


class TestCreateServer:
    """Tests for server creation."""

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_create_none_auth(self, mock_validate, service) -> None:
        """Should create server with no auth successfully."""
        mock_validate.return_value = (True, None)
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(return_value=MagicMock())

        user_id = uuid4()
        data = UserMCPServerCreate(
            name="Test",
            url="https://mcp.example.com/sse",
            auth_type=UserMCPAuthType.NONE,
        )

        await service.create_server(user_id, data)
        service.repository.create.assert_called_once()
        call_args = service.repository.create.call_args[0][0]
        assert call_args["credentials_encrypted"] is None
        assert call_args["status"] == "active"

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    @patch("src.domains.user_mcp.service.encrypt_data")
    async def test_create_api_key_encrypts(self, mock_encrypt, mock_validate, service) -> None:
        """Should encrypt API key credentials on creation."""
        mock_validate.return_value = (True, None)
        mock_encrypt.return_value = "encrypted_creds"
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(return_value=MagicMock())

        data = UserMCPServerCreate(
            name="API Test",
            url="https://mcp.example.com/sse",
            auth_type=UserMCPAuthType.API_KEY,
            api_key="sk-test-123",
            header_name="X-Custom",
        )

        await service.create_server(uuid4(), data)

        # Verify encrypt_data was called with JSON containing creds
        mock_encrypt.assert_called_once()
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["api_key"] == "sk-test-123"
        assert encrypted_json["header_name"] == "X-Custom"

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_create_oauth2_sets_auth_required(self, mock_validate, service) -> None:
        """Should set initial status to auth_required for OAuth2."""
        mock_validate.return_value = (True, None)
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(return_value=MagicMock())

        data = UserMCPServerCreate(
            name="OAuth Test",
            url="https://mcp.example.com/sse",
            auth_type=UserMCPAuthType.OAUTH2,
        )

        await service.create_server(uuid4(), data)
        call_args = service.repository.create.call_args[0][0]
        assert call_args["status"] == "auth_required"

    @pytest.mark.asyncio
    async def test_create_exceeds_limit(self, service) -> None:
        """Should reject creation when user has reached the max limit."""
        service.repository.count_for_user = AsyncMock(return_value=5)
        from src.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Maximum of"):
            await service.create_server(
                uuid4(),
                UserMCPServerCreate(
                    name="Test",
                    url="https://mcp.example.com/sse",
                ),
            )

    @pytest.mark.asyncio
    async def test_create_duplicate_name_raises(self, service) -> None:
        """Should reject creation when name already exists for user."""
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.get_by_name_for_user = AsyncMock(return_value=MagicMock())
        from src.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="already exists"):
            await service.create_server(
                uuid4(),
                UserMCPServerCreate(
                    name="Existing Server",
                    url="https://mcp.example.com/sse",
                ),
            )

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_create_invalid_url(self, mock_validate, service) -> None:
        """Should reject invalid URL (SSRF prevention)."""
        mock_validate.return_value = (False, "SSRF: private IP range")
        service.repository.count_for_user = AsyncMock(return_value=0)
        from src.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="Invalid MCP server URL"):
            await service.create_server(
                uuid4(),
                UserMCPServerCreate(
                    name="Test",
                    url="https://192.168.1.1:8080/sse",
                ),
            )


class TestToggleServer:
    """Tests for server toggle."""

    @pytest.mark.asyncio
    async def test_toggle_disable(self, service, sample_server) -> None:
        """Should disable server and disconnect from pool."""
        sample_server.is_enabled = True
        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        service.repository.update = AsyncMock(return_value=sample_server)

        with patch.object(
            UserMCPServerService, "_disconnect_from_pool", new_callable=AsyncMock
        ) as mock_disconnect:
            await service.toggle_server(sample_server.id, sample_server.user_id)
            mock_disconnect.assert_called_once_with(sample_server.user_id, sample_server.id)

    @pytest.mark.asyncio
    async def test_toggle_enable(self, service, sample_server) -> None:
        """Should enable server without disconnecting."""
        sample_server.is_enabled = False
        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        service.repository.update = AsyncMock(return_value=sample_server)

        with patch.object(
            UserMCPServerService, "_disconnect_from_pool", new_callable=AsyncMock
        ) as mock_disconnect:
            await service.toggle_server(sample_server.id, sample_server.user_id)
            mock_disconnect.assert_not_called()


class TestDeleteServer:
    """Tests for server deletion."""

    @pytest.mark.asyncio
    async def test_delete_disconnects_first(self, service, sample_server) -> None:
        """Should disconnect from pool BEFORE deleting from DB."""
        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        service.repository.delete = AsyncMock()
        call_order = []

        with patch.object(
            UserMCPServerService,
            "_disconnect_from_pool",
            new_callable=AsyncMock,
            side_effect=lambda *a: call_order.append("disconnect"),
        ):
            service.repository.delete.side_effect = lambda *a: call_order.append("delete")
            await service.delete_server(sample_server.id, sample_server.user_id)
            assert call_order == ["disconnect", "delete"]


class TestEncryptCredentials:
    """Tests for credential encryption helpers."""

    @patch("src.domains.user_mcp.service.encrypt_data")
    def test_encrypt_api_key(self, mock_encrypt) -> None:
        """Should encrypt API key with header name."""
        mock_encrypt.return_value = "encrypted"
        data = UserMCPServerCreate(
            name="Test",
            url="https://example.com",
            auth_type=UserMCPAuthType.API_KEY,
            api_key="sk-123",
        )
        result = UserMCPServerService._encrypt_credentials(data)
        assert result == "encrypted"
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["header_name"] == "X-API-Key"  # default
        assert encrypted_json["api_key"] == "sk-123"

    @patch("src.domains.user_mcp.service.encrypt_data")
    def test_encrypt_bearer(self, mock_encrypt) -> None:
        """Should encrypt Bearer token."""
        mock_encrypt.return_value = "encrypted"
        data = UserMCPServerCreate(
            name="Test",
            url="https://example.com",
            auth_type=UserMCPAuthType.BEARER,
            bearer_token="eyJ-test",
        )
        result = UserMCPServerService._encrypt_credentials(data)
        assert result == "encrypted"

    def test_encrypt_none_returns_none(self) -> None:
        """Should return None for 'none' auth type."""
        data = UserMCPServerCreate(
            name="Test",
            url="https://example.com",
            auth_type=UserMCPAuthType.NONE,
        )
        result = UserMCPServerService._encrypt_credentials(data)
        assert result is None


class TestEncryptCredentialsFromUpdate:
    """Tests for _encrypt_credentials_from_update merge behavior."""

    @patch("src.domains.user_mcp.service.encrypt_data")
    @patch("src.domains.user_mcp.service.decrypt_data")
    def test_merge_header_name_only(self, mock_decrypt, mock_encrypt) -> None:
        """Should merge new header_name with existing api_key from encrypted blob."""
        # Existing credentials: api_key="sk-123", header_name="X-API-Key"
        mock_decrypt.return_value = json.dumps(
            {
                "header_name": "X-API-Key",
                "api_key": "sk-123",
            }
        )
        mock_encrypt.return_value = "re-encrypted"

        server = MagicMock()
        server.credentials_encrypted = "old_encrypted"

        update_data = {"header_name": "X-Hf-Token"}

        result = UserMCPServerService._encrypt_credentials_from_update(
            update_data, UserMCPAuthType.API_KEY.value, server
        )
        assert result == "re-encrypted"
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["api_key"] == "sk-123"  # preserved from existing
        assert encrypted_json["header_name"] == "X-Hf-Token"  # updated

    @patch("src.domains.user_mcp.service.encrypt_data")
    @patch("src.domains.user_mcp.service.decrypt_data")
    def test_merge_api_key_preserves_header(self, mock_decrypt, mock_encrypt) -> None:
        """Should preserve existing header_name when only api_key changes."""
        mock_decrypt.return_value = json.dumps(
            {
                "header_name": "X-Custom",
                "api_key": "old-key",
            }
        )
        mock_encrypt.return_value = "re-encrypted"

        server = MagicMock()
        server.credentials_encrypted = "old_encrypted"

        update_data = {"api_key": "new-key"}

        result = UserMCPServerService._encrypt_credentials_from_update(
            update_data, UserMCPAuthType.API_KEY.value, server
        )
        assert result == "re-encrypted"
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["api_key"] == "new-key"  # updated
        assert encrypted_json["header_name"] == "X-Custom"  # preserved

    @patch("src.domains.user_mcp.service.encrypt_data")
    @patch("src.domains.user_mcp.service.decrypt_data")
    def test_merge_both_api_key_and_header(self, mock_decrypt, mock_encrypt) -> None:
        """Should use both new values when both are provided."""
        mock_decrypt.return_value = json.dumps(
            {
                "header_name": "X-Old",
                "api_key": "old-key",
            }
        )
        mock_encrypt.return_value = "re-encrypted"

        server = MagicMock()
        server.credentials_encrypted = "old_encrypted"

        update_data = {"api_key": "new-key", "header_name": "X-New"}

        UserMCPServerService._encrypt_credentials_from_update(
            update_data, UserMCPAuthType.API_KEY.value, server
        )
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["api_key"] == "new-key"
        assert encrypted_json["header_name"] == "X-New"

    def test_no_api_key_available_returns_existing(self) -> None:
        """Should return existing encrypted blob when no api_key in update or existing."""
        server = MagicMock()
        server.credentials_encrypted = None

        update_data = {"header_name": "X-Custom"}

        result = UserMCPServerService._encrypt_credentials_from_update(
            update_data, UserMCPAuthType.API_KEY.value, server
        )
        assert result is None  # server.credentials_encrypted was None

    @patch("src.domains.user_mcp.service.encrypt_data")
    @patch("src.domains.user_mcp.service.decrypt_data")
    def test_bearer_merge_preserves_existing_token(self, mock_decrypt, mock_encrypt) -> None:
        """Should preserve existing bearer token when no new token provided."""
        mock_decrypt.return_value = json.dumps({"token": "existing-token"})
        mock_encrypt.return_value = "re-encrypted"

        server = MagicMock()
        server.credentials_encrypted = "old_encrypted"

        # Update with auth_type change but no new bearer_token
        update_data: dict = {}

        result = UserMCPServerService._encrypt_credentials_from_update(
            update_data, UserMCPAuthType.BEARER.value, server
        )
        assert result == "re-encrypted"
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["token"] == "existing-token"

    @patch("src.domains.user_mcp.service.encrypt_data")
    @patch("src.domains.user_mcp.service.decrypt_data")
    def test_oauth2_merge_new_client_credentials(self, mock_decrypt, mock_encrypt) -> None:
        """Should merge new client_id/client_secret into existing OAuth credentials."""
        mock_decrypt.return_value = json.dumps(
            {
                "client_id": "old-client",
                "client_secret": "old-secret",
                "access_token": "tok-abc",
                "refresh_token": "ref-xyz",
            }
        )
        mock_encrypt.return_value = "re-encrypted"

        server = MagicMock()
        server.credentials_encrypted = "old_encrypted"

        update_data = {
            "oauth_client_id": "new-client",
            "oauth_client_secret": "new-secret",
        }

        result = UserMCPServerService._encrypt_credentials_from_update(
            update_data, UserMCPAuthType.OAUTH2.value, server
        )
        assert result == "re-encrypted"
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["client_id"] == "new-client"
        assert encrypted_json["client_secret"] == "new-secret"
        # Existing OAuth tokens must be preserved
        assert encrypted_json["access_token"] == "tok-abc"
        assert encrypted_json["refresh_token"] == "ref-xyz"

    @patch("src.domains.user_mcp.service.encrypt_data")
    @patch("src.domains.user_mcp.service.decrypt_data")
    def test_oauth2_preserves_existing_when_no_new_creds(self, mock_decrypt, mock_encrypt) -> None:
        """Should keep existing credentials when no new client_id provided."""
        mock_decrypt.return_value = json.dumps(
            {"client_id": "existing-id", "client_secret": "existing-secret"}
        )
        mock_encrypt.return_value = "re-encrypted"

        server = MagicMock()
        server.credentials_encrypted = "old_encrypted"

        # Update with no OAuth fields (e.g. just changing name)
        update_data: dict = {}

        result = UserMCPServerService._encrypt_credentials_from_update(
            update_data, UserMCPAuthType.OAUTH2.value, server
        )
        assert result == "re-encrypted"
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json["client_id"] == "existing-id"
        assert encrypted_json["client_secret"] == "existing-secret"

    def test_oauth2_no_existing_no_new_returns_existing(self) -> None:
        """Should return existing blob when no client_id in update or existing creds."""
        server = MagicMock()
        server.credentials_encrypted = None

        result = UserMCPServerService._encrypt_credentials_from_update(
            {}, UserMCPAuthType.OAUTH2.value, server
        )
        assert result is None

    def test_switch_to_none_clears_credentials(self) -> None:
        """Should return None when switching to auth_type 'none'."""
        server = MagicMock()
        server.credentials_encrypted = "old_encrypted"

        result = UserMCPServerService._encrypt_credentials_from_update(
            {}, UserMCPAuthType.NONE.value, server
        )
        assert result is None


class TestCreateServerDomainDescription:
    """Tests for domain_description in create_server."""

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_create_passes_domain_description(self, mock_validate, service) -> None:
        """Should pass domain_description to repository.create."""
        mock_validate.return_value = (True, None)
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(return_value=MagicMock())

        data = UserMCPServerCreate(
            name="HF Server",
            url="https://mcp.example.com/sse",
            domain_description="Search ML models on HuggingFace Hub",
        )
        await service.create_server(uuid4(), data)

        call_args = service.repository.create.call_args[0][0]
        assert call_args["domain_description"] == "Search ML models on HuggingFace Hub"

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_create_passes_none_domain_description(self, mock_validate, service) -> None:
        """Should pass None domain_description when not provided."""
        mock_validate.return_value = (True, None)
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(return_value=MagicMock())

        data = UserMCPServerCreate(
            name="Test",
            url="https://mcp.example.com/sse",
        )
        await service.create_server(uuid4(), data)

        call_args = service.repository.create.call_args[0][0]
        assert call_args["domain_description"] is None


class TestDisconnectOAuth:
    """Tests for disconnect_oauth method."""

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.encrypt_data")
    @patch("src.domains.user_mcp.service.decrypt_data")
    async def test_disconnect_purges_tokens_keeps_client_creds(
        self, mock_decrypt, mock_encrypt, service, sample_server
    ) -> None:
        """Should remove OAuth tokens but preserve client_id/client_secret."""
        sample_server.auth_type = UserMCPAuthType.OAUTH2.value
        sample_server.status = UserMCPServerStatus.ACTIVE.value
        sample_server.credentials_encrypted = "encrypted_blob"
        mock_decrypt.return_value = json.dumps(
            {
                "client_id": "my-client",
                "client_secret": "my-secret",
                "access_token": "tok-abc",
                "refresh_token": "ref-xyz",
                "expires_at": 1234567890,
            }
        )
        mock_encrypt.return_value = "re-encrypted-client-only"

        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        service.repository.update = AsyncMock(return_value=sample_server)

        with patch.object(
            UserMCPServerService, "_disconnect_from_pool", new_callable=AsyncMock
        ) as mock_disconnect:
            await service.disconnect_oauth(sample_server.id, sample_server.user_id)
            mock_disconnect.assert_called_once()

        # Verify only client credentials are re-encrypted
        encrypted_json = json.loads(mock_encrypt.call_args[0][0])
        assert encrypted_json == {"client_id": "my-client", "client_secret": "my-secret"}
        assert "access_token" not in encrypted_json
        assert "refresh_token" not in encrypted_json

        # Verify status set to auth_required
        update_call = service.repository.update.call_args[0][1]
        assert update_call["status"] == UserMCPServerStatus.AUTH_REQUIRED.value
        assert update_call["credentials_encrypted"] == "re-encrypted-client-only"

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.decrypt_data")
    async def test_disconnect_no_client_creds_clears_all(
        self, mock_decrypt, service, sample_server
    ) -> None:
        """Should set credentials to None when no client_id/client_secret exist."""
        sample_server.auth_type = UserMCPAuthType.OAUTH2.value
        sample_server.credentials_encrypted = "encrypted_blob"
        mock_decrypt.return_value = json.dumps(
            {"access_token": "tok-abc", "refresh_token": "ref-xyz"}
        )

        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        service.repository.update = AsyncMock(return_value=sample_server)

        with patch.object(UserMCPServerService, "_disconnect_from_pool", new_callable=AsyncMock):
            await service.disconnect_oauth(sample_server.id, sample_server.user_id)

        update_call = service.repository.update.call_args[0][1]
        assert update_call["credentials_encrypted"] is None
        assert update_call["status"] == UserMCPServerStatus.AUTH_REQUIRED.value

    @pytest.mark.asyncio
    async def test_disconnect_non_oauth_raises(self, service, sample_server) -> None:
        """Should raise ValidationError for non-OAuth servers."""
        sample_server.auth_type = UserMCPAuthType.API_KEY.value
        service.repository.get_by_id = AsyncMock(return_value=sample_server)

        from src.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="oauth2"):
            await service.disconnect_oauth(sample_server.id, sample_server.user_id)


class TestUpdateToolEmbeddings:
    """Tests for update_tool_embeddings method."""

    @pytest.mark.asyncio
    async def test_update_tool_embeddings(self, service, sample_server) -> None:
        """Should update tool_embeddings_cache via repository."""
        service.repository.get_by_id = AsyncMock(return_value=sample_server)
        service.repository.update = AsyncMock(return_value=sample_server)

        embeddings = {"tool_a": {"description": [0.1, 0.2], "keywords": [[0.3, 0.4]]}}
        await service.update_tool_embeddings(sample_server.id, sample_server.user_id, embeddings)

        service.repository.update.assert_called_once_with(
            sample_server, {"tool_embeddings_cache": embeddings}
        )
