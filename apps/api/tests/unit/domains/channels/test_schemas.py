"""Tests for Channel Pydantic schemas validation."""

from datetime import UTC, datetime
from uuid import uuid4

from src.domains.channels.models import ChannelType
from src.domains.channels.schemas import (
    ChannelBindingListResponse,
    ChannelBindingResponse,
    ChannelBindingToggleResponse,
    OTPGenerateResponse,
)


class TestOTPGenerateResponse:
    """Tests for OTPGenerateResponse schema."""

    def test_valid_response(self) -> None:
        """Should accept valid OTP response data."""
        resp = OTPGenerateResponse(
            code="123456",
            expires_in_seconds=300,
            bot_username="LIABot",
            channel_type=ChannelType.TELEGRAM,
        )
        assert resp.code == "123456"
        assert resp.expires_in_seconds == 300
        assert resp.bot_username == "LIABot"
        assert resp.channel_type == ChannelType.TELEGRAM

    def test_nullable_bot_username(self) -> None:
        """bot_username should be optional."""
        resp = OTPGenerateResponse(
            code="654321",
            expires_in_seconds=300,
            channel_type=ChannelType.TELEGRAM,
        )
        assert resp.bot_username is None


class TestChannelBindingResponse:
    """Tests for ChannelBindingResponse schema."""

    def test_valid_response(self) -> None:
        """Should accept valid binding data."""
        now = datetime.now(UTC)
        resp = ChannelBindingResponse(
            id=uuid4(),
            channel_type=ChannelType.TELEGRAM,
            channel_user_id="123456789",
            channel_username="@testuser",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        assert resp.channel_type == ChannelType.TELEGRAM
        assert resp.is_active is True
        assert resp.channel_username == "@testuser"

    def test_nullable_username(self) -> None:
        """channel_username should be optional."""
        now = datetime.now(UTC)
        resp = ChannelBindingResponse(
            id=uuid4(),
            channel_type=ChannelType.TELEGRAM,
            channel_user_id="123456789",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        assert resp.channel_username is None

    def test_from_attributes(self) -> None:
        """Should support from_attributes for ORM conversion."""
        assert ChannelBindingResponse.model_config.get("from_attributes") is True


class TestChannelBindingListResponse:
    """Tests for ChannelBindingListResponse schema."""

    def test_empty_list(self) -> None:
        """Should accept empty binding list."""
        resp = ChannelBindingListResponse(bindings=[], total=0)
        assert resp.total == 0
        assert resp.bindings == []

    def test_with_bindings(self) -> None:
        """Should accept list with bindings."""
        now = datetime.now(UTC)
        binding = ChannelBindingResponse(
            id=uuid4(),
            channel_type=ChannelType.TELEGRAM,
            channel_user_id="111",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        resp = ChannelBindingListResponse(bindings=[binding], total=1)
        assert resp.total == 1
        assert len(resp.bindings) == 1


class TestChannelBindingToggleResponse:
    """Tests for ChannelBindingToggleResponse schema."""

    def test_toggle_active(self) -> None:
        resp = ChannelBindingToggleResponse(id=uuid4(), is_active=True)
        assert resp.is_active is True

    def test_toggle_inactive(self) -> None:
        resp = ChannelBindingToggleResponse(id=uuid4(), is_active=False)
        assert resp.is_active is False
