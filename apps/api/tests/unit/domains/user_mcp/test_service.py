"""Tests for UserMCPServerService business logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.user_mcp.models import (
    UserMCPAuthType,
    UserMCPServer,
    UserMCPServerStatus,
    UserMCPTestErrorCode,
)
from src.domains.user_mcp.schemas import UserMCPServerCreate, UserMCPServerUpdate
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
    server.plugin_id = None
    server.extra_headers = None
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
        from src.core.config import settings
        from src.core.exceptions import ValidationError

        # Mock the user count strictly above the configured per-user cap so the
        # assertion stays correct regardless of the env-driven default.
        max_servers = settings.mcp_user_max_servers_per_user
        service.repository.count_for_user = AsyncMock(return_value=max_servers)

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


class TestUpdateServerCredentials:
    """What update_server writes: credential_transition's decision, nothing else."""

    @staticmethod
    def _row(auth_type: UserMCPAuthType, status: UserMCPServerStatus) -> UserMCPServer:
        return UserMCPServer(
            id=uuid4(),
            user_id=uuid4(),
            name="Notes",
            url="https://notes.example/mcp",
            auth_type=auth_type.value,
            status=status.value,
            credentials_encrypted="stored-ciphertext",
            oauth_metadata=None,
            required_header_name=None,
            last_error="Server returned an error response",
        )

    @staticmethod
    def _wire(
        service: UserMCPServerService, row: UserMCPServer, stored: dict[str, object]
    ) -> AsyncMock:
        service.repository.get_by_id = AsyncMock(return_value=row)
        service.repository.update = AsyncMock(return_value=row)
        service._decrypt_existing_credentials = MagicMock(return_value=stored)
        return service.repository.update

    @pytest.mark.asyncio
    async def test_switch_to_oauth_awaits_authorization(self, service) -> None:
        row = self._row(UserMCPAuthType.API_KEY, UserMCPServerStatus.ERROR)
        update = self._wire(service, row, {"header_name": "X-API-Key", "api_key": "sk-123"})
        with patch.object(UserMCPServerService, "_disconnect_from_pool", new_callable=AsyncMock):
            await service.update_server(
                row.id, row.user_id, UserMCPServerUpdate(auth_type=UserMCPAuthType.OAUTH2)
            )
        written = update.call_args[0][1]
        assert written["auth_type"] == UserMCPAuthType.OAUTH2.value
        assert written["credentials_encrypted"] is None
        assert written["status"] == UserMCPServerStatus.AUTH_REQUIRED.value
        assert written["last_error"] is None

    @pytest.mark.asyncio
    async def test_switch_to_api_key_without_key_writes_nothing(self, service) -> None:
        from src.core.exceptions import ValidationError

        row = self._row(UserMCPAuthType.OAUTH2, UserMCPServerStatus.ACTIVE)
        update = self._wire(service, row, {"client_id": "c", "access_token": "tok"})
        before_write = AsyncMock()
        with pytest.raises(ValidationError):
            await service.update_server(
                row.id,
                row.user_id,
                UserMCPServerUpdate(auth_type=UserMCPAuthType.API_KEY),
                before_write=before_write,
            )
        before_write.assert_not_awaited()
        update.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.encrypt_data", return_value="client-only")
    @patch(
        "src.domains.user_mcp.service.validate_http_endpoint",
        new_callable=AsyncMock,
        return_value=(True, None),
    )
    async def test_new_address_of_an_oauth_server_drops_its_tokens(
        self, _validate, mock_encrypt, service
    ) -> None:
        row = self._row(UserMCPAuthType.OAUTH2, UserMCPServerStatus.ACTIVE)
        row.oauth_metadata = {
            "issuer": "https://auth.example",
            "authorization_endpoint": "https://auth.example/authorize",
            "token_endpoint": "https://auth.example/token",
            "requested_scopes": "read",
        }
        stored = {"client_id": "client-1", "access_token": "tok", "refresh_token": "ref"}
        update = self._wire(service, row, stored)
        with patch.object(UserMCPServerService, "_disconnect_from_pool", new_callable=AsyncMock):
            await service.update_server(
                row.id, row.user_id, UserMCPServerUpdate(url="https://other.example/mcp")
            )
        assert json.loads(mock_encrypt.call_args[0][0]) == {"client_id": "client-1"}
        written = update.call_args[0][1]
        assert written["credentials_encrypted"] == "client-only"
        assert written["status"] == UserMCPServerStatus.AUTH_REQUIRED.value
        # The endpoints were found for the old address: only the person's scopes stay.
        assert written["oauth_metadata"] == {"requested_scopes": "read"}

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.encrypt_data", return_value="client-only")
    @patch(
        "src.domains.user_mcp.service.validate_http_endpoint",
        new_callable=AsyncMock,
        return_value=(True, None),
    )
    async def test_new_address_and_scopes_together_keep_the_new_scopes(
        self, _validate, _encrypt, service
    ) -> None:
        row = self._row(UserMCPAuthType.OAUTH2, UserMCPServerStatus.ACTIVE)
        row.oauth_metadata = {"token_endpoint": "https://auth.example/token"}
        update = self._wire(service, row, {"client_id": "client-1", "access_token": "tok"})
        with patch.object(UserMCPServerService, "_disconnect_from_pool", new_callable=AsyncMock):
            await service.update_server(
                row.id,
                row.user_id,
                UserMCPServerUpdate(url="https://other.example/mcp", oauth_scopes="read write"),
            )
        assert update.call_args[0][1]["oauth_metadata"] == {"requested_scopes": "read write"}

    @pytest.mark.asyncio
    async def test_unrelated_update_leaves_credentials_and_status(self, service) -> None:
        row = self._row(UserMCPAuthType.OAUTH2, UserMCPServerStatus.ERROR)
        update = self._wire(service, row, {"client_id": "c", "access_token": "tok"})
        await service.update_server(row.id, row.user_id, UserMCPServerUpdate(timeout_seconds=90))
        written = update.call_args[0][1]
        assert written == {"timeout_seconds": 90}


