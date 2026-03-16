"""
Unit tests for GoogleGmailClient.

Tests cover:
- MIME parsing (base64url, multipart, HTML stripping)
- OAuth token refresh
- Rate limiting
- Caching
- Error handling
- Email search and retrieval
- Email sending
"""

import asyncio
import base64
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from src.core.constants import GMAIL_FORMAT_FULL
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.schemas import ConnectorCredentials

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def user_id():
    """Generate test user ID."""
    return uuid4()


@pytest.fixture
def valid_credentials():
    """Generate valid (non-expired) credentials."""
    return ConnectorCredentials(
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),  # Valid for 1 hour
    )


@pytest.fixture
def expired_credentials():
    """Generate expired credentials."""
    return ConnectorCredentials(
        access_token="expired_access_token",
        refresh_token="test_refresh_token",
        expires_at=datetime.now(UTC) - timedelta(hours=1),  # Expired 1 hour ago
    )


@pytest.fixture
def mock_connector_service():
    """Mock ConnectorService for token refresh."""
    service = MagicMock()
    service._refresh_oauth_token = AsyncMock(
        return_value=ConnectorCredentials(
            access_token="new_access_token",
            refresh_token="test_refresh_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    service.get_connector_credentials = AsyncMock(return_value=None)
    # Mock db context manager
    service.db = MagicMock()
    service.db.__aenter__ = AsyncMock(return_value=MagicMock())
    service.db.__aexit__ = AsyncMock(return_value=None)
    return service


@pytest.fixture
def gmail_client(user_id, valid_credentials, mock_connector_service):
    """Create GoogleGmailClient instance."""
    return GoogleGmailClient(user_id, valid_credentials, mock_connector_service)


# ============================================================================
# MIME PARSING TESTS
# ============================================================================


def test_decode_base64url_valid():
    """Test base64url decoding with valid input."""
    # Gmail uses base64url encoding (- instead of +, _ instead of /)
    text = "Hello, World!"
    encoded = base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8").rstrip("=")

    decoded = GoogleGmailClient._decode_base64url(encoded)
    assert decoded == text


def test_decode_base64url_with_padding():
    """Test base64url decoding with missing padding."""
    # Test with no padding (Gmail format)
    encoded = "SGVsbG8sIFdvcmxkIQ"  # "Hello, World!" without padding
    decoded = GoogleGmailClient._decode_base64url(encoded)
    assert decoded == "Hello, World!"


def test_decode_base64url_invalid():
    """Test base64url decoding with invalid input."""
    # Should return empty string on decode error
    decoded = GoogleGmailClient._decode_base64url("invalid!!!base64")
    assert decoded == ""


def test_encode_base64url():
    """Test base64url encoding."""
    text = "Hello, World!"
    encoded = GoogleGmailClient._encode_base64url(text)

    # Verify no padding
    assert "=" not in encoded

    # Verify roundtrip
    decoded = GoogleGmailClient._decode_base64url(encoded)
    assert decoded == text


def test_extract_headers():
    """Test header extraction from Gmail message."""
    message = {
        "payload": {
            "headers": [
                {"name": "From", "value": "john@example.com"},
                {"name": "To", "value": "jane@example.com"},
                {"name": "Subject", "value": "Test Email"},
                {"name": "Date", "value": "Mon, 01 Jan 2025 12:00:00 +0000"},
                {"name": "X-Custom", "value": "ignored"},  # Should be ignored
            ]
        }
    }

    headers = GoogleGmailClient._extract_headers(message)

    assert headers["from"] == "john@example.com"
    assert headers["to"] == "jane@example.com"
    assert headers["subject"] == "Test Email"
    assert headers["date"] == "Mon, 01 Jan 2025 12:00:00 +0000"
    assert "x-custom" not in headers  # Not in whitelist


def test_extract_body_text_plain():
    """Test body extraction from text/plain message."""
    body_text = "This is a plain text email."
    encoded_body = base64.urlsafe_b64encode(body_text.encode("utf-8")).decode("utf-8").rstrip("=")

    payload = {
        "mimeType": "text/plain",
        "body": {"data": encoded_body},
    }

    extracted = GoogleGmailClient._extract_body_recursive(payload)
    assert extracted == body_text


def test_extract_body_text_html():
    """Test body extraction from text/html message with tag stripping."""
    html_body = "<html><body><h1>Hello</h1><p>This is <b>bold</b> text.</p></body></html>"
    encoded_body = base64.urlsafe_b64encode(html_body.encode("utf-8")).decode("utf-8").rstrip("=")

    payload = {
        "mimeType": "text/html",
        "body": {"data": encoded_body},
    }

    extracted = GoogleGmailClient._extract_body_recursive(payload)

    # HTML tags should be stripped
    assert "<html>" not in extracted
    assert "<body>" not in extracted
    assert "<h1>" not in extracted
    assert "<p>" not in extracted
    assert "Hello" in extracted
    assert "This is bold text." in extracted


def test_extract_body_multipart_alternative():
    """Test body extraction from multipart/alternative (text + HTML)."""
    text_body = "Plain text version"
    html_body = "<html><body><p>HTML version</p></body></html>"

    text_encoded = base64.urlsafe_b64encode(text_body.encode("utf-8")).decode("utf-8").rstrip("=")
    html_encoded = base64.urlsafe_b64encode(html_body.encode("utf-8")).decode("utf-8").rstrip("=")

    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": text_encoded}},
            {"mimeType": "text/html", "body": {"data": html_encoded}},
        ],
    }

    extracted = GoogleGmailClient._extract_body_recursive(payload)

    # Should prefer text/plain over HTML
    assert extracted == text_body


