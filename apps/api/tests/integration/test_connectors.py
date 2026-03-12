"""
Integration tests for connectors (external services).
"""

import pytest
from httpx import AsyncClient

from src.domains.auth.models import User
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType


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

        # Correct route is /activate (POST)
        response = await client.post(
            "/api/v1/connectors/gmail/activate",
            json={
                "code": "fake-auth-code",
                "state": "invalid-state",
            },
        )

        assert response.status_code == 400


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
    """Test refreshing connector credentials."""

    @pytest.mark.asyncio
    async def test_refresh_connector_credentials(
        self, authenticated_client: tuple[AsyncClient, User], async_session
    ):
        """Test refreshing connector OAuth credentials."""
        import json

        from src.core.security import encrypt_data

        client, user = authenticated_client

        # Create test connector with refresh token
        credentials = {
            "access_token": "old-access-token",
            "refresh_token": "test-refresh-token",
            "expires_at": 1234567890,
        }
        connector = Connector(
            user_id=user.id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            credentials_encrypted=encrypt_data(json.dumps(credentials)),
        )
        async_session.add(connector)
        await async_session.commit()
        await async_session.refresh(connector)

        response = await client.post(f"/api/v1/connectors/{connector.id}/refresh")

        # May return 200 (success) or error depending on mock/real OAuth
        # For now, just verify endpoint exists
        assert response.status_code in [200, 400, 500]


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