class TestConnectionAwaitingAuthorization:
    """An OAuth server awaiting its authorization is never contacted, and stays auth_required."""

    @staticmethod
    def _row(status: UserMCPServerStatus) -> UserMCPServer:
        return UserMCPServer(
            id=uuid4(),
            user_id=uuid4(),
            name="Notes",
            url="https://notes.example/mcp",
            auth_type=UserMCPAuthType.OAUTH2.value,
            status=status.value,
            timeout_seconds=30,
        )

    @staticmethod
    def _pool(failure: BaseException | None = None) -> MagicMock:
        pool = MagicMock()
        pool.get_or_connect = AsyncMock(side_effect=failure)
        return pool

    async def _test(
        self, service: UserMCPServerService, row: UserMCPServer, stored: dict, pool: MagicMock
    ) -> tuple[dict, dict]:
        service.repository.get_by_id = AsyncMock(return_value=row)
        service.repository.update = AsyncMock(return_value=row)
        service._decrypt_existing_credentials = MagicMock(return_value=stored)
        with (
            patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool),
            patch("src.infrastructure.mcp.auth.build_auth_for_server", return_value=object()),
        ):
            result = await service.test_connection(row.id, row.user_id)
        return result, service.repository.update.call_args[0][1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "stored"),
        [
            (UserMCPServerStatus.ERROR, {}),
            (UserMCPServerStatus.ACTIVE, {"client_id": "client-1"}),
            (UserMCPServerStatus.AUTH_REQUIRED, {"client_id": "c", "access_token": "tok"}),
        ],
    )
    async def test_not_contacted_before_authorization(
        self, service, status: UserMCPServerStatus, stored: dict
    ) -> None:
        pool = self._pool()
        result, written = await self._test(service, self._row(status), stored, pool)
        pool.get_or_connect.assert_not_awaited()
        assert result["success"] is False
        assert result["error_code"] == UserMCPTestErrorCode.OAUTH_AUTHORIZATION_REQUIRED.value
        assert written == {"status": UserMCPServerStatus.AUTH_REQUIRED.value, "last_error": None}

    @pytest.mark.asyncio
    async def test_token_refused_while_testing_keeps_auth_required(self, service) -> None:
        from src.infrastructure.mcp.utils import MCPAuthRequiredError

        pool = self._pool(MCPAuthRequiredError("Notes"))
        stored = {"client_id": "c", "access_token": "tok"}
        result, written = await self._test(
            service, self._row(UserMCPServerStatus.ACTIVE), stored, pool
        )
        pool.get_or_connect.assert_awaited_once()
        assert result["error_code"] == UserMCPTestErrorCode.OAUTH_AUTHORIZATION_REQUIRED.value
        assert written["status"] == UserMCPServerStatus.AUTH_REQUIRED.value

    @pytest.mark.asyncio
    async def test_any_other_failure_is_an_error(self, service) -> None:
        pool = self._pool(RuntimeError("boom"))
        stored = {"client_id": "c", "access_token": "tok"}
        result, written = await self._test(
            service, self._row(UserMCPServerStatus.ACTIVE), stored, pool
        )
        assert result["error"] == "Connection failed: RuntimeError"
        assert "error_code" not in result
        assert written["status"] == UserMCPServerStatus.ERROR.value


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


