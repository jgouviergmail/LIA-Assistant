"""Tests for ChannelService business logic."""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.channels.models import ChannelType
from src.domains.channels.service import ChannelService


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create service with mocked dependencies."""
    svc = ChannelService(mock_db)
    svc.repository = AsyncMock()
    return svc


@pytest.fixture
def sample_binding():
    """Create a mock UserChannelBinding instance."""
    binding = MagicMock()
    binding.id = uuid4()
    binding.user_id = uuid4()
    binding.channel_type = "telegram"
    binding.channel_user_id = "123456789"
    binding.channel_username = "@testuser"
    binding.is_active = True
    return binding


class TestGenerateOTP:
    """Tests for OTP generation."""

    @pytest.mark.asyncio
    async def test_generate_otp_success(self, service) -> None:
        """Should generate OTP code and store in Redis."""
        user_id = uuid4()
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        with patch(
            "src.infrastructure.cache.redis.get_redis_session",
            return_value=mock_redis,
        ):
            code, ttl = await service.generate_otp(user_id, ChannelType.TELEGRAM)

        assert len(code) == 6
        assert code.isdigit()
        assert ttl == 300
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_otp_rejects_existing_binding(self, service) -> None:
        """Should reject OTP generation when user already has a binding."""
        user_id = uuid4()
        existing = MagicMock()
        service.repository.get_by_user_and_type = AsyncMock(return_value=existing)

        from src.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="already have a telegram account linked"):
            await service.generate_otp(user_id, ChannelType.TELEGRAM)

    @pytest.mark.asyncio
    async def test_generate_otp_stores_correct_data(self, service) -> None:
        """OTP Redis data should contain user_id and channel_type."""
        user_id = uuid4()
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)

        mock_redis = AsyncMock()
        stored_data = {}

        async def capture_setex(key, ttl, data):
            stored_data["key"] = key
            stored_data["ttl"] = ttl
            stored_data["data"] = json.loads(data)

        mock_redis.setex = capture_setex

        with patch(
            "src.infrastructure.cache.redis.get_redis_session",
            return_value=mock_redis,
        ):
            code, _ = await service.generate_otp(user_id, ChannelType.TELEGRAM)

        assert stored_data["data"]["user_id"] == str(user_id)
        assert stored_data["data"]["channel_type"] == "telegram"
        assert stored_data["key"].startswith("channel_otp:")


class TestVerifyOTP:
    """Tests for OTP verification (static method)."""

    @pytest.mark.asyncio
    async def test_verify_valid_otp(self) -> None:
        """Should return user data for valid OTP."""
        user_id = str(uuid4())
        otp_data = json.dumps({"user_id": user_id, "channel_type": "telegram"})

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # No brute-force block

        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[otp_data, 1])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch(
            "src.infrastructure.cache.redis.get_redis_session",
            return_value=mock_redis,
        ):
            result = await ChannelService.verify_otp(
                code="123456",
                channel_type="telegram",
                channel_user_id="999",
            )

        assert result is not None
        assert result["user_id"] == user_id
        assert result["channel_type"] == "telegram"

    @pytest.mark.asyncio
    async def test_verify_invalid_otp_returns_none(self) -> None:
        """Should return None for invalid/expired OTP."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # No brute-force block

        # First pipeline: get+delete for OTP lookup — returns None (not found)
        mock_pipe1 = AsyncMock()
        mock_pipe1.execute = AsyncMock(return_value=[None, 0])

        # Second pipeline: incr+expire for attempt tracking
        mock_pipe2 = AsyncMock()
        mock_pipe2.execute = AsyncMock(return_value=[1, True])

        mock_redis.pipeline = MagicMock(side_effect=[mock_pipe1, mock_pipe2])

        with patch(
            "src.infrastructure.cache.redis.get_redis_session",
            return_value=mock_redis,
        ):
            result = await ChannelService.verify_otp(
                code="000000",
                channel_type="telegram",
                channel_user_id="999",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_verify_otp_brute_force_blocked(self) -> None:
        """Should return None when chat_id is blocked (too many attempts)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"5")  # 5 attempts (max reached)

        with patch(
            "src.infrastructure.cache.redis.get_redis_session",
            return_value=mock_redis,
        ):
            result = await ChannelService.verify_otp(
                code="123456",
                channel_type="telegram",
                channel_user_id="999",
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_verify_otp_type_mismatch(self) -> None:
        """Should return None when channel_type doesn't match OTP data."""
        otp_data = json.dumps({"user_id": str(uuid4()), "channel_type": "discord"})

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        mock_pipe = AsyncMock()
        mock_pipe.execute = AsyncMock(return_value=[otp_data, 1])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch(
            "src.infrastructure.cache.redis.get_redis_session",
            return_value=mock_redis,
        ):
            result = await ChannelService.verify_otp(
                code="123456",
                channel_type="telegram",
                channel_user_id="999",
            )

        assert result is None


class TestCreateBinding:
    """Tests for binding creation."""

    @pytest.mark.asyncio
    async def test_create_binding_success(self, service) -> None:
        """Should create binding when no conflicts exist."""
        user_id = uuid4()
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)
        service.repository.get_by_channel_id = AsyncMock(return_value=None)

        mock_binding = MagicMock()
        service.repository.create = AsyncMock(return_value=mock_binding)

        result = await service.create_binding(
            user_id=user_id,
            channel_type="telegram",
            channel_user_id="123456789",
            channel_username="@testuser",
        )

        assert result == mock_binding
        service.repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_binding_rejects_duplicate_user_type(self, service) -> None:
        """Should reject when user already has a binding for this channel type."""
        user_id = uuid4()
        existing = MagicMock()
        service.repository.get_by_user_and_type = AsyncMock(return_value=existing)

        from src.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="already exists for this user"):
            await service.create_binding(
                user_id=user_id,
                channel_type="telegram",
                channel_user_id="123456789",
            )

    @pytest.mark.asyncio
    async def test_create_binding_rejects_duplicate_channel_id(self, service) -> None:
        """Should reject when channel_user_id is already linked to another user."""
        user_id = uuid4()
        service.repository.get_by_user_and_type = AsyncMock(return_value=None)
        service.repository.get_by_channel_id = AsyncMock(return_value=MagicMock())

        from src.core.exceptions import ValidationError

        with pytest.raises(ValidationError, match="already linked to another user"):
            await service.create_binding(
                user_id=user_id,
                channel_type="telegram",
                channel_user_id="123456789",
            )


