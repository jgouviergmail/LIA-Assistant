"""
Unit tests for BaseAPIKeyClient.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Created: 2025-11-20
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException, status

from src.domains.connectors.clients.base_api_key_client import BaseAPIKeyClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials


# Mock concrete implementation for testing
class MockAPIKeyClient(BaseAPIKeyClient):
    connector_type = ConnectorType.GOOGLE_GMAIL
    api_base_url = "https://api.example.com/v1"
    auth_header_name = "Authorization"
    auth_header_prefix = "Bearer"


@pytest.fixture
def user_id():
    """Provide test user ID."""
    return uuid4()


@pytest.fixture
def valid_credentials():
    """Provide valid API key credentials."""
    return APIKeyCredentials(api_key="sk-test1234567890abcdefghijklmnopqrstuvwxyz")


@pytest.fixture
def client(user_id, valid_credentials):
    """Provide MockAPIKeyClient instance."""
    return MockAPIKeyClient(
        user_id=user_id,
        credentials=valid_credentials,
        rate_limit_per_second=10,
    )


class TestClientInitialization:
    def test_init_sets_attributes(self, user_id, valid_credentials):
        """Test client initialization sets attributes correctly."""
        client = MockAPIKeyClient(
            user_id=user_id,
            credentials=valid_credentials,
            rate_limit_per_second=20,
        )

        assert client.user_id == user_id
        assert client.credentials == valid_credentials
        assert client._rate_limit_per_second == 20
        assert client._rate_limit_interval == 1.0 / 20
        assert client._http_client is None


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
    @patch("src.domains.connectors.clients.base_api_key_client.time")
    async def test_rate_limit_throttles_requests(self, mock_time, client):
        """Test rate limiting applies throttling between requests."""
        # Simulate fast consecutive requests
        # Need 4 calls: now, elapsed calculation, end of first call, start of second call
        mock_time.monotonic.side_effect = [0.0, 0.0, 0.0, 0.05, 0.05, 0.15]

        # Mock Redis rate limiter to avoid real Redis connection
        mock_limiter = AsyncMock()
        mock_limiter.acquire.return_value = True
        with patch.object(client, "_get_redis_rate_limiter", AsyncMock(return_value=mock_limiter)):
            # First request - no throttle
            await client._rate_limit()

            # Second request - should throttle
            await client._rate_limit()

    @pytest.mark.asyncio
    @patch("src.domains.connectors.clients.base_api_key_client.time")
    async def test_rate_limit_no_throttle_when_interval_passed(self, mock_time, client):
        """Test rate limiting skips throttling when interval has passed."""
        # Simulate requests with sufficient time gap
        mock_time.monotonic.side_effect = [0.0, 0.2]

        # Mock Redis rate limiter to avoid real Redis connection
        mock_limiter = AsyncMock()
        mock_limiter.acquire.return_value = True
        with patch.object(client, "_get_redis_rate_limiter", AsyncMock(return_value=mock_limiter)):
            await client._rate_limit()
            # Should not throttle (0.2s > 0.1s interval for 10 req/s)


class TestAuthHeaders:
    def test_build_auth_headers_with_prefix(self, client):
        """Test building auth headers with prefix."""
        headers = client._build_auth_headers()

        assert headers["Authorization"] == f"Bearer {client.credentials.api_key}"

    def test_build_auth_headers_without_prefix(self, client):
        """Test building auth headers without prefix."""
        client.auth_header_prefix = ""

        headers = client._build_auth_headers()

        assert headers["Authorization"] == client.credentials.api_key

    def test_build_auth_headers_query_method_returns_empty(self, client):
        """Test building auth headers returns empty when using query method."""
        client.auth_method = "query"

        headers = client._build_auth_headers()

        assert headers == {}


class TestAuthParams:
    def test_build_auth_params_query_method(self, client):
        """Test building auth params for query method."""
        client.auth_method = "query"

        params = client._build_auth_params()

        assert params[client.auth_query_param] == client.credentials.api_key

    def test_build_auth_params_header_method_returns_empty(self, client):
        """Test building auth params returns empty for header method."""
        client.auth_method = "header"

        params = client._build_auth_params()

        assert params == {}


class TestMaskAPIKey:
    def test_mask_api_key_standard(self, client):
        """Test masking standard length API key."""
        key = "sk-test1234567890abcdefghijklmnopqrstuvwxyz"
        masked = client._mask_api_key(key)

        assert masked == "sk-t...wxyz"
        assert len(masked) < len(key)

    def test_mask_api_key_short(self, client):
        """Test masking short API key."""
        key = "short"
        masked = client._mask_api_key(key)

        assert masked == "***"

    def test_mask_api_key_preserves_prefix_suffix(self, client):
        """Test masking preserves first 4 and last 4 characters."""
        key = "sk-abcdefghijklmnopqrstuvwxyz"
        masked = client._mask_api_key(key)

        assert masked.startswith(key[:4])
        assert masked.endswith(key[-4:])


class TestValidateAPIKey:
    @pytest.mark.asyncio
    async def test_validate_api_key_valid(self, client):
        """Test API key validation succeeds for valid key."""
        result = await client.validate_api_key()

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_api_key_empty(self, client):
        """Test API key validation fails for empty key."""
        client.credentials.api_key = ""

        result = await client.validate_api_key()

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_api_key_too_short(self, client):
        """Test API key validation fails for short key."""
        client.credentials.api_key = "short"

        result = await client.validate_api_key()

        assert result is False


class TestMakeRequest:
    @pytest.mark.asyncio
    async def test_make_request_get_success(self, client):
        """Test successful GET request with header auth."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {"result": "success"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            result = await client._make_request("GET", "/test", params={"query": "test"})

        assert result == {"result": "success"}
        mock_http_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_post_success(self, client):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"created": true}'
        mock_response.json.return_value = {"created": True}

        mock_http_client = AsyncMock()
        mock_http_client.post = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            result = await client._make_request("POST", "/test", json_data={"data": "value"})

        assert result == {"created": True}
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_includes_auth_in_headers(self, client):
        """Test request includes API key in authorization header."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {"result": "success"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            await client._make_request("GET", "/test")

        call_args = mock_http_client.get.call_args
        headers = call_args.kwargs["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_make_request_includes_auth_in_params_for_query_method(self, client):
        """Test request includes API key in query params when using query method."""
        client.auth_method = "query"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {"result": "success"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            await client._make_request("GET", "/test")

        call_args = mock_http_client.get.call_args
        params = call_args.kwargs["params"]
        assert client.auth_query_param in params
        assert params[client.auth_query_param] == client.credentials.api_key

    @pytest.mark.asyncio
    async def test_make_request_retries_on_429(self, client):
        """Test request retries on 429 rate limit."""
        # First attempt: 429, second attempt: success
        mock_response_429 = Mock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"Retry-After": "1"}

        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.text = '{"result": "success"}'
        mock_response_200.json.return_value = {"result": "success"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=[mock_response_429, mock_response_200])
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
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
        mock_response_200.text = '{"result": "success"}'
        mock_response_200.json.return_value = {"result": "success"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=[mock_response_500, mock_response_200])
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            result = await client._make_request("GET", "/test")

        assert result == {"result": "success"}
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_raises_401_on_auth_error(self, client):
        """Test request raises 401 on authentication error."""
        mock_response = Mock()
        mock_response.status_code = 401

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_request("GET", "/test")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_make_request_raises_403_on_forbidden(self, client):
        """Test request raises 401 on 403 forbidden error."""
        mock_response = Mock()
        mock_response.status_code = 403

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_request("GET", "/test")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_make_request_raises_on_other_4xx_errors(self, client):
        """Test request raises HTTPException on other 4xx errors."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_request("GET", "/test")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_make_request_handles_network_error(self, client):
        """Test request handles network errors with retry."""
        # First attempt: network error, second attempt: success
        mock_response_200 = Mock()
        mock_response_200.status_code = 200
        mock_response_200.text = '{"result": "success"}'
        mock_response_200.json.return_value = {"result": "success"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(
            side_effect=[httpx.RequestError("Network error"), mock_response_200]
        )
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            result = await client._make_request("GET", "/test")

        assert result == {"result": "success"}
        assert mock_http_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_make_request_raises_503_on_max_network_errors(self, client):
        """Test request raises 503 when network errors exceed max retries."""
        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(side_effect=httpx.RequestError("Network error"))
        client._http_client = mock_http_client

        with patch.object(client, "_rate_limit", AsyncMock()):
            with pytest.raises(HTTPException) as exc_info:
                await client._make_request("GET", "/test", max_retries=3)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_make_request_returns_empty_dict_on_no_content(self, client):
        """Test request returns empty dict when response has no text."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.text = ""

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
        ):
            result = await client._make_request("GET", "/test")

        assert result == {}

    @pytest.mark.asyncio
    async def test_make_request_supports_all_http_methods(self, client):
        """Test request supports GET, POST, PUT, DELETE, PATCH methods."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"result": "success"}'
        mock_response.json.return_value = {"result": "success"}

        mock_http_client = AsyncMock()
        mock_http_client.get = AsyncMock(return_value=mock_response)
        mock_http_client.post = AsyncMock(return_value=mock_response)
        mock_http_client.put = AsyncMock(return_value=mock_response)
        mock_http_client.delete = AsyncMock(return_value=mock_response)
        mock_http_client.patch = AsyncMock(return_value=mock_response)
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
        ):
            await client._make_request("GET", "/test")
            await client._make_request("POST", "/test", json_data={})
            await client._make_request("PUT", "/test", json_data={})
            await client._make_request("DELETE", "/test")
            await client._make_request("PATCH", "/test", json_data={})

        mock_http_client.get.assert_called_once()
        mock_http_client.post.assert_called_once()
        mock_http_client.put.assert_called_once()
        mock_http_client.delete.assert_called_once()
        mock_http_client.patch.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_raises_on_unsupported_method(self, client):
        """Test request raises ValueError on unsupported HTTP method."""
        mock_http_client = AsyncMock()
        client._http_client = mock_http_client

        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
        ):
            with pytest.raises(ValueError, match="Unsupported HTTP method"):
                await client._make_request("INVALID", "/test")
