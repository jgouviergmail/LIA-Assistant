"""
Unit tests for BaseGoogleClient.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Created: 2025-11-20
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException, status

from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from tests.helpers.oauth_refresh_io import ServedCredentials


# Mock concrete implementation for testing
class MockGoogleClient(BaseGoogleClient):
    connector_type = ConnectorType.GOOGLE_CONTACTS
    api_base_url = "https://people.googleapis.com/v1"


@pytest.fixture
def user_id():
    """Provide test user ID."""
    return uuid4()


@pytest.fixture
def valid_credentials():
    """Provide valid OAuth credentials."""
    return ConnectorCredentials(
        access_token="valid_access_token",
        refresh_token="valid_refresh_token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        token_type="Bearer",
    )


@pytest.fixture
def expired_credentials():
    """Provide expired OAuth credentials."""
    return ConnectorCredentials(
        access_token="expired_access_token",
        refresh_token="valid_refresh_token",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
        token_type="Bearer",
    )


@pytest.fixture
def mock_connector_service():
    """Provide mock connector service."""
    service = Mock()
    service.read_connector_credentials = AsyncMock()
    service.db = AsyncMock()
    return service


@pytest.fixture
def client(user_id, valid_credentials, mock_connector_service):
    """Provide MockGoogleClient instance."""
    return MockGoogleClient(
        user_id=user_id,
        credentials=valid_credentials,
        connector_service=mock_connector_service,
        rate_limit_per_second=10,
    )


class TestClientInitialization:
    def test_init_sets_attributes(self, user_id, valid_credentials, mock_connector_service):
        """Test client initialization sets attributes correctly."""
        client = MockGoogleClient(
            user_id=user_id,
            credentials=valid_credentials,
            connector_service=mock_connector_service,
            rate_limit_per_second=20,
        )

        assert client.user_id == user_id
        assert client.credentials == valid_credentials
        assert client.connector_service == mock_connector_service
        assert client._rate_limit_per_second == 20
        assert client._rate_limit_interval == 1.0 / 20
        assert client._http_client is None
        assert client._redis_rate_limiter is None


class TestHttpClient:
    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, client):
        """Test _get_client creates HTTP client with connection pooling."""
        http_client = await client._get_client()

        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)
        assert client._http_client is http_client

    @pytest.mark.asyncio
    async def test_get_client_reuses_existing(self, client):
        """Test _get_client reuses existing HTTP client."""
        client1 = await client._get_client()
        client2 = await client._get_client()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_closes_client(self, client):
        """Test close() closes HTTP client."""
        await client._get_client()
        assert client._http_client is not None

        await client.close()
        assert client._http_client is None


class TestRateLimiting:
    @pytest.mark.asyncio
    @patch("src.domains.connectors.clients.base_oauth_client.settings")
    async def test_rate_limit_disabled_returns_immediately(self, mock_settings, client):
        """Test rate limiting returns immediately when disabled."""
        mock_settings.rate_limit_enabled = False

        # Should not raise or wait
        await client._rate_limit()

    @pytest.mark.asyncio
    @patch("src.domains.connectors.clients.base_oauth_client.settings")
    async def test_rate_limit_acquires_redis_token(self, mock_settings, client):
        """Test rate limiting acquires token from Redis."""
        mock_settings.rate_limit_enabled = True

        mock_limiter = AsyncMock()
        mock_limiter.acquire = AsyncMock(return_value=True)
        client._redis_rate_limiter = mock_limiter

        await client._rate_limit()

        mock_limiter.acquire.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.domains.connectors.clients.base_oauth_client.settings")
    @patch("src.domains.connectors.clients.base_oauth_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_retries_on_limit_exceeded(self, mock_sleep, mock_settings, client):
        """Test rate limiting retries when limit exceeded."""
        mock_settings.rate_limit_enabled = True

        mock_limiter = AsyncMock()
        # Fail first 2 attempts, succeed on 3rd
        mock_limiter.acquire = AsyncMock(side_effect=[False, False, True])
        client._redis_rate_limiter = mock_limiter

        await client._rate_limit()

        assert mock_limiter.acquire.call_count == 3

    @pytest.mark.asyncio
    @patch("src.domains.connectors.clients.base_oauth_client.settings")
    @patch("src.domains.connectors.clients.base_oauth_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_rate_limit_raises_429_on_max_retries(self, mock_sleep, mock_settings, client):
        """Test rate limiting raises 429 when max retries exceeded (Lines 189-199)."""
        mock_settings.rate_limit_enabled = True

        # Create mock limiter with explicit async function
        async def mock_acquire(*args, **kwargs):
            return False

        mock_limiter = Mock()
        mock_limiter.acquire = mock_acquire

        # Set limiter directly to avoid Redis initialization
        client._redis_rate_limiter = mock_limiter

        # An explicit refusal is final; it is not a Redis outage permitting a
        # local fallback that would bypass the account's allowance.
        with pytest.raises(HTTPException) as refused:
            await client._rate_limit()
        assert refused.value.status_code == 429

        # Verify sleep was called for retries (but not actual wait due to mock)
        assert mock_sleep.await_count >= 1  # At least one retry happened

    @pytest.mark.asyncio
    @patch("src.domains.connectors.clients.base_oauth_client.settings")
    @patch("src.domains.connectors.clients.base_oauth_client.time")
    async def test_rate_limit_fallback_to_local_on_redis_error(
        self, mock_time, mock_settings, client
    ):
        """Test rate limiting falls back to local throttling on Redis error."""
        mock_settings.rate_limit_enabled = True
        mock_time.monotonic.side_effect = [0.0, 0.05, 0.15]

        # Simulate Redis error
        client._redis_rate_limiter = None
        with patch.object(
            client, "_get_redis_rate_limiter", side_effect=ConnectionError("Redis unavailable")
        ):
            # Should not raise - fallback to local
            await client._rate_limit()


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_token_not_needed_when_valid(self, client, valid_credentials):
        """Test token refresh skipped when token still valid."""
        client.credentials = valid_credentials

        access_token = await client._ensure_valid_token()

        assert access_token == valid_credentials.access_token
        client.connector_service.read_connector_credentials.assert_not_called()

    @pytest.mark.asyncio
    async def test_an_expired_token_is_replaced_by_what_the_door_serves(
        self, client, expired_credentials
    ):
        """The client refreshes nothing itself: the service hands the stored token to the
        one refresh door (audit AC-029), and the client keeps what comes back."""
        client.credentials = expired_credentials
        refreshed = ConnectorCredentials(
            access_token="new_access_token",
            refresh_token="valid_refresh_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        )
        served = ServedCredentials(refreshed)
        client.connector_service.read_connector_credentials.return_value = served

        access_token = await client._ensure_valid_token()

        assert access_token == "new_access_token"
        assert client.credentials == refreshed
        assert served.asked == 1, "the client must ask the door for a fresh token, once"
        client.connector_service.read_connector_credentials.assert_awaited_once_with(
            client.user_id, client.connector_type
        )

    @pytest.mark.asyncio
    async def test_refresh_token_raises_404_when_connector_not_found(
        self, client, expired_credentials
    ):
        """No credentials and no row: the connector is gone (404)."""
        client.credentials = expired_credentials
        client.connector_service.read_connector_credentials.return_value = None
        mock_repo = Mock()
        mock_repo.get_by_user_and_type = AsyncMock(return_value=None)

        with patch("src.domains.connectors.repository.ConnectorRepository", return_value=mock_repo):
            with pytest.raises(HTTPException) as exc_info:
                await client._ensure_valid_token()

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestARefreshOfAnOwnedUnit:
    """A unit of work that owns its session is OVER before the door is asked (ADR-304)."""

    @pytest.mark.asyncio
    async def test_the_unit_ends_before_the_token_endpoint_is_called(
        self, user_id, expired_credentials, valid_credentials
    ):
        from collections.abc import AsyncIterator
        from contextlib import asynccontextmanager

        from src.domains.connectors.session_scope import ConnectorUnitOfWork

        order: list[str] = []

        class _Stored:
            async def fresh(self) -> ConnectorCredentials:
                order.append("door")
                return valid_credentials

        async def read(*_args: object) -> _Stored:
            order.append("read")
            return _Stored()

        unit_service = Mock()
        unit_service.read_connector_credentials = AsyncMock(side_effect=read)

        class _OwnedUnit(ConnectorUnitOfWork):
            owns_units = True

            @asynccontextmanager
            async def unit_of_work(self) -> AsyncIterator[Mock]:
                order.append("unit:open")
                yield unit_service
                order.append("unit:over")

        client = MockGoogleClient(
            user_id=user_id,
            credentials=expired_credentials,
            connector_service=_OwnedUnit(),
            rate_limit_per_second=10,
        )

        assert await client._ensure_valid_token() == valid_credentials.access_token
        assert order == ["unit:open", "read", "unit:over", "door"]


class TestMakeRequest:
    @pytest.mark.asyncio
    async def test_make_request_get_success(self, client):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_response.content = b'{"result": "success"}'

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("GET", "/test", params={"query": "test"})

        assert result == {"result": "success"}
        mock_http_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_post_success(self, client):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"created": True}
        mock_response.content = b'{"created": true}'

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("POST", "/test", json_data={"data": "value"})

        assert result == {"created": True}
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("base_url", "expected_url"),
        [
            (None, "https://people.googleapis.com/v1/messages/send"),
            ("https://upload.example.test/v1", "https://upload.example.test/v1/messages/send"),
        ],
    )
    async def test_make_request_posts_to_the_root_the_call_names(
        self, client, base_url, expected_url
    ):
        """A raw body reaches the root the call names, else ``api_base_url`` (ADR-321).

        Gmail accepts a message carrying a file on its UPLOAD URI only: a send
        that kept the default root would meet the metadata URI's ~1 MiB refusal.
        """
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "sent"}
        mock_response.content = b'{"id": "sent"}'

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            await client._make_request(
                "POST",
                "/messages/send",
                extra_headers={"Content-Type": "message/rfc822"},
                content=b"raw message",
                base_url=base_url,
            )

        sent = mock_http_client.post.await_args
        assert sent.args[0] == expected_url
        assert sent.kwargs["content"] == b"raw message"
        assert sent.kwargs["headers"]["Content-Type"] == "message/rfc822"

    @pytest.mark.asyncio
    async def test_make_request_retries_on_429(self, client):
        """Test request retries on 429 rate limit."""
        # First attempt: 429, second attempt: success
        mock_response_429 = Mock()
        mock_response_429.status_code = 429

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"result": "success"}
        mock_response_200.content = b'{"result": "success"}'

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=[mock_response_429, mock_response_200])
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("GET", "/test")

        assert result == {"result": "success"}
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_retries_on_500(self, client):
        """Test request retries on 500 server error."""
        # First attempt: 500, second attempt: success
        mock_response_500 = Mock()
        mock_response_500.status_code = 500

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"result": "success"}
        mock_response_200.content = b'{"result": "success"}'

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=[mock_response_500, mock_response_200])
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("GET", "/test")

        assert result == {"result": "success"}
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_raises_on_4xx_client_error(self, client):
        """Test request raises HTTPException on 4xx client error."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_request("GET", "/test")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_make_request_handles_network_error(self, client):
        """Test request handles network errors with retry."""
        # First attempt: network error, second attempt: success
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"result": "success"}
        mock_response_200.content = b'{"result": "success"}'

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(
            side_effect=[httpx.RequestError("Network error"), mock_response_200]
        )
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("GET", "/test")

        assert result == {"result": "success"}
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_returns_empty_dict_on_no_content(self, client):
        """Test request returns empty dict when response has no content."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.content = b""

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("GET", "/test")

        assert result == {}

    @pytest.mark.asyncio
    async def test_make_request_put_success(self, client):
        """Test successful PUT request (Line 334)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"updated": True}
        mock_response.content = b'{"updated": true}'

        mock_http_client = AsyncMock()
        mock_http_client.put = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("PUT", "/test", json_data={"data": "value"})

        assert result == {"updated": True}
        mock_http_client.put.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_put_carries_a_raw_body(self, client):
        """A PUT can carry raw bytes: Gmail's draft update takes a multipart body."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "r-1"}
        mock_response.content = b'{"id": "r-1"}'

        mock_http_client = AsyncMock()
        mock_http_client.put = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            await client._make_request(
                "PUT",
                "/drafts/r-1",
                extra_headers={"Content-Type": "multipart/related; boundary=b"},
                content=b"--b--",
            )

        assert mock_http_client.put.call_args.kwargs["content"] == b"--b--"

    @pytest.mark.asyncio
    async def test_make_request_delete_success(self, client):
        """Test successful DELETE request (Line 336)."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.content = b""

        mock_http_client = AsyncMock()
        mock_http_client.delete = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_request("DELETE", "/test")

        assert result == {}
        mock_http_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_raises_on_unsupported_method(self, client):
        """Test request raises ValueError on unsupported HTTP method (Line 378)."""
        client._http_client = AsyncMock()

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            with pytest.raises(ValueError) as exc_info:
                await client._make_request("OPTIONS", "/test")

        assert "Unsupported HTTP method: OPTIONS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_make_request_max_retries_exceeded_on_network_error(self, client):
        """Test max retries exceeded on persistent network errors (Lines 398-404)."""
        mock_http_client = AsyncMock()
        # Always fail with network error
        mock_http_client.get = AsyncMock(side_effect=httpx.RequestError("Network unreachable"))
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
            patch(
                "src.domains.connectors.clients.base_google_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_request("GET", "/test", max_retries=3)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "API unavailable" in exc_info.value.detail
        # Verify retried 3 times
        assert mock_http_client.get.call_count == 3

    @pytest.mark.asyncio
    async def test_make_request_max_retries_exceeded_on_429(self, client):
        """Test max retries exceeded on persistent 429 errors (Lines 403-407)."""
        mock_response = Mock()
        mock_response.status_code = 429

        mock_http_client = AsyncMock()
        # Always return 429
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
            patch(
                "src.domains.connectors.clients.base_google_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_request("GET", "/test", max_retries=3)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "max retries exceeded" in exc_info.value.detail
        # Verify retried 3 times
        assert mock_http_client.get.call_count == 3


class TestTokenRefreshBugFixes:
    """Bug #1 and #3: a refresh must use the STORED refresh token, never a stale one.

    Since the one refresh door (audit AC-029) this is structural: the client hands the
    door nothing of its own, the service reads the row and the door exchanges what is
    stored. Proven here through the real service and the real door.
    """

    @pytest.mark.asyncio
    async def test_the_exchange_uses_the_stored_token_not_the_stale_one(self, user_id, monkeypatch):
        from src.core.security import encrypt_data
        from src.domains.connectors.models import Connector, ConnectorStatus
        from src.domains.connectors.service import ConnectorService
        from tests.helpers.oauth_refresh_io import install_scripted_door

        stale = ConnectorCredentials(
            access_token="stale_access",
            refresh_token="refresh_token_v1",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            token_type="Bearer",
        )
        # Another process rotated the refresh token; the stored access token expires too.
        stored = ConnectorCredentials(
            access_token="stored_access",
            refresh_token="refresh_token_v2",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            token_type="Bearer",
        )
        row = Connector(
            id=uuid4(),
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=ConnectorStatus.ACTIVE,
            scopes=[],
            credentials_encrypted=encrypt_data(stored.model_dump_json()),
        )
        service = ConnectorService(AsyncMock())
        service.repository.get_by_user_and_type = AsyncMock(return_value=row)
        door = install_scripted_door(monkeypatch, row)
        client = MockGoogleClient(
            user_id=user_id,
            credentials=stale,
            connector_service=service,
            rate_limit_per_second=10,
        )

        await client._ensure_valid_token()

        assert door.exchanged == ["refresh_token_v2"]

    @pytest.mark.asyncio
    async def test_refresh_token_raises_400_when_no_fresh_credentials(
        self, client, expired_credentials
    ):
        """A row that exists but serves no credentials is a 400, never a silent pass."""
        client.credentials = expired_credentials
        client.connector_service.read_connector_credentials.return_value = None
        mock_repo = Mock()
        mock_repo.get_by_user_and_type = AsyncMock(return_value=Mock())

        with patch("src.domains.connectors.repository.ConnectorRepository", return_value=mock_repo):
            with pytest.raises(HTTPException) as exc_info:
                await client._ensure_valid_token()

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "No credentials found" in exc_info.value.detail


# ============================================================================
# Tests for apply_max_items_limit() helper
# ============================================================================


class TestApplyMaxItemsLimit:
    """Tests for the apply_max_items_limit helper function."""

    @patch("src.domains.connectors.clients.base_google_client.settings")
    def test_returns_max_results_when_below_limit(self, mock_settings):
        """Test returns max_results unchanged when below limit."""
        mock_settings.api_max_items_per_request = 100
        result = apply_max_items_limit(50)
        assert result == 50

    @patch("src.domains.connectors.clients.base_google_client.settings")
    def test_returns_limit_when_max_results_exceeds(self, mock_settings):
        """Test returns limit when max_results exceeds limit."""
        mock_settings.api_max_items_per_request = 100
        result = apply_max_items_limit(500)
        assert result == 100

    @patch("src.domains.connectors.clients.base_google_client.settings")
    def test_returns_limit_when_equal(self, mock_settings):
        """Test returns limit when max_results equals limit."""
        mock_settings.api_max_items_per_request = 100
        result = apply_max_items_limit(100)
        assert result == 100

    @patch("src.domains.connectors.clients.base_google_client.settings")
    def test_handles_zero_max_results(self, mock_settings):
        """Test handles zero max_results."""
        mock_settings.api_max_items_per_request = 100
        result = apply_max_items_limit(0)
        assert result == 0


# ============================================================================
# Tests for _get_paginated_list()
# ============================================================================


class TestGetPaginatedList:
    """Tests for the _get_paginated_list method."""

    @pytest.mark.asyncio
    async def test_single_page_returns_all_items(self, client):
        """Test single page response returns all items."""
        mock_response = {"items": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}

        with (
            patch.object(client, "_make_request", AsyncMock(return_value=mock_response)),
            patch("src.domains.connectors.clients.base_google_client.settings") as mock_settings,
        ):
            mock_settings.api_max_items_per_request = 100

            result = await client._get_paginated_list(
                endpoint="/test",
                items_key="items",
                max_results=10,
            )

        assert len(result["items"]) == 3
        assert result["items"][0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_multi_page_collects_all_items(self, client):
        """Test multi-page pagination collects all items."""
        page1_response = {"items": [{"id": "1"}, {"id": "2"}], "nextPageToken": "token123"}
        page2_response = {"items": [{"id": "3"}, {"id": "4"}]}

        mock_request = AsyncMock(side_effect=[page1_response, page2_response])

        with (
            patch.object(client, "_make_request", mock_request),
            patch("src.domains.connectors.clients.base_google_client.settings") as mock_settings,
        ):
            mock_settings.api_max_items_per_request = 100

            result = await client._get_paginated_list(
                endpoint="/test",
                items_key="items",
                max_results=10,
            )

        assert len(result["items"]) == 4
        assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_stops_at_max_results(self, client):
        """Test pagination stops when max_results is reached."""
        page1_response = {"items": [{"id": "1"}, {"id": "2"}], "nextPageToken": "token123"}
        page2_response = {"items": [{"id": "3"}, {"id": "4"}], "nextPageToken": "token456"}

        mock_request = AsyncMock(side_effect=[page1_response, page2_response])

        with (
            patch.object(client, "_make_request", mock_request),
            patch("src.domains.connectors.clients.base_google_client.settings") as mock_settings,
        ):
            mock_settings.api_max_items_per_request = 100

            result = await client._get_paginated_list(
                endpoint="/test",
                items_key="items",
                max_results=3,  # Only want 3 items
            )

        # Should truncate to max_results
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_applies_security_limit(self, client):
        """Test applies api_max_items_per_request security limit."""
        mock_response = {"items": [{"id": "1"}]}

        mock_request = AsyncMock(return_value=mock_response)

        with (
            patch.object(client, "_make_request", mock_request),
            patch("src.domains.connectors.clients.base_google_client.settings") as mock_settings,
        ):
            mock_settings.api_max_items_per_request = 50  # Security limit

            await client._get_paginated_list(
                endpoint="/test",
                items_key="items",
                max_results=1000,  # Request more than limit
            )

        # Should request only 50 (the limit), not 1000
        call_args = mock_request.call_args
        # params are passed as 3rd positional arg
        assert call_args[0][2]["pageSize"] == 50

    @pytest.mark.asyncio
    async def test_passes_custom_params(self, client):
        """Test passes additional custom parameters."""
        mock_response = {"items": []}

        mock_request = AsyncMock(return_value=mock_response)

        with (
            patch.object(client, "_make_request", mock_request),
            patch("src.domains.connectors.clients.base_google_client.settings") as mock_settings,
        ):
            mock_settings.api_max_items_per_request = 100

            await client._get_paginated_list(
                endpoint="/test",
                items_key="items",
                max_results=10,
                params={"q": "test query", "orderBy": "name"},
            )

        call_args = mock_request.call_args
        # params are passed as 3rd positional arg
        assert call_args[0][2]["q"] == "test query"
        assert call_args[0][2]["orderBy"] == "name"

    @pytest.mark.asyncio
    async def test_uses_custom_token_keys(self, client):
        """Test uses custom pageToken and nextPageToken keys."""
        page1_response = {"data": [{"id": "1"}], "continuation": "abc"}
        page2_response = {"data": [{"id": "2"}]}

        mock_request = AsyncMock(side_effect=[page1_response, page2_response])

        with (
            patch.object(client, "_make_request", mock_request),
            patch("src.domains.connectors.clients.base_google_client.settings") as mock_settings,
        ):
            mock_settings.api_max_items_per_request = 100

            result = await client._get_paginated_list(
                endpoint="/test",
                items_key="data",
                max_results=10,
                page_token_key="cursor",
                next_page_token_key="continuation",
            )

        assert len(result["data"]) == 2
        # Second call should have cursor param
        second_call_args = mock_request.call_args_list[1]
        # params are passed as 3rd positional arg
        assert second_call_args[0][2]["cursor"] == "abc"

    @pytest.mark.asyncio
    async def test_applies_transform_items(self, client):
        """Test applies transform_items callback."""
        mock_response = {"items": [{"name": "a"}, {"name": "b"}]}

        def uppercase_transform(items):
            return [{"name": item["name"].upper()} for item in items]

        mock_request = AsyncMock(return_value=mock_response)

        with (
            patch.object(client, "_make_request", mock_request),
            patch("src.domains.connectors.clients.base_google_client.settings") as mock_settings,
        ):
            mock_settings.api_max_items_per_request = 100

            result = await client._get_paginated_list(
                endpoint="/test",
                items_key="items",
                max_results=10,
                transform_items=uppercase_transform,
            )

        assert result["items"][0]["name"] == "A"
        assert result["items"][1]["name"] == "B"


# ============================================================================
# Tests for _make_raw_request()
# ============================================================================


class TestMakeRawRequest:
    """Tests for the _make_raw_request method for binary downloads."""

    @pytest.mark.asyncio
    async def test_returns_bytes_on_success(self, client):
        """Test returns raw bytes on successful response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"binary file content"

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            result = await client._make_raw_request("GET", "/files/123", {"alt": "media"})

        assert result == b"binary file content"
        mock_http_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_429(self, client):
        """Test retries on 429 rate limit response."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.content = b"success"

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(side_effect=[mock_response_429, mock_response_200])
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
            patch(
                "src.domains.connectors.clients.base_google_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await client._make_raw_request("GET", "/files/123")

        assert result == b"success"
        assert mock_http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_5xx(self, client):
        """Test retries on 5xx server error."""
        mock_response_500 = Mock()
        mock_response_500.status_code = 500

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.content = b"success"

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(side_effect=[mock_response_500, mock_response_200])
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
            patch(
                "src.domains.connectors.clients.base_google_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await client._make_raw_request("GET", "/files/123")

        assert result == b"success"
        assert mock_http_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_on_4xx_client_error(self, client):
        """Test raises HTTPException on 4xx client error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "File not found"

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_raw_request("GET", "/files/123")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self, client):
        """Test raises 503 when max retries exceeded."""
        mock_response = Mock()
        mock_response.status_code = 500

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
            patch(
                "src.domains.connectors.clients.base_google_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_raw_request("GET", "/files/123", max_retries=3)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert mock_http_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_network_error_with_retry(self, client):
        """Test handles network error with retry."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"success after retry"

        mock_http_client = AsyncMock()
        mock_http_client.request = AsyncMock(
            side_effect=[httpx.RequestError("Network error"), mock_response]
        )
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
            patch(
                "src.domains.connectors.clients.base_google_client.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            result = await client._make_raw_request("GET", "/files/123")

        assert result == b"success after retry"
        assert mock_http_client.request.call_count == 2


# ============================================================================
# Tests for extra_headers in _make_request()
# ============================================================================


class TestMakeRequestExtraHeaders:
    """Tests for extra_headers parameter in _make_request."""

    @pytest.mark.asyncio
    async def test_includes_extra_headers_in_request(self, client):
        """Test extra_headers are included in the request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_response.content = b'{"result": "success"}'

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            await client._make_request(
                "GET",
                "/test",
                extra_headers={"X-Goog-FieldMask": "places.id,places.name"},
            )

        # Verify headers were passed
        call_args = mock_http_client.get.call_args
        headers = call_args.kwargs["headers"]
        assert "X-Goog-FieldMask" in headers
        assert headers["X-Goog-FieldMask"] == "places.id,places.name"

    @pytest.mark.asyncio
    async def test_extra_headers_merged_with_auth(self, client):
        """Test extra_headers are merged with Authorization header."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.content = b"{}"

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="test_token")),
        ):
            await client._make_request(
                "POST",
                "/test",
                extra_headers={"X-Custom-Header": "value"},
            )

        call_args = mock_http_client.post.call_args
        headers = call_args.kwargs["headers"]
        # Both Authorization and custom header should be present
        assert headers["Authorization"] == "Bearer test_token"
        assert headers["X-Custom-Header"] == "value"

    @pytest.mark.asyncio
    async def test_no_extra_headers_still_works(self, client):
        """Test request works without extra_headers."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.content = b"{}"

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_ensure_valid_token", AsyncMock(return_value="valid_token")),
        ):
            # No extra_headers parameter
            result = await client._make_request("GET", "/test")

        assert result == {}
        call_args = mock_http_client.get.call_args
        headers = call_args.kwargs["headers"]
        # Only Authorization header
        assert headers == {"Authorization": "Bearer valid_token"}
