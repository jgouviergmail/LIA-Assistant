"""
Unit tests for domains/notifications/schemas.py.

Tests Pydantic schemas for notifications API.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.notifications.schemas import (
    BroadcastInfo,
    BroadcastMessageRequest,
    BroadcastMessageResponse,
    TokenInfo,
    TokenRegisterRequest,
    TokenRegisterResponse,
    TokenUnregisterRequest,
    TokenUnregisterResponse,
    UnreadBroadcastsResponse,
    UserTokensResponse,
)


@pytest.mark.unit
class TestTokenRegisterRequest:
    """Tests for TokenRegisterRequest schema."""

    def test_valid_android_token(self):
        """Test registering a valid Android token."""
        request = TokenRegisterRequest(
            token="fcm_token_12345678901234567890",
            device_type="android",
            device_name="Samsung Galaxy S21",
        )

        assert request.token == "fcm_token_12345678901234567890"
        assert request.device_type == "android"
        assert request.device_name == "Samsung Galaxy S21"

    def test_valid_ios_token(self):
        """Test registering a valid iOS token."""
        request = TokenRegisterRequest(
            token="fcm_token_ios_device",
            device_type="ios",
        )

        assert request.device_type == "ios"
        assert request.device_name is None

    def test_valid_web_token(self):
        """Test registering a valid web token."""
        request = TokenRegisterRequest(
            token="fcm_token_web_client",
            device_type="web",
            device_name="Chrome Browser",
        )

        assert request.device_type == "web"

    def test_token_min_length(self):
        """Test token minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            TokenRegisterRequest(
                token="short",  # Less than 10 chars
                device_type="android",
            )

        assert "String should have at least 10 characters" in str(exc_info.value)

    def test_invalid_device_type(self):
        """Test invalid device type."""
        with pytest.raises(ValidationError) as exc_info:
            TokenRegisterRequest(
                token="valid_token_123456",
                device_type="windows",  # Not valid
            )

        assert "String should match pattern" in str(exc_info.value)

    def test_device_name_max_length(self):
        """Test device name maximum length."""
        with pytest.raises(ValidationError):
            TokenRegisterRequest(
                token="valid_token_123456",
                device_type="android",
                device_name="x" * 101,  # Over 100 chars
            )


@pytest.mark.unit
class TestTokenRegisterResponse:
    """Tests for TokenRegisterResponse schema."""

    def test_valid_response(self):
        """Test valid registration response."""
        now = datetime.now(UTC)
        response = TokenRegisterResponse(
            id=uuid4(),
            device_type="android",
            device_name="My Phone",
            created_at=now,
        )

        assert response.device_type == "android"
        assert response.message == "Token registered successfully"

    def test_default_message(self):
        """Test default message value."""
        response = TokenRegisterResponse(
            id=uuid4(),
            device_type="ios",
            device_name=None,
            created_at=datetime.now(UTC),
        )

        assert response.message == "Token registered successfully"


@pytest.mark.unit
class TestTokenUnregisterRequest:
    """Tests for TokenUnregisterRequest schema."""

    def test_valid_unregister(self):
        """Test valid unregister request."""
        request = TokenUnregisterRequest(token="fcm_token_to_remove")
        assert request.token == "fcm_token_to_remove"

    def test_token_min_length(self):
        """Test token minimum length."""
        with pytest.raises(ValidationError):
            TokenUnregisterRequest(token="short")


@pytest.mark.unit
class TestTokenUnregisterResponse:
    """Tests for TokenUnregisterResponse schema."""

    def test_success_response(self):
        """Test successful unregister response."""
        response = TokenUnregisterResponse(
            success=True,
            message="Token unregistered successfully",
        )

        assert response.success is True
        assert "successfully" in response.message

    def test_failure_response(self):
        """Test failed unregister response."""
        response = TokenUnregisterResponse(
            success=False,
            message="Token not found",
        )

        assert response.success is False


@pytest.mark.unit
class TestTokenInfo:
    """Tests for TokenInfo schema."""

    def test_valid_token_info(self):
        """Test valid token info."""
        now = datetime.now(UTC)
        info = TokenInfo(
            id=uuid4(),
            device_type="android",
            device_name="My Device",
            is_active=True,
            last_used_at=now,
            created_at=now,
        )

        assert info.is_active is True
        assert info.device_type == "android"

    def test_token_info_without_last_used(self):
        """Test token info without last_used_at."""
        now = datetime.now(UTC)
        info = TokenInfo(
            id=uuid4(),
            device_type="web",
            device_name=None,
            is_active=True,
            last_used_at=None,
            created_at=now,
        )

        assert info.last_used_at is None


