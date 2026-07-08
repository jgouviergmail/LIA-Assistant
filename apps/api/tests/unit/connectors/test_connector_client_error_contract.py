"""
Contract tests for the connector client domain error taxonomy (ADR-113).

The connector client layer used to raise raw ``fastapi.HTTPException``. It now
raises typed ``BaseAPIException`` subclasses. These tests pin the three
invariants of that migration:

1. **Mapping** — each client failure category raises the documented typed
   exception with the SAME status code, detail and headers as the legacy raw
   ``HTTPException`` (byte-identical external contract).
2. **Edge contract** — FastAPI renders the typed exceptions exactly like raw
   ``HTTPException`` (``{"detail": ...}`` payload, status code, headers), so
   the external API contract is unchanged by construction.
3. **Tool path** — ``handle_tool_exception`` / ``handle_connector_api_error``
   classify the typed exceptions exactly as they classified raw
   ``HTTPException`` (``isinstance`` checks still hold).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.core.exceptions import (
    AuthenticationError,
    ConnectorAPIError,
    ExternalServiceError,
    RateLimitError,
    ResourceNotFoundError,
    ValidationError,
)
from src.core.field_names import FIELD_ERROR_MESSAGE, FIELD_ERROR_TYPE
from src.core.i18n_api_messages import APIMessages
from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.google_places_client import GooglePlacesClient
from src.domains.connectors.clients.google_routes_client import GoogleRoutesClient
from src.domains.connectors.clients.microsoft_tasks_client import MicrosoftTasksClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.resilience import CircuitBreakerError
from src.infrastructure.resilience.circuit_breaker import CircuitState


class _GoogleClient(BaseGoogleClient):
    connector_type = ConnectorType.GOOGLE_CONTACTS
    api_base_url = "https://people.googleapis.com/v1"


class _MicrosoftClient(BaseMicrosoftClient):
    connector_type = ConnectorType.MICROSOFT_OUTLOOK
    api_base_url = "https://graph.microsoft.com/v1.0"


@pytest.fixture
def valid_credentials() -> ConnectorCredentials:
    """Provide valid OAuth credentials."""
    return ConnectorCredentials(
        access_token="valid_access_token",
        refresh_token="valid_refresh_token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        token_type="Bearer",
    )


@pytest.fixture
def expired_credentials() -> ConnectorCredentials:
    """Provide expired OAuth credentials."""
    return ConnectorCredentials(
        access_token="expired_access_token",
        refresh_token="valid_refresh_token",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
        token_type="Bearer",
    )


@pytest.fixture
def mock_connector_service() -> Mock:
    """Provide mock connector service."""
    service = Mock()
    service.get_connector_credentials = AsyncMock()
    service._refresh_oauth_token = AsyncMock()
    service.db = AsyncMock()
    return service


@pytest.fixture
def google_client(valid_credentials, mock_connector_service) -> _GoogleClient:
    """Provide a concrete OAuth (Google-family) client."""
    return _GoogleClient(
        user_id=uuid4(),
        credentials=valid_credentials,
        connector_service=mock_connector_service,
        rate_limit_per_second=10,
    )


@pytest.fixture
def microsoft_client(valid_credentials, mock_connector_service) -> _MicrosoftClient:
    """Provide a concrete Microsoft Graph client."""
    return _MicrosoftClient(
        user_id=uuid4(),
        credentials=valid_credentials,
        connector_service=mock_connector_service,
        rate_limit_per_second=10,
    )


def _mock_http_client(response_or_side_effect) -> AsyncMock:
    """Build a mocked httpx.AsyncClient whose verbs all return/raise the given value."""
    http = AsyncMock()
    for verb in ("get", "post", "put", "patch", "delete", "request"):
        if isinstance(response_or_side_effect, Exception) or (
            isinstance(response_or_side_effect, list)
        ):
            setattr(http, verb, AsyncMock(side_effect=response_or_side_effect))
        else:
            setattr(http, verb, AsyncMock(return_value=response_or_side_effect))
    return http


# =============================================================================
# 1. Mapping — BaseOAuthClient._make_request (shared by Google + Microsoft)
# =============================================================================


class TestOAuthBaseMakeRequestMapping:
    @pytest.mark.asyncio
    async def test_upstream_401_raises_authentication_error_with_reconnect_header(
        self, google_client
    ):
        """A provider 401 maps to AuthenticationError: same 401, detail, header."""
        response = Mock(status_code=401, text="invalid_grant")
        google_client._http_client = _mock_http_client(response)

        with (
            patch.object(google_client, "_rate_limit", AsyncMock()),
            patch.object(google_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch.object(
                google_client, "_invalidate_connector_on_auth_failure", AsyncMock()
            ) as invalidate,
        ):
            with pytest.raises(AuthenticationError) as exc_info:
                await google_client._make_request("GET", "/test")

        exc = exc_info.value
        assert isinstance(exc, HTTPException)  # external contract preserved
        assert exc.status_code == 401
        assert exc.detail == APIMessages.connector_auth_invalid("google_contacts")
        assert exc.headers == {"X-Requires-Reconnect": "true"}
        invalidate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upstream_4xx_maps_to_connector_api_error_with_forwarded_status(
        self, google_client
    ):
        """Non-auth upstream client errors forward the status code unchanged."""
        response = Mock(status_code=403, text="forbidden")
        google_client._http_client = _mock_http_client(response)

        with (
            patch.object(google_client, "_rate_limit", AsyncMock()),
            patch.object(google_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
        ):
            with pytest.raises(ConnectorAPIError) as exc_info:
                await google_client._make_request("GET", "/test")

        exc = exc_info.value
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 403
        assert exc.detail == "google_contacts API error: forbidden"

    @pytest.mark.asyncio
    async def test_network_failure_maps_to_external_service_error_503(self, google_client):
        """Exhausted network retries map to ExternalServiceError (503)."""
        google_client._http_client = _mock_http_client(httpx.ConnectError("boom"))

        with (
            patch.object(google_client, "_rate_limit", AsyncMock()),
            patch.object(google_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await google_client._make_request("GET", "/test")

        exc = exc_info.value
        assert exc.status_code == 503
        assert exc.detail == "google_contacts API unavailable: boom"

    @pytest.mark.asyncio
    async def test_retry_exhaustion_maps_to_external_service_error_503(self, google_client):
        """429 on every attempt exhausts retries and maps to a 503, as before."""
        response = Mock(status_code=429, headers={})
        google_client._http_client = _mock_http_client(response)

        with (
            patch.object(google_client, "_rate_limit", AsyncMock()),
            patch.object(google_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await google_client._make_request("GET", "/test")

        exc = exc_info.value
        assert exc.status_code == 503
        assert exc.detail == "google_contacts API: max retries exceeded"

    def test_client_side_rate_limit_raises_rate_limit_error_429(self, google_client):
        """The client-side rate-limit hook keeps the legacy 429 detail verbatim."""
        with pytest.raises(RateLimitError) as exc_info:
            google_client._on_rate_limit_exceeded()

        exc = exc_info.value
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 429
        assert exc.detail == ("Rate limit exceeded for google_contacts. Please try again later.")

    @pytest.mark.asyncio
    async def test_circuit_open_maps_to_external_service_error_with_retry_after(
        self, google_client
    ):
        """Circuit-open rejections keep the 503 + Retry-After header contract."""
        breaker = Mock()
        breaker.check = AsyncMock(
            side_effect=CircuitBreakerError("svc", CircuitState.OPEN, retry_after=30.0)
        )

        with (
            patch.object(google_client, "_is_circuit_breaker_enabled", return_value=True),
            patch.object(google_client, "_get_circuit_breaker", return_value=breaker),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await google_client._make_authenticated_request("GET", "https://x.test/y")

        exc = exc_info.value
        assert exc.status_code == 503
        assert exc.headers == {"Retry-After": "30"}
        assert exc.detail == (
            "google_contacts service temporarily unavailable. Please try again later."
        )


class TestOAuthTokenRefreshMapping:
    async def _run_refresh(self, client, expired_credentials, connector_row):
        """Drive _ensure_valid_token through the refresh path with a mocked repo."""
        client.credentials = expired_credentials
        client.connector_service.get_connector_credentials.return_value = (
            None if connector_row is not None else expired_credentials
        )

        mock_db_session = Mock()

        async def mock_aenter(*args, **kwargs):
            return mock_db_session

        async def mock_aexit(*args, **kwargs):
            return False

        mock_db = Mock()
        mock_db.__aenter__ = mock_aenter
        mock_db.__aexit__ = mock_aexit
        client.connector_service.db = mock_db

        mock_repo = Mock()
        mock_repo.get_by_user_and_type = AsyncMock(return_value=connector_row)

        mock_lock_context = AsyncMock()
        mock_lock_context.__aenter__ = AsyncMock(return_value=None)
        # return_value=False is REQUIRED: a bare AsyncMock returns a truthy
        # MagicMock from __aexit__, which silently suppresses the exception.
        mock_lock_context.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.domains.connectors.clients.base_oauth_client.get_redis_session",
                new=AsyncMock(),
            ),
            patch(
                "src.domains.connectors.clients.base_oauth_client.OAuthLock",
                return_value=mock_lock_context,
            ),
            patch(
                "src.domains.connectors.repository.ConnectorRepository",
                return_value=mock_repo,
            ),
        ):
            await client._ensure_valid_token()

    @pytest.mark.asyncio
    async def test_missing_connector_maps_to_resource_not_found_404(
        self, google_client, expired_credentials
    ):
        """Refresh with no connector row keeps the legacy 404."""
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await self._run_refresh(google_client, expired_credentials, connector_row=None)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "google_contacts connector not found"

    @pytest.mark.asyncio
    async def test_missing_credentials_maps_to_validation_error_400(
        self, google_client, expired_credentials
    ):
        """Refresh with a connector but no credentials keeps the legacy 400."""
        with pytest.raises(ValidationError) as exc_info:
            await self._run_refresh(google_client, expired_credentials, connector_row=Mock())

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "No credentials found for google_contacts connector"


# =============================================================================
# 2. Mapping — BaseMicrosoftClient._make_request_full_url
# =============================================================================


class TestMicrosoftFullUrlMapping:
    @pytest.mark.asyncio
    async def test_upstream_401_raises_authentication_error_with_reconnect_header(
        self, microsoft_client
    ):
        """Graph 401 on the nextLink path maps to AuthenticationError."""
        response = Mock(status_code=401)
        microsoft_client._http_client = _mock_http_client(response)

        with (
            patch.object(microsoft_client, "_rate_limit", AsyncMock()),
            patch.object(microsoft_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch.object(microsoft_client, "_parse_error_detail", return_value="bad token"),
            patch.object(microsoft_client, "_invalidate_connector_on_auth_failure", AsyncMock()),
        ):
            with pytest.raises(AuthenticationError) as exc_info:
                await microsoft_client._make_request_full_url(
                    "GET", "https://graph.microsoft.com/v1.0/me/messages?$skip=10"
                )

        exc = exc_info.value
        assert exc.status_code == 401
        assert exc.detail == APIMessages.connector_auth_invalid("microsoft_outlook")
        assert exc.headers == {"X-Requires-Reconnect": "true"}

    @pytest.mark.asyncio
    async def test_upstream_4xx_maps_to_connector_api_error(self, microsoft_client):
        """Graph non-auth 4xx forwards the status code unchanged."""
        response = Mock(status_code=409)
        microsoft_client._http_client = _mock_http_client(response)

        with (
            patch.object(microsoft_client, "_rate_limit", AsyncMock()),
            patch.object(microsoft_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch.object(microsoft_client, "_parse_error_detail", return_value="conflict"),
        ):
            with pytest.raises(ConnectorAPIError) as exc_info:
                await microsoft_client._make_request_full_url(
                    "GET", "https://graph.microsoft.com/v1.0/me/messages?$skip=10"
                )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "microsoft_outlook API error: conflict"

    @pytest.mark.asyncio
    async def test_network_failure_maps_to_external_service_error_503(self, microsoft_client):
        """Graph network exhaustion on the nextLink path maps to a 503."""
        microsoft_client._http_client = _mock_http_client(httpx.ConnectError("boom"))

        with (
            patch.object(microsoft_client, "_rate_limit", AsyncMock()),
            patch.object(microsoft_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await microsoft_client._make_request_full_url(
                    "GET", "https://graph.microsoft.com/v1.0/me/messages?$skip=10"
                )

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "microsoft_outlook API unavailable: boom"

    @pytest.mark.asyncio
    async def test_retry_exhaustion_maps_to_external_service_error_503(self, microsoft_client):
        """Graph 429 on every nextLink attempt exhausts retries into a 503."""
        response = Mock(status_code=429)
        microsoft_client._http_client = _mock_http_client(response)

        with (
            patch.object(microsoft_client, "_rate_limit", AsyncMock()),
            patch.object(microsoft_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch.object(microsoft_client, "_get_retry_delay", return_value=0),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await microsoft_client._make_request_full_url(
                    "GET", "https://graph.microsoft.com/v1.0/me/messages?$skip=10"
                )

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "microsoft_outlook API: max retries exceeded"


class TestGoogleRawRequestMapping:
    """Pins the 3 sites of BaseGoogleClient._make_raw_request (downloads/exports)."""

    @pytest.mark.asyncio
    async def test_upstream_4xx_maps_to_connector_api_error(self, google_client):
        """Raw-request upstream client errors forward the status code unchanged."""
        response = Mock(status_code=400, text="Bad Request")
        google_client._http_client = _mock_http_client(response)

        with (
            patch.object(google_client, "_rate_limit", AsyncMock()),
            patch.object(google_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
        ):
            with pytest.raises(ConnectorAPIError) as exc_info:
                await google_client._make_raw_request("GET", "/files/abc")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "google_contacts API error: Bad Request"

    @pytest.mark.asyncio
    async def test_network_failure_maps_to_external_service_error_503(self, google_client):
        """Raw-request network exhaustion maps to ExternalServiceError (503)."""
        google_client._http_client = _mock_http_client(httpx.ConnectError("boom"))

        with (
            patch.object(google_client, "_rate_limit", AsyncMock()),
            patch.object(google_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await google_client._make_raw_request("GET", "/files/abc")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "google_contacts API unavailable: boom"

    @pytest.mark.asyncio
    async def test_retry_exhaustion_maps_to_external_service_error_503(self, google_client):
        """Raw-request 429 on every attempt exhausts retries into a 503."""
        response = Mock(status_code=429)
        google_client._http_client = _mock_http_client(response)

        with (
            patch.object(google_client, "_rate_limit", AsyncMock()),
            patch.object(google_client, "_ensure_valid_token", AsyncMock(return_value="tok")),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await google_client._make_raw_request("GET", "/files/abc")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "google_contacts API: max retries exceeded"


# =============================================================================
# 3. Mapping — GooglePlacesClient / GoogleRoutesClient / MicrosoftTasksClient
# =============================================================================


class TestPlacesClientMapping:
    def test_missing_api_key_maps_to_external_service_error_503(self):
        """Missing global API key keeps the legacy 503 detail verbatim."""
        client = GooglePlacesClient(user_id=uuid4(), language="fr")

        with patch("src.domains.connectors.clients.google_places_client.settings") as mock_settings:
            mock_settings.google_api_key = None
            with pytest.raises(ExternalServiceError) as exc_info:
                _ = client.api_key

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == (
            "Google Places service unavailable: API key not configured"
        )

    @pytest.mark.asyncio
    async def test_upstream_4xx_maps_to_connector_api_error_with_truncated_detail(self):
        """Upstream 4xx forwards the status; response body is truncated to 200 chars."""
        client = GooglePlacesClient(user_id=uuid4(), language="fr")
        response = Mock(status_code=400, text="x" * 500)
        client._http_client = _mock_http_client(response)

        with (
            patch("src.domains.connectors.clients.google_places_client.settings") as mock_settings,
            patch.object(client, "_rate_limit", AsyncMock()),
        ):
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ConnectorAPIError) as exc_info:
                await client._make_request("POST", "/places:searchText")

        exc = exc_info.value
        assert exc.status_code == 400
        assert exc.detail == "Google Places API error: " + "x" * 200

    @pytest.mark.asyncio
    async def test_reverse_geocode_upstream_error_maps_to_connector_api_error(self):
        """Geocoding upstream errors forward the status code unchanged."""
        client = GooglePlacesClient(user_id=uuid4(), language="fr")
        response = Mock(status_code=403, text="denied")
        client._http_client = _mock_http_client(response)

        with (
            patch("src.domains.connectors.clients.google_places_client.settings") as mock_settings,
            patch.object(client, "_rate_limit", AsyncMock()),
        ):
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ConnectorAPIError) as exc_info:
                await client.reverse_geocode(48.8584, 2.2945)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Google Geocoding API error: denied"

    @pytest.mark.asyncio
    async def test_network_failure_maps_to_external_service_error_503(self):
        """Places network exhaustion keeps the legacy 503 detail verbatim."""
        client = GooglePlacesClient(user_id=uuid4(), language="fr")
        client._http_client = _mock_http_client(httpx.ConnectError("boom"))

        with (
            patch("src.domains.connectors.clients.google_places_client.settings") as mock_settings,
            patch.object(client, "_rate_limit", AsyncMock()),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ExternalServiceError) as exc_info:
                await client._make_request("POST", "/places:searchText")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Google Places API connection error: boom"

    @pytest.mark.asyncio
    async def test_retry_exhaustion_maps_to_external_service_error_503(self):
        """Places 429 on every attempt exhausts retries into a 503."""
        client = GooglePlacesClient(user_id=uuid4(), language="fr")
        response = Mock(status_code=429)
        client._http_client = _mock_http_client(response)

        with (
            patch("src.domains.connectors.clients.google_places_client.settings") as mock_settings,
            patch.object(client, "_rate_limit", AsyncMock()),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ExternalServiceError) as exc_info:
                await client._make_request("POST", "/places:searchText")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Google Places API unavailable after retries"

    @pytest.mark.asyncio
    async def test_reverse_geocode_network_failure_maps_to_external_service_error(self):
        """Geocoding network failure keeps the legacy 503 detail verbatim."""
        client = GooglePlacesClient(user_id=uuid4(), language="fr")
        client._http_client = _mock_http_client(httpx.ConnectError("boom"))

        with (
            patch("src.domains.connectors.clients.google_places_client.settings") as mock_settings,
            patch.object(client, "_rate_limit", AsyncMock()),
        ):
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ExternalServiceError) as exc_info:
                await client.reverse_geocode(48.8584, 2.2945)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Google Geocoding API unavailable: boom"


class TestRoutesClientMapping:
    def test_missing_api_key_maps_to_external_service_error_503(self):
        """Missing global API key keeps the legacy 503 detail verbatim."""
        client = GoogleRoutesClient(language="fr")

        with patch("src.domains.connectors.clients.google_routes_client.settings") as mock_settings:
            mock_settings.google_api_key = None
            with pytest.raises(ExternalServiceError) as exc_info:
                client._get_headers()

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Google API key not configured (GOOGLE_API_KEY)"

    @pytest.mark.asyncio
    async def test_upstream_error_maps_to_connector_api_error(self):
        """Routes upstream errors forward the status code unchanged."""
        client = GoogleRoutesClient(language="fr")
        response = Mock(status_code=400, text="bad request")
        client._client = _mock_http_client(response)
        client._client.is_closed = False

        with patch("src.domains.connectors.clients.google_routes_client.settings") as mock_settings:
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ConnectorAPIError) as exc_info:
                await client.compute_route(origin="Paris", destination="Lyon")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Google Routes API error: bad request"

    @pytest.mark.asyncio
    async def test_network_failure_maps_to_external_service_error_503(self):
        """Routes network failure keeps the legacy 503 detail verbatim."""
        client = GoogleRoutesClient(language="fr")
        client._client = _mock_http_client(httpx.ConnectError("boom"))
        client._client.is_closed = False

        with patch("src.domains.connectors.clients.google_routes_client.settings") as mock_settings:
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ExternalServiceError) as exc_info:
                await client.compute_route(origin="Paris", destination="Lyon")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Google Routes API unavailable: boom"

    @pytest.mark.asyncio
    async def test_matrix_upstream_error_maps_to_connector_api_error(self):
        """Matrix upstream errors forward the status code unchanged."""
        client = GoogleRoutesClient(language="fr")
        response = Mock(status_code=400, text="matrix bad")
        client._client = _mock_http_client(response)
        client._client.is_closed = False

        with patch("src.domains.connectors.clients.google_routes_client.settings") as mock_settings:
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ConnectorAPIError) as exc_info:
                await client.compute_route_matrix(origins=["Paris"], destinations=["Lyon"])

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Google Routes Matrix API error: matrix bad"

    @pytest.mark.asyncio
    async def test_matrix_network_failure_maps_to_external_service_error_503(self):
        """Matrix network failure keeps the legacy 503 detail verbatim."""
        client = GoogleRoutesClient(language="fr")
        client._client = _mock_http_client(httpx.ConnectError("boom"))
        client._client.is_closed = False

        with patch("src.domains.connectors.clients.google_routes_client.settings") as mock_settings:
            mock_settings.google_api_key = "test-key"
            with pytest.raises(ExternalServiceError) as exc_info:
                await client.compute_route_matrix(origins=["Paris"], destinations=["Lyon"])

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Google Routes Matrix API unavailable: boom"

    @pytest.mark.asyncio
    async def test_matrix_over_625_elements_maps_to_validation_error_400(self):
        """The 25x25 matrix cap keeps the legacy 400 detail verbatim."""
        client = GoogleRoutesClient(language="fr")

        with pytest.raises(ValidationError) as exc_info:
            await client.compute_route_matrix(
                origins=[f"origin-{i}" for i in range(26)],
                destinations=[f"dest-{i}" for i in range(25)],
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Route matrix limited to 625 elements (25x25 max)"


class TestMicrosoftTasksMapping:
    @pytest.mark.asyncio
    async def test_no_task_lists_maps_to_resource_not_found_404(
        self, valid_credentials, mock_connector_service
    ):
        """Empty task-list resolution keeps the legacy 404 detail verbatim."""
        client = MicrosoftTasksClient(
            user_id=uuid4(),
            credentials=valid_credentials,
            connector_service=mock_connector_service,
            rate_limit_per_second=10,
        )

        with patch.object(client, "_make_request", AsyncMock(return_value={"value": []})):
            with pytest.raises(ResourceNotFoundError) as exc_info:
                await client._resolve_list_id("@default")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "No task lists found in Microsoft To Do."


# =============================================================================
# 4. Edge contract — FastAPI renders typed exceptions like raw HTTPException
# =============================================================================


def _build_parity_app() -> FastAPI:
    """One route per typed exception, plus its raw-HTTPException twin."""
    app = FastAPI()
    auth_detail = APIMessages.connector_auth_invalid("google_gmail")

    @app.get("/typed/auth")
    async def typed_auth():
        raise AuthenticationError(detail=auth_detail, headers={"X-Requires-Reconnect": "true"})

    @app.get("/legacy/auth")
    async def legacy_auth():
        raise HTTPException(
            status_code=401, detail=auth_detail, headers={"X-Requires-Reconnect": "true"}
        )

    @app.get("/typed/upstream")
    async def typed_upstream():
        raise ConnectorAPIError(
            connector_type="google_gmail",
            status_code=403,
            detail="google_gmail API error: forbidden",
        )

    @app.get("/legacy/upstream")
    async def legacy_upstream():
        raise HTTPException(status_code=403, detail="google_gmail API error: forbidden")

    @app.get("/typed/unavailable")
    async def typed_unavailable():
        raise ExternalServiceError(
            service_name="google_gmail",
            detail="google_gmail service temporarily unavailable. Please try again later.",
            error_type="circuit_open",
            headers={"Retry-After": "30"},
        )

    @app.get("/legacy/unavailable")
    async def legacy_unavailable():
        raise HTTPException(
            status_code=503,
            detail="google_gmail service temporarily unavailable. Please try again later.",
            headers={"Retry-After": "30"},
        )

    @app.get("/typed/rate-limit")
    async def typed_rate_limit():
        raise RateLimitError(
            limit=600,
            window_seconds=60,
            retry_after=60,
            detail="Rate limit exceeded for google_gmail. Please try again later.",
        )

    @app.get("/legacy/rate-limit")
    async def legacy_rate_limit():
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for google_gmail. Please try again later.",
        )

    return app


class TestEdgeContractParity:
    @pytest.mark.parametrize(
        ("path", "expected_status", "expected_headers"),
        [
            ("auth", 401, {"X-Requires-Reconnect": "true"}),
            ("upstream", 403, {}),
            ("unavailable", 503, {"Retry-After": "30"}),
            ("rate-limit", 429, {}),
        ],
    )
    def test_typed_exception_renders_identically_to_raw_http_exception(
        self, path, expected_status, expected_headers
    ):
        """Same status, same JSON payload, same headers as the legacy raise."""
        client = TestClient(_build_parity_app(), raise_server_exceptions=False)

        typed = client.get(f"/typed/{path}")
        legacy = client.get(f"/legacy/{path}")

        assert typed.status_code == expected_status
        assert typed.status_code == legacy.status_code
        assert typed.json() == legacy.json()
        assert set(typed.json().keys()) == {"detail"}
        for header_name, header_value in expected_headers.items():
            assert typed.headers[header_name] == header_value
            assert legacy.headers[header_name] == header_value


# =============================================================================
# 5. Tool path — classification identical to the raw-HTTPException era
# =============================================================================


class TestToolPathClassification:
    def test_handle_tool_exception_keeps_internal_error_code_and_message_format(self):
        """ConnectorTool.handle_error path: same error_code, str(e) format kept."""
        from src.domains.agents.tools.runtime_helpers import handle_tool_exception

        detail = APIMessages.connector_auth_invalid("google_calendar")
        exc = AuthenticationError(detail=detail, headers={"X-Requires-Reconnect": "true"})

        output = handle_tool_exception(exc, "search_events_tool", {"query": "réunion"})

        assert output.success is False
        assert output.error_code == "INTERNAL_ERROR"
        assert output.metadata[FIELD_ERROR_TYPE] == "AuthenticationError"
        # Starlette's HTTPException.__str__ ("<status>: <detail>") is inherited,
        # so the message consumed by the LLM keeps the legacy format.
        assert output.metadata[FIELD_ERROR_MESSAGE] == f"401: {detail}"

    def test_handle_connector_api_error_still_matches_http_exception_branch(self):
        """The isinstance(HTTPException) branch still classifies typed exceptions."""
        from src.domains.agents.tools.runtime_helpers import handle_connector_api_error

        exc = ConnectorAPIError(
            connector_type="google_contacts",
            status_code=403,
            detail="google_contacts API error: forbidden",
        )

        output = handle_connector_api_error(
            exc, "search", "search_contacts_tool", {"query": "jean"}
        )

        assert output.success is False
        assert output.error_code == "http_error"
        assert output.metadata["status_code"] == 403
        assert output.message == "google_contacts API error: forbidden"