class TestCreateServerIterativeMode:
    """Regression tests for iterative_mode in create_server (2026-07 audit, wave 1).

    create_server used to omit iterative_mode from the repository dict, so the
    column always kept its False default regardless of the request payload.
    """

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_create_passes_iterative_mode_true(self, mock_validate, service) -> None:
        """Should pass iterative_mode=True to repository.create."""
        mock_validate.return_value = (True, None)
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(return_value=MagicMock())

        data = UserMCPServerCreate(
            name="ReAct Server",
            url="https://mcp.example.com/sse",
            iterative_mode=True,
        )
        await service.create_server(uuid4(), data)

        call_args = service.repository.create.call_args[0][0]
        assert call_args["iterative_mode"] is True

    @pytest.mark.asyncio
    @patch("src.domains.user_mcp.service.validate_http_endpoint", new_callable=AsyncMock)
    async def test_create_defaults_iterative_mode_false(self, mock_validate, service) -> None:
        """Should pass iterative_mode=False when not provided."""
        mock_validate.return_value = (True, None)
        service.repository.count_for_user = AsyncMock(return_value=0)
        service.repository.create = AsyncMock(return_value=MagicMock())

        data = UserMCPServerCreate(
            name="Plain Server",
            url="https://mcp.example.com/sse",
        )
        await service.create_server(uuid4(), data)

        call_args = service.repository.create.call_args[0][0]
        assert call_args["iterative_mode"] is False


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


class TestDescriptionGenerationKnowsAuthentication:
    """The description generator must know whether calls carry the user's
    own credential (2026-09-02): fed only tool names, it described an
    authenticated GitHub server as "public GitHub repositories", and the
    model rationally asked the user for a username instead of reading "my"
    as the connected account.
    """

    @pytest.fixture(autouse=True)
    def _no_operator_ceiling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No daily ceiling is set (the operator setting's declared default).

        The generator asks the spend ceilings before calling the model; the real
        read of the operator's ceiling would reach the settings store.
        """
        monkeypatch.setattr(
            "src.domains.system_settings.service.get_instance_daily_budget_eur",
            AsyncMock(return_value=None),
        )

    def _llm(self):
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(return_value=MagicMock(content="A fine description."))
        return llm

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.get_llm")
    async def test_account_scoped_server_declares_it_to_the_generator(
        self, mock_get_llm, service
    ) -> None:
        llm = self._llm()
        mock_get_llm.return_value = llm

        await service._llm_generate_description(
            tool_list=[{"name": "search_repositories", "description": "Search repos"}],
            server_name="Github",
            account_scoped=True,
        )

        human = llm.ainvoke.call_args[0][0][1].content
        assert "user's own account" in human

    @pytest.mark.asyncio
    @patch("src.infrastructure.llm.get_llm")
    async def test_anonymous_server_declares_no_authentication(self, mock_get_llm, service) -> None:
        llm = self._llm()
        mock_get_llm.return_value = llm

        await service._llm_generate_description(
            tool_list=[{"name": "get_price", "description": "Get price"}],
            server_name="Coingecko",
            account_scoped=False,
        )

        human = llm.ainvoke.call_args[0][0][1].content
        assert "own account" not in human