class TestToggleBinding:
    """Tests for binding toggle."""

    @pytest.mark.asyncio
    async def test_toggle_active_to_inactive(self, service, sample_binding) -> None:
        """Should toggle active binding to inactive."""
        sample_binding.is_active = True
        service.repository.get_by_id = AsyncMock(return_value=sample_binding)

        toggled = MagicMock()
        toggled.is_active = False
        service.repository.update = AsyncMock(return_value=toggled)

        result = await service.toggle_binding(sample_binding.id, sample_binding.user_id)
        assert result.is_active is False
        service.repository.update.assert_called_once_with(sample_binding, {"is_active": False})

    @pytest.mark.asyncio
    async def test_toggle_wrong_user_raises(self, service, sample_binding) -> None:
        """Should raise ResourceNotFoundError for wrong user."""
        service.repository.get_by_id = AsyncMock(return_value=sample_binding)

        from src.core.exceptions import ResourceNotFoundError

        with pytest.raises(ResourceNotFoundError):
            await service.toggle_binding(sample_binding.id, uuid4())


class TestDeleteBinding:
    """Tests for binding deletion."""

    @pytest.mark.asyncio
    async def test_delete_binding_success(self, service, sample_binding) -> None:
        """Should delete binding when ownership is valid."""
        service.repository.get_by_id = AsyncMock(return_value=sample_binding)
        service.repository.delete = AsyncMock()

        await service.delete_binding(sample_binding.id, sample_binding.user_id)
        service.repository.delete.assert_called_once_with(sample_binding)

    @pytest.mark.asyncio
    async def test_delete_wrong_user_raises(self, service, sample_binding) -> None:
        """Should raise ResourceNotFoundError for wrong user."""
        service.repository.get_by_id = AsyncMock(return_value=sample_binding)

        from src.core.exceptions import ResourceNotFoundError

        with pytest.raises(ResourceNotFoundError):
            await service.delete_binding(sample_binding.id, uuid4())

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(self, service) -> None:
        """Should raise ResourceNotFoundError for non-existent binding."""
        service.repository.get_by_id = AsyncMock(return_value=None)

        from src.core.exceptions import ResourceNotFoundError

        with pytest.raises(ResourceNotFoundError):
            await service.delete_binding(uuid4(), uuid4())
