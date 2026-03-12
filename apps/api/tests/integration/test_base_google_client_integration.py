"""
Integration tests for BaseGoogleClient and derived clients.

Tests that the inheritance hierarchy works correctly with real clients.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.schemas import ConnectorCredentials


@pytest.mark.integration
class TestGoogleClientInheritance:
    """Tests for Google client inheritance from BaseGoogleClient."""

    @pytest.fixture
    def user_id(self):
        """Test user ID."""
        return uuid4()

    @pytest.fixture
    def valid_credentials(self):
        """Valid OAuth credentials."""
        return ConnectorCredentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    @pytest.fixture
    def mock_connector_service(self, valid_credentials):
        """Mock ConnectorService."""
        service = MagicMock()
        service._refresh_oauth_token = AsyncMock(return_value=valid_credentials)
        service.get_connector_credentials = AsyncMock(return_value=None)
        service.db = MagicMock()
        service.db.__aenter__ = AsyncMock(return_value=MagicMock())
        service.db.__aexit__ = AsyncMock(return_value=None)
        return service

    @pytest.mark.asyncio
    async def test_google_people_client_inherits_base(
        self, user_id, valid_credentials, mock_connector_service
    ):
        """Test that GooglePeopleClient correctly inherits from BaseGoogleClient."""
        from src.domains.connectors.clients.base_google_client import BaseGoogleClient
        from src.domains.connectors.clients.google_people_client import GooglePeopleClient

        # Verify inheritance
        assert issubclass(GooglePeopleClient, BaseGoogleClient)

        # Create instance with proper mocks
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.setex = AsyncMock(return_value=True)

        with patch(
            "src.domains.connectors.clients.base_google_client.get_redis_session",
            return_value=mock_redis,
        ):
            client = GooglePeopleClient(
                user_id=user_id,
                credentials=valid_credentials,
                connector_service=mock_connector_service,
            )

            # Verify it has base class attributes
            assert hasattr(client, "user_id")
            assert hasattr(client, "credentials")
            assert hasattr(client, "_rate_limit_per_second")
            assert hasattr(client, "api_base_url")
            assert hasattr(client, "connector_type")

            # Verify correct connector type
            from src.domains.connectors.models import ConnectorType

            assert client.connector_type == ConnectorType.GOOGLE_CONTACTS

            await client.close()

    @pytest.mark.asyncio
    async def test_google_gmail_client_inherits_base(
        self, user_id, valid_credentials, mock_connector_service
    ):
        """Test that GoogleGmailClient correctly inherits from BaseGoogleClient."""
        from src.domains.connectors.clients.base_google_client import BaseGoogleClient
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

        # Verify inheritance
        assert issubclass(GoogleGmailClient, BaseGoogleClient)

        # Create instance with proper mocks
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.setex = AsyncMock(return_value=True)

        with patch(
            "src.domains.connectors.clients.base_google_client.get_redis_session",
            return_value=mock_redis,
        ):
            client = GoogleGmailClient(
                user_id=user_id,
                credentials=valid_credentials,
                connector_service=mock_connector_service,
            )

            # Verify it has base class attributes
            assert hasattr(client, "user_id")
            assert hasattr(client, "credentials")
            assert hasattr(client, "_rate_limit_per_second")
            assert hasattr(client, "api_base_url")
            assert hasattr(client, "connector_type")

            # Verify correct connector type
            from src.domains.connectors.models import ConnectorType

            assert client.connector_type == ConnectorType.GOOGLE_GMAIL

            await client.close()

    @pytest.mark.asyncio
    async def test_clients_share_common_methods(
        self, user_id, valid_credentials, mock_connector_service
    ):
        """Test that all clients share common methods from base class."""
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
        from src.domains.connectors.clients.google_people_client import GooglePeopleClient

        with patch("src.domains.connectors.clients.base_google_client.get_redis_session"):
            people_client = GooglePeopleClient(
                user_id=user_id,
                credentials=valid_credentials,
                connector_service=mock_connector_service,
            )

            gmail_client = GoogleGmailClient(
                user_id=user_id,
                credentials=valid_credentials,
                connector_service=mock_connector_service,
            )

            # Both should have these inherited methods
            common_methods = [
                "_get_client",
                "_make_request",
                "_ensure_valid_token",
                "close",
            ]

            for method in common_methods:
                assert hasattr(people_client, method), f"GooglePeopleClient missing {method}"
                assert hasattr(gmail_client, method), f"GoogleGmailClient missing {method}"

            await people_client.close()
            await gmail_client.close()


@pytest.mark.integration
class TestClientRateLimiting:
    """Tests for rate limiting across Google clients."""

    @pytest.fixture
    def user_id(self):
        return uuid4()

    @pytest.fixture
    def valid_credentials(self):
        return ConnectorCredentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

    @pytest.fixture
    def mock_connector_service(self, valid_credentials):
        service = MagicMock()
        service._refresh_oauth_token = AsyncMock(return_value=valid_credentials)
        service.get_connector_credentials = AsyncMock(return_value=None)
        service.db = MagicMock()
        service.db.__aenter__ = AsyncMock(return_value=MagicMock())
        service.db.__aexit__ = AsyncMock(return_value=None)
        return service

    @pytest.mark.asyncio
    async def test_rate_limiters_are_independent(
        self, user_id, valid_credentials, mock_connector_service
    ):
        """Test that different clients have independent rate limiters."""
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
        from src.domains.connectors.clients.google_people_client import GooglePeopleClient

        # Create proper mock for Redis
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.setex = AsyncMock(return_value=True)

        with patch(
            "src.domains.connectors.clients.base_google_client.get_redis_session",
            return_value=mock_redis,
        ):
            people_client = GooglePeopleClient(
                user_id=user_id,
                credentials=valid_credentials,
                connector_service=mock_connector_service,
            )

            gmail_client = GoogleGmailClient(
                user_id=user_id,
                credentials=valid_credentials,
                connector_service=mock_connector_service,
            )

            # Rate limiters should be independent (different last request times)
            # Each client has its own _last_request_time
            assert people_client._last_request_time == gmail_client._last_request_time == 0.0
            # But they are independent objects
            assert people_client is not gmail_client

            await people_client.close()
            await gmail_client.close()


@pytest.mark.integration
class TestClientConfiguration:
    """Tests for client configuration inheritance."""

    def test_api_base_urls_are_different(self):
        """Test that each client has correct API base URL."""
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
        from src.domains.connectors.clients.google_people_client import GooglePeopleClient

        assert "people.googleapis.com" in GooglePeopleClient.api_base_url
        assert "gmail.googleapis.com" in GoogleGmailClient.api_base_url

    def test_connector_types_are_different(self):
        """Test that each client has correct connector type."""
        from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
        from src.domains.connectors.clients.google_people_client import GooglePeopleClient

        assert GooglePeopleClient.connector_type == "google_contacts"
        assert GoogleGmailClient.connector_type == "google_gmail"