def test_extract_body_multipart_mixed_with_attachment():
    """Test body extraction from multipart/mixed (text + attachment)."""
    text_body = "Email with attachment"
    text_encoded = base64.urlsafe_b64encode(text_body.encode("utf-8")).decode("utf-8").rstrip("=")

    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": text_encoded}},
            {"mimeType": "application/pdf", "filename": "document.pdf"},  # Attachment (ignored)
        ],
    }

    extracted = GoogleGmailClient._extract_body_recursive(payload)
    assert extracted == text_body


def test_extract_body_empty():
    """Test body extraction with no body data."""
    payload = {"mimeType": "text/plain", "body": {}}

    extracted = GoogleGmailClient._extract_body_recursive(payload)
    assert extracted == ""


def test_extract_body_bounded_recursion():
    """Test that deeply nested structures don't cause stack overflow (Security 2025-12-19)."""
    # Build deeply nested multipart structure (20 levels)
    current: dict = {"mimeType": "text/plain", "body": {"data": ""}}
    for _ in range(20):
        current = {
            "mimeType": "multipart/mixed",
            "parts": [current],
        }

    # Should NOT raise RecursionError
    extracted = GoogleGmailClient._extract_body_recursive(current)
    # May return empty due to max_depth, but should not crash
    assert isinstance(extracted, str)


def test_extract_body_max_depth_limit():
    """Test that max_depth parameter limits recursion depth (Security 2025-12-19)."""
    import base64

    body_text = "deep body"
    encoded = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")

    # Create 15-level deep structure with text at bottom
    payload: dict = {"mimeType": "text/plain", "body": {"data": encoded}}
    for _ in range(15):
        payload = {"mimeType": "multipart/mixed", "parts": [payload]}

    # With max_depth=5, should return "" (text is too deep)
    result = GoogleGmailClient._extract_body_recursive(payload, max_depth=5)
    assert result == ""

    # With max_depth=20, should find the text
    result = GoogleGmailClient._extract_body_recursive(payload, max_depth=20)
    assert result == body_text