@pytest.mark.unit
class TestUserTokensResponse:
    """Tests for UserTokensResponse schema."""

    def test_empty_tokens(self):
        """Test response with no tokens."""
        response = UserTokensResponse(tokens=[], total=0)

        assert len(response.tokens) == 0
        assert response.total == 0

    def test_with_tokens(self):
        """Test response with tokens."""
        now = datetime.now(UTC)
        token = TokenInfo(
            id=uuid4(),
            device_type="ios",
            device_name="iPhone",
            is_active=True,
            last_used_at=now,
            created_at=now,
        )

        response = UserTokensResponse(tokens=[token], total=1)

        assert len(response.tokens) == 1
        assert response.total == 1


@pytest.mark.unit
class TestBroadcastMessageRequest:
    """Tests for BroadcastMessageRequest schema."""

    def test_valid_broadcast(self):
        """Test valid broadcast request."""
        request = BroadcastMessageRequest(
            message="Important announcement for all users",
        )

        assert request.message == "Important announcement for all users"
        assert request.expires_in_days is None

    def test_broadcast_with_expiry(self):
        """Test broadcast with expiry."""
        request = BroadcastMessageRequest(
            message="Time-limited offer",
            expires_in_days=7,
        )

        assert request.expires_in_days == 7

    def test_message_min_length(self):
        """Test message minimum length."""
        with pytest.raises(ValidationError):
            BroadcastMessageRequest(message="")

    def test_message_max_length(self):
        """Test message maximum length."""
        with pytest.raises(ValidationError):
            BroadcastMessageRequest(message="x" * 1001)

    def test_expires_in_days_min(self):
        """Test expires_in_days minimum value."""
        with pytest.raises(ValidationError):
            BroadcastMessageRequest(
                message="Test",
                expires_in_days=0,
            )

    def test_expires_in_days_max(self):
        """Test expires_in_days maximum value."""
        with pytest.raises(ValidationError):
            BroadcastMessageRequest(
                message="Test",
                expires_in_days=366,
            )

    def test_expires_in_days_boundaries(self):
        """Test expires_in_days valid boundaries."""
        # Min valid (1 day)
        request = BroadcastMessageRequest(message="Test", expires_in_days=1)
        assert request.expires_in_days == 1

        # Max valid (365 days)
        request = BroadcastMessageRequest(message="Test", expires_in_days=365)
        assert request.expires_in_days == 365


@pytest.mark.unit
class TestBroadcastMessageResponse:
    """Tests for BroadcastMessageResponse schema."""

    def test_successful_broadcast(self):
        """Test successful broadcast response."""
        response = BroadcastMessageResponse(
            success=True,
            broadcast_id=uuid4(),
            total_users=100,
            fcm_sent=95,
            fcm_failed=5,
        )

        assert response.success is True
        assert response.total_users == 100
        assert response.fcm_sent == 95
        assert response.fcm_failed == 5


@pytest.mark.unit
class TestBroadcastInfo:
    """Tests for BroadcastInfo schema."""

    def test_valid_broadcast_info(self):
        """Test valid broadcast info."""
        now = datetime.now(UTC)
        info = BroadcastInfo(
            id=uuid4(),
            message="Important message",
            sent_at=now,
            sender_name="Admin",
        )

        assert info.message == "Important message"
        assert info.sender_name == "Admin"

    def test_broadcast_info_without_sender(self):
        """Test broadcast info without sender name."""
        now = datetime.now(UTC)
        info = BroadcastInfo(
            id=uuid4(),
            message="System message",
            sent_at=now,
        )

        assert info.sender_name is None


@pytest.mark.unit
class TestUnreadBroadcastsResponse:
    """Tests for UnreadBroadcastsResponse schema."""

    def test_empty_broadcasts(self):
        """Test response with no unread broadcasts."""
        response = UnreadBroadcastsResponse(broadcasts=[], total=0)

        assert len(response.broadcasts) == 0
        assert response.total == 0

    def test_with_broadcasts(self):
        """Test response with broadcasts."""
        now = datetime.now(UTC)
        broadcast = BroadcastInfo(
            id=uuid4(),
            message="New feature available",
            sent_at=now,
        )

        response = UnreadBroadcastsResponse(broadcasts=[broadcast], total=1)

        assert len(response.broadcasts) == 1
        assert response.total == 1
