"""
Integration tests for connectors (external services).
"""

from collections.abc import Sequence
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.security import decrypt_data
from src.domains.connectors import oauth_refresh_targets
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.oauth_refresh_exchange import RefreshedToken, TokenEndpoint
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User
from tests.helpers.committed_users import commit_owner
from tests.helpers.oauth_refresh_io import commit_expired_connector, fresh_token


@pytest.mark.integration
class TestListConnectors:
    """Test listing user connectors."""

    @pytest.mark.asyncio
    async def test_list_own_connectors(
        self, authenticated_client: tuple[AsyncClient, User], async_session
    ):
        """Test listing own connectors."""
        from src.core.security import encrypt_data

        client, user = authenticated_client

        # Create test connector
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data('{"access_token": "test-token"}'),
            metadata={"email": "test@example.com"},
        )
        async_session.add(connector)
        await async_session.commit()

        response = await client.get("/api/v1/connectors")

        assert response.status_code == 200
        data = response.json()

        # API returns structured response with pagination
        assert "connectors" in data
        assert "total" in data
        assert isinstance(data["connectors"], list)
        assert data["total"] >= 1
        assert len(data["connectors"]) >= 1
        assert any(c["connector_type"] == "google_gmail" for c in data["connectors"])

    @pytest.mark.asyncio
    async def test_list_connectors_empty(self, authenticated_client: tuple[AsyncClient, User]):
        """Test listing connectors when user has none."""
        client, _ = authenticated_client

        response = await client.get("/api/v1/connectors")

        assert response.status_code == 200
        data = response.json()

        # API returns structured response with pagination
        assert "connectors" in data
        assert "total" in data
        assert isinstance(data["connectors"], list)
        assert data["total"] == 0
        assert len(data["connectors"]) == 0