# ============================================================================
# OAUTH & TOKEN REFRESH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_ensure_valid_token_valid_token(gmail_client):
    """Test that valid token is not refreshed."""
    token = await gmail_client._ensure_valid_token()

    assert token == "test_access_token"
    gmail_client.connector_service.refresh_oauth_token.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_valid_token_expired_token(
    user_id, expired_credentials, mock_connector_service
):
    """Test automatic token refresh when expired."""
    client = GoogleGmailClient(user_id, expired_credentials, mock_connector_service)

    # Mock get_connector_credentials to return expired credentials (fresh from DB)
    # This simulates the double-check pattern where we read fresh credentials after lock
    mock_connector_service.get_connector_credentials.return_value = expired_credentials

    # Mock Redis lock and OAuthLock (now in base_google_client)
    with patch("src.domains.connectors.clients.base_oauth_client.get_redis_session") as mock_redis:
        mock_session = AsyncMock()
        mock_redis.return_value = mock_session

        # Mock OAuthLock context manager
        mock_oauth_lock = MagicMock()
        mock_oauth_lock.__aenter__ = AsyncMock()
        mock_oauth_lock.__aexit__ = AsyncMock(return_value=False)  # Don't suppress exceptions

        # Mock repository
        mock_repo = MagicMock()
        mock_connector = MagicMock()
        mock_repo.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Mock DB context manager
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)
        mock_connector_service.db = mock_db

        with patch(
            "src.domains.connectors.clients.base_oauth_client.OAuthLock",
            return_value=mock_oauth_lock,
        ):
            with patch(
                "src.domains.connectors.repository.ConnectorRepository", return_value=mock_repo
            ):
                token = await client._ensure_valid_token()

        # Should return new token
        assert token == "new_access_token"
        assert client.credentials.access_token == "new_access_token"

        # Should call refresh with fresh_credentials (from get_connector_credentials)
        mock_connector_service._refresh_oauth_token.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_token_lock_contention(user_id, expired_credentials, mock_connector_service):
    """Test token refresh with lock contention (another process refreshing)."""
    client = GoogleGmailClient(user_id, expired_credentials, mock_connector_service)

    # Mock Redis session for lock (now in base_google_client)
    with patch("src.domains.connectors.clients.base_oauth_client.get_redis_session") as mock_redis:
        mock_session = AsyncMock()
        mock_redis.return_value = mock_session

        # Mock OAuthLock context manager
        mock_oauth_lock = MagicMock()
        mock_oauth_lock.__aenter__ = AsyncMock()
        mock_oauth_lock.__aexit__ = AsyncMock()

        # Mock repository to return updated credentials after wait
        mock_repo = MagicMock()
        mock_connector = MagicMock()
        mock_connector.credentials_decrypted = ConnectorCredentials(
            access_token="refreshed_by_other_process",
            refresh_token="test_refresh_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        mock_repo.get_by_user_and_type = AsyncMock(return_value=mock_connector)

        # Mock get_connector_credentials to return updated credentials
        mock_connector_service.get_connector_credentials.return_value = ConnectorCredentials(
            access_token="refreshed_by_other_process",
            refresh_token="test_refresh_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        with patch(
            "src.domains.connectors.clients.base_oauth_client.OAuthLock",
            return_value=mock_oauth_lock,
        ):
            with patch(
                "src.domains.connectors.repository.ConnectorRepository", return_value=mock_repo
            ):
                token = await client._ensure_valid_token()

        # Should get updated credentials
        assert token == "refreshed_by_other_process"


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================


@pytest.mark.skip(reason="Rate limiting moved to Redis - see test_redis_limiter.py")
@pytest.mark.asyncio
async def test_rate_limit_throttle(gmail_client):
    """Test rate limiting throttles requests."""
    # First request - no throttle
    start = asyncio.get_event_loop().time()
    await gmail_client._rate_limit()
    first_elapsed = asyncio.get_event_loop().time() - start
    assert first_elapsed < 0.01  # Should be instant

    # Second request immediately after - should throttle
    start = asyncio.get_event_loop().time()
    await gmail_client._rate_limit()
    second_elapsed = asyncio.get_event_loop().time() - start

    # Should wait ~0.1 seconds (1/10 per second rate limit)
    assert second_elapsed >= 0.08  # Allow some tolerance


@pytest.mark.skip(reason="Rate limiting moved to Redis - see test_redis_limiter.py")
@pytest.mark.asyncio
@pytest.mark.integration  # Requires Redis connection
async def test_rate_limit_no_throttle_after_interval(gmail_client):
    """Test no throttling after interval passes.

    Note: This test requires Redis to be running. It's marked as integration
    because it tests the actual Redis rate limiter behavior, not just the
    Gmail client logic.
    """
    await gmail_client._rate_limit()

    # Wait for rate limit interval to pass
    await asyncio.sleep(0.11)  # Slightly more than 0.1 second interval

    # Should not throttle
    start = asyncio.get_event_loop().time()
    await gmail_client._rate_limit()
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 0.01


# ============================================================================
# HTTP CLIENT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_client_creates_once(gmail_client):
    """Test HTTP client is created once and reused."""
    client1 = await gmail_client._get_client()
    client2 = await gmail_client._get_client()

    assert client1 is client2  # Same instance
    assert isinstance(client1, httpx.AsyncClient)


@pytest.mark.asyncio
async def test_close_cleanup(gmail_client):
    """Test close() cleanup."""
    await gmail_client._get_client()
    assert gmail_client._http_client is not None

    await gmail_client.close()
    assert gmail_client._http_client is None


# ============================================================================
# API REQUEST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_make_request_success(gmail_client):
    """Test successful API request."""
    mock_response = {"messages": [], "resultSizeEstimate": 0}

    with patch.object(gmail_client, "_rate_limit", AsyncMock()):
        with patch.object(gmail_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.content = b'{"messages": [], "resultSizeEstimate": 0}'
            mock_client.get = AsyncMock(return_value=mock_response_obj)
            mock_get_client.return_value = mock_client

            result = await gmail_client._make_request(
                "GET", "/users/me/messages", params={"q": "test"}
            )

            assert result == mock_response
            mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_make_request_401_unauthorized(gmail_client):
    """Test 401 Unauthorized error handling."""
    with patch.object(gmail_client, "_rate_limit", AsyncMock()):
        with patch.object(gmail_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await gmail_client._make_request("GET", "/users/me/messages")

            assert exc_info.value.status_code == 401
            # BaseGoogleClient uses different error format
            assert "google_gmail" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_make_request_403_forbidden(gmail_client):
    """Test 403 Forbidden error handling."""
    with patch.object(gmail_client, "_rate_limit", AsyncMock()):
        with patch.object(gmail_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.text = "Insufficient permissions"
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await gmail_client._make_request("GET", "/users/me/messages")

            assert exc_info.value.status_code == 403
            assert "insufficient permissions" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_make_request_404_not_found(gmail_client):
    """Test 404 Not Found error handling."""
    with patch.object(gmail_client, "_rate_limit", AsyncMock()):
        with patch.object(gmail_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Message not found"
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await gmail_client._make_request("GET", "/users/me/messages/123")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_make_request_429_rate_limit(gmail_client):
    """Test 429 Too Many Requests error handling - retries then fails."""
    with patch.object(gmail_client, "_rate_limit", AsyncMock()):
        with patch.object(gmail_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = "Rate limit exceeded"
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):  # Speed up test
                with pytest.raises(HTTPException) as exc_info:
                    await gmail_client._make_request("GET", "/users/me/messages", max_retries=3)

            # After max retries, should raise HTTPException with 503 (service unavailable)
            assert exc_info.value.status_code == 503
            assert "max retries exceeded" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_make_request_network_error(gmail_client):
    """Test network error handling - retries then fails."""
    with patch.object(gmail_client, "_rate_limit", AsyncMock()):
        with patch.object(gmail_client, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
            mock_get_client.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):  # Speed up test
                with pytest.raises(HTTPException) as exc_info:
                    await gmail_client._make_request("GET", "/users/me/messages", max_retries=3)

            assert exc_info.value.status_code == 503
            assert "connection failed" in exc_info.value.detail.lower()


# ============================================================================
# EMAIL SEARCH TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_search_emails_success(gmail_client):
    """Test search_emails with valid results."""
    mock_search_response = {
        "messages": [{"id": "msg1"}, {"id": "msg2"}],
        "resultSizeEstimate": 2,
    }

    mock_message_1 = {
        "id": "msg1",
        "threadId": "thread1",
        "snippet": "First email...",
        "internalDate": "1609459200000",
    }

    mock_message_2 = {
        "id": "msg2",
        "threadId": "thread2",
        "snippet": "Second email...",
        "internalDate": "1609545600000",
    }

    with patch.object(gmail_client, "_make_request") as mock_request:
        with patch(
            "src.domains.connectors.clients.google_gmail_client.get_redis_cache"
        ) as mock_cache:
            # Setup mocks
            mock_request.side_effect = [
                mock_search_response,
                mock_message_1,
                mock_message_2,
            ]

            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)  # No cache
            mock_redis.setex = AsyncMock()
            mock_cache.return_value = mock_redis

            # Execute
            result = await gmail_client.search_emails(query="from:john@example.com", max_results=10)

            # Verify
            assert result["resultSizeEstimate"] == 2
            assert len(result["messages"]) == 2
            assert result["messages"][0]["id"] == "msg1"
            assert result["messages"][1]["id"] == "msg2"
            assert result["from_cache"] is False

            # Verify cache was set (3 times: 2 individual messages + 1 search result)
            assert mock_redis.setex.call_count == 3


@pytest.mark.asyncio
async def test_search_emails_cache_hit(gmail_client):
    """Test search_emails returns cached results."""
    import json

    cached_data = {
        "messages": [{"id": "cached_msg"}],
        "resultSizeEstimate": 1,
        "cached_at": "2025-01-01T12:00:00",
    }

    with patch("src.domains.connectors.clients.google_gmail_client.get_redis_cache") as mock_cache:
        mock_redis = AsyncMock()
        # get_redis_cache returns JSON string, not dict
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))
        mock_cache.return_value = mock_redis

        result = await gmail_client.search_emails(query="test", use_cache=True)

        assert result["from_cache"] is True
        assert result["messages"][0]["id"] == "cached_msg"
        assert result["cached_at"] == "2025-01-01T12:00:00"


# ============================================================================
# GET MESSAGE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_message_success(gmail_client):
    """Test get_message retrieves single message."""
    mock_message = {
        "id": "msg123",
        "threadId": "thread123",
        "labelIds": ["INBOX"],
        "snippet": "Test email",
        "payload": {
            "headers": [{"name": "Subject", "value": "Test"}],
            "mimeType": "text/plain",
        },
    }

    with patch.object(gmail_client, "_make_request") as mock_request:
        with patch(
            "src.domains.connectors.clients.google_gmail_client.get_redis_cache"
        ) as mock_cache:
            mock_request.return_value = mock_message

            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.setex = AsyncMock()
            mock_cache.return_value = mock_redis

            result = await gmail_client.get_message("msg123", format=GMAIL_FORMAT_FULL)

            assert result["id"] == "msg123"
            assert result["from_cache"] is False
            mock_request.assert_called_once_with(
                "GET", "/users/me/messages/msg123", params={"format": GMAIL_FORMAT_FULL}
            )


# ============================================================================
# SEND EMAIL TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_send_email_success(gmail_client):
    """Test send_email sends plain text email."""
    mock_response = {
        "id": "sent_msg123",
        "threadId": "thread123",
        "labelIds": ["SENT"],
    }

    with patch.object(gmail_client, "_make_request") as mock_request:
        mock_request.return_value = mock_response

        result = await gmail_client.send_email(
            to="john@example.com",
            subject="Test Email",
            body="Hello, World!",
        )

        assert result["id"] == "sent_msg123"
        mock_request.assert_called_once()

        # Verify request structure
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/users/me/messages/send"
        assert "raw" in call_args[1]["json_data"]


@pytest.mark.asyncio
async def test_send_email_html(gmail_client):
    """Test send_email sends HTML email."""
    mock_response = {"id": "sent_msg456"}

    with patch.object(gmail_client, "_make_request") as mock_request:
        mock_request.return_value = mock_response

        result = await gmail_client.send_email(
            to="john@example.com",
            subject="HTML Email",
            body="<h1>Hello</h1><p>World</p>",
            is_html=True,
        )

        assert result["id"] == "sent_msg456"
        mock_request.assert_called_once()


@pytest.mark.asyncio
async def test_send_email_with_cc_bcc(gmail_client):
    """Test send_email with CC and BCC recipients."""
    mock_response = {"id": "sent_msg789"}

    with patch.object(gmail_client, "_make_request") as mock_request:
        mock_request.return_value = mock_response

        result = await gmail_client.send_email(
            to="john@example.com",
            subject="Test",
            body="Body",
            cc="jane@example.com",
            bcc="admin@example.com",
        )

        assert result["id"] == "sent_msg789"


# ============================================================================
# MESSAGE NORMALIZATION TESTS
# ============================================================================


@pytest.mark.unit
class TestNormalizeMessageFields:
    """Tests for _normalize_message_fields — unified provider format.

    Google Gmail messages store from/subject/to/cc in payload.headers.
    This normalization extracts them to top-level fields, matching the
    format already produced by Apple and Microsoft normalizers.
    """

    def test_metadata_format_extracts_headers(self):
        """Test header extraction to top-level in metadata format."""
        msg = {
            "id": "msg-1",
            "snippet": "Preview text",
            "internalDate": "1737000000000",
            "payload": {
                "headers": [
                    {"name": "From", "value": "alice@gmail.com"},
                    {"name": "To", "value": "bob@example.com"},
                    {"name": "Cc", "value": "carol@example.com"},
                    {"name": "Subject", "value": "Meeting tomorrow"},
                    {"name": "Date", "value": "Mon, 15 Jan 2026 14:00:00 +0000"},
                ]
            },
        }

        GoogleGmailClient._normalize_message_fields(msg, "metadata")

        assert msg["from"] == "alice@gmail.com"
        assert msg["to"] == "bob@example.com"
        assert msg["cc"] == "carol@example.com"
        assert msg["subject"] == "Meeting tomorrow"
        assert msg["date"] == "Mon, 15 Jan 2026 14:00:00 +0000"
        assert msg["_provider"] == "google"
        # Original payload preserved
        assert len(msg["payload"]["headers"]) == 5

    def test_metadata_format_does_not_extract_body(self):
        """Test that body is NOT extracted in metadata format (no body data available)."""
        msg = {
            "id": "msg-2",
            "payload": {
                "headers": [{"name": "Subject", "value": "Test"}],
                "mimeType": "text/plain",
                "body": {"size": 0},
            },
        }

        GoogleGmailClient._normalize_message_fields(msg, "metadata")

        assert "body" not in msg

    def test_full_format_extracts_body(self):
        """Test that body IS extracted in full format."""
        import base64

        body_text = "Hello, World!"
        encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")

        msg = {
            "id": "msg-3",
            "payload": {
                "headers": [{"name": "Subject", "value": "Test"}],
                "mimeType": "text/plain",
                "body": {"data": encoded_body},
            },
        }

        GoogleGmailClient._normalize_message_fields(msg, "full")

        assert msg["body"] == "Hello, World!"
        assert msg["subject"] == "Test"

    def test_existing_top_level_fields_not_overwritten(self):
        """Test that pre-existing top-level fields are not overwritten."""
        msg = {
            "id": "msg-4",
            "from": "existing@example.com",
            "subject": "Existing subject",
            "_provider": "already-set",
            "payload": {
                "headers": [
                    {"name": "From", "value": "header@example.com"},
                    {"name": "Subject", "value": "Header subject"},
                ]
            },
        }

        GoogleGmailClient._normalize_message_fields(msg, "metadata")

        # Original values preserved
        assert msg["from"] == "existing@example.com"
        assert msg["subject"] == "Existing subject"
        assert msg["_provider"] == "already-set"

    def test_empty_payload_no_crash(self):
        """Test graceful handling of missing payload."""
        msg = {"id": "msg-5"}

        GoogleGmailClient._normalize_message_fields(msg, "metadata")

        assert msg["_provider"] == "google"
        assert "from" not in msg
        assert "subject" not in msg

    def test_multipart_body_extraction(self):
        """Test body extraction from multipart message in full format."""
        import base64

        body_text = "Plain text body"
        encoded = base64.urlsafe_b64encode(body_text.encode()).decode().rstrip("=")

        msg = {
            "id": "msg-6",
            "payload": {
                "headers": [],
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": encoded},
                    },
                    {
                        "mimeType": "text/html",
                        "body": {"data": base64.urlsafe_b64encode(b"<p>HTML</p>").decode()},
                    },
                ],
            },
        }

        GoogleGmailClient._normalize_message_fields(msg, "full")

        # text/plain preferred over text/html
        assert msg["body"] == "Plain text body"