@pytest.mark.integration
class TestGetConnector:
    """Test get connector by ID."""

    @pytest.mark.asyncio
    async def test_get_own_connector(
        self, authenticated_client: tuple[AsyncClient, User], async_session
    ):
        """Test getting own connector by ID."""
        from src.core.security import encrypt_data

        client, user = authenticated_client

        # Create test connector
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data('{"access_token": "test-token"}'),
            metadata={"email": "test@example.com"},
        )
        async_session.add(connector)
        await async_session.commit()
        await async_session.refresh(connector)

        response = await client.get(f"/api/v1/connectors/{connector.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(connector.id)
        assert data["connector_type"] == "google_gmail"
        assert data["status"] == "active"
        # Credentials should NOT be exposed in response
        assert "credentials_encrypted" not in data

    @pytest.mark.asyncio
    async def test_get_other_user_connector(
        self, authenticated_client: tuple[AsyncClient, User], test_superuser: User, async_session
    ):
        """Test getting another user's connector (should be forbidden)."""
        from src.core.security import encrypt_data

        client, _ = authenticated_client

        # Create connector for superuser
        connector = Connector(
            user_id=test_superuser.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data('{"access_token": "test-token"}'),
        )
        async_session.add(connector)
        await async_session.commit()
        await async_session.refresh(connector)

        response = await client.get(f"/api/v1/connectors/{connector.id}")

        # API returns 404 for security (doesn't reveal if connector exists but belongs to another user)
        # This is better than 403 which would leak information about existence
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_nonexistent_connector(self, authenticated_client: tuple[AsyncClient, User]):
        """Test getting non-existent connector."""
        client, _ = authenticated_client

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/connectors/{fake_uuid}")

        assert response.status_code == 404


@pytest.mark.integration
class TestCreateConnector:
    """Test creating connectors."""

    @pytest.mark.asyncio
    async def test_initiate_gmail_oauth(self, authenticated_client: tuple[AsyncClient, User]):
        """Test initiating Gmail OAuth flow."""
        client, _ = authenticated_client

        # Correct route is /authorize (GET), not /connect (POST)
        response = await client.get("/api/v1/connectors/gmail/authorize")

        assert response.status_code == 200
        data = response.json()

        assert "authorization_url" in data
        assert "state" in data
        assert "accounts.google.com" in data["authorization_url"]

    @pytest.mark.asyncio
    async def test_gmail_oauth_callback_invalid_state(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """Test Gmail OAuth callback with invalid state."""
        client, _ = authenticated_client

        # Current contract: GET /gmail/callback redirects to the frontend
        # settings page with a connector_error param on failure (302), it
        # does not return a 400 (see handle_oauth_callback_error_redirect).
        response = await client.get(
            "/api/v1/connectors/gmail/callback",
            params={"code": "fake-auth-code", "state": "invalid-state"},
        )

        assert response.status_code == 302
        assert "connector_error=" in response.headers["location"]


@pytest.mark.integration
class TestUpdateConnector:
    """Test updating connectors."""

    @pytest.mark.asyncio
    async def test_update_connector_status(
        self, authenticated_client: tuple[AsyncClient, User], async_session
    ):
        """Test updating connector status."""
        from src.core.security import encrypt_data

        client, user = authenticated_client

        # Create test connector
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data('{"access_token": "test-token"}'),
        )
        async_session.add(connector)
        await async_session.commit()
        await async_session.refresh(connector)

        response = await client.patch(
            f"/api/v1/connectors/{connector.id}",
            json={"status": "inactive"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_update_connector_metadata(
        self, authenticated_client: tuple[AsyncClient, User], async_session
    ):
        """Test updating connector metadata."""
        from src.core.security import encrypt_data

        client, user = authenticated_client

        # Create test connector
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data('{"access_token": "test-token"}'),
            metadata={"email": "old@example.com"},
        )
        async_session.add(connector)
        await async_session.commit()
        await async_session.refresh(connector)

        response = await client.patch(
            f"/api/v1/connectors/{connector.id}",
            json={"metadata": {"email": "new@example.com", "custom": "value"}},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["metadata"]["email"] == "new@example.com"
        assert data["metadata"]["custom"] == "value"


@pytest.mark.integration
class TestDeleteConnector:
    """Test deleting connectors."""

    @pytest.mark.asyncio
    async def test_delete_own_connector(
        self, authenticated_client: tuple[AsyncClient, User], async_session
    ):
        """Test deleting own connector."""
        from src.core.security import encrypt_data

        client, user = authenticated_client

        # Create test connector
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data('{"access_token": "test-token"}'),
        )
        async_session.add(connector)
        await async_session.commit()
        await async_session.refresh(connector)

        response = await client.delete(f"/api/v1/connectors/{connector.id}")

        assert response.status_code == 204

        # Verify connector is deleted
        get_response = await client.get(f"/api/v1/connectors/{connector.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_user_connector(
        self, authenticated_client: tuple[AsyncClient, User], test_superuser: User, async_session
    ):
        """Test deleting another user's connector (should be forbidden)."""
        from src.core.security import encrypt_data

        client, _ = authenticated_client

        # Create connector for superuser
        connector = Connector(
            user_id=test_superuser.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data('{"access_token": "test-token"}'),
        )
        async_session.add(connector)
        await async_session.commit()
        await async_session.refresh(connector)

        response = await client.delete(f"/api/v1/connectors/{connector.id}")

        # API returns 404 for security (doesn't reveal if connector exists but belongs to another user)
        assert response.status_code == 404


@pytest.mark.integration
class TestConnectorRefresh:
    """A manual refresh goes through the one refresh door (audit AC-029).

    The door reads and writes on sessions of its own, so the connector is
    COMMITTED: a row only the test's transaction holds is, to the door, absent —
    it answered 403 « not authorized » for it. The provider exchange is scripted:
    no request leaves the test.
    """

    async def test_a_manual_refresh_stores_the_token_the_provider_issued(
        self,
        async_engine: AsyncEngine,
        committed_user_ids: list[UUID],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        owner = await commit_owner(async_engine, committed_user_ids)
        connector = await commit_expired_connector(async_engine, owner)
        exchanged: list[str] = []

        async def provider(
            endpoint: TokenEndpoint,
            *,
            refresh_token: str,
            scopes: Sequence[str],
            owner_id: UUID | None,
        ) -> RefreshedToken:
            exchanged.append(refresh_token)
            return fresh_token("manually-refreshed")

        monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", provider)

        async with AsyncSession(async_engine) as db:
            response = await ConnectorService(db).refresh_connector_credentials(owner, connector.id)

        async with AsyncSession(async_engine) as db:
            row = await db.get(Connector, connector.id)
        assert row is not None
        stored = ConnectorCredentials.model_validate_json(decrypt_data(row.credentials_encrypted))
        assert exchanged == ["refresh-1"]
        assert stored.access_token == "manually-refreshed"
        assert response.id == connector.id and response.status == ConnectorStatus.ACTIVE


@pytest.mark.integration
class TestConnectorTypes:
    """Test different connector types."""

    @pytest.mark.asyncio
    async def test_list_supported_connector_types(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """Test listing supported connector types."""
        client, _ = authenticated_client

        response = await client.get("/api/v1/connectors/types")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        assert "google_gmail" in data
        assert "google_drive" in data
        assert "google_calendar" in data
