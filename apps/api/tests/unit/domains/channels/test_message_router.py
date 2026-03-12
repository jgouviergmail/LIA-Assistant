"""Tests for ChannelMessageRouter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.message_router import ChannelMessageRouter
from src.domains.channels.models import ChannelType

# Patch targets — source modules (lazy imports inside functions)
_PATCH_DB_CTX = "src.infrastructure.database.session.get_db_context"
_PATCH_REPO = "src.domains.channels.repository.UserChannelBindingRepository"
_PATCH_RATE_LIMITER = "src.infrastructure.rate_limiting.redis_limiter.RedisRateLimiter"
_PATCH_USER_SERVICE = "src.domains.users.service.UserService"
_PATCH_CONV_CACHE = "src.infrastructure.cache.conversation_cache.get_conversation_id_cached"
_PATCH_INBOUND_HANDLER = "src.domains.channels.inbound_handler.InboundMessageHandler"
_PATCH_HITL_STORE = "src.domains.agents.utils.hitl_store.HITLStore"
_PATCH_BOT_MESSAGE = "src.infrastructure.channels.telegram.formatter.get_bot_message"


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)  # Lock acquired by default
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_sender() -> AsyncMock:
    sender = AsyncMock()
    sender.send_message = AsyncMock(return_value="msg_1")
    sender.send_typing_indicator = AsyncMock()
    return sender


@pytest.fixture
def router(mock_redis: AsyncMock, mock_sender: AsyncMock) -> ChannelMessageRouter:
    return ChannelMessageRouter(redis=mock_redis, sender=mock_sender)


@pytest.fixture
def text_message() -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        text="Hello bot",
        message_id="42",
        raw_data={},
    )


def _make_binding(user_id=None, is_active=True):
    """Create a mock UserChannelBinding."""
    binding = MagicMock()
    binding.user_id = user_id or uuid4()
    binding.is_active = is_active
    binding.channel_type = "telegram"
    binding.channel_user_id = "12345"
    return binding


def _make_user(user_id=None, is_active=True, language="fr", timezone="Europe/Paris"):
    """Create a mock User."""
    user = MagicMock()
    user.id = user_id or uuid4()
    user.is_active = is_active
    user.language = language
    user.timezone = timezone
    user.memory_enabled = True
    return user


def _make_db_context(mock_db=None):
    """Create a mock async context manager for get_db_context()."""
    if mock_db is None:
        mock_db = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# =============================================================================
# No binding (unbound user)
# =============================================================================


class TestUnboundUser:
    """Tests for messages from users without a channel binding."""

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Unbound message")
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_no_binding_sends_unbound_message(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """User without binding receives 'unbound' message."""
        mock_db_ctx.return_value = _make_db_context()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=None)

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()
        sent_msg = mock_sender.send_message.call_args[0][1]
        assert sent_msg.text == "Unbound message"

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Unbound message")
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_inactive_binding_sends_unbound_message(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Inactive binding treated same as no binding."""
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding(is_active=False)
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()


# =============================================================================
# Rate limiting
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting."""

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Busy message")
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_rate_limited_sends_busy_message(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Rate limited user receives 'busy' message."""
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        # Rate limit exceeded
        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=False)

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()
        sent_msg = mock_sender.send_message.call_args[0][1]
        assert sent_msg.text == "Busy message"


# =============================================================================
# Per-user lock
# =============================================================================


class TestUserLock:
    """Tests for per-user Redis lock."""

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Busy message")
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_lock_not_acquired_sends_busy(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """If lock is already held, send 'busy' message."""
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)

        # Lock NOT acquired (another message being processed)
        mock_redis.set = AsyncMock(return_value=False)

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()

    @pytest.mark.asyncio
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_SERVICE)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_lock_released_after_success(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_service_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Lock should be released in finally block after successful processing."""
        mock_db_ctx.return_value = _make_db_context()
        user_id = uuid4()
        binding = _make_binding(user_id=user_id)
        user = _make_user(user_id=user_id)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        mock_user_svc = mock_user_service_cls.return_value
        mock_user_svc.get_user_by_id = AsyncMock(return_value=user)

        mock_handler_cls.return_value.handle = AsyncMock()

        await router.route_message(text_message)

        # Verify lock was released
        mock_redis.delete.assert_called_once()
        lock_key = mock_redis.delete.call_args[0][0]
        assert "channel_msg_lock:" in lock_key

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_SERVICE)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_lock_released_after_handler_error(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_service_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Lock should be released even when handler raises an exception."""
        mock_db_ctx.return_value = _make_db_context()
        user_id = uuid4()
        binding = _make_binding(user_id=user_id)
        user = _make_user(user_id=user_id)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        mock_user_svc = mock_user_service_cls.return_value
        mock_user_svc.get_user_by_id = AsyncMock(return_value=user)

        mock_handler_cls.return_value.handle = AsyncMock(side_effect=RuntimeError("Pipeline crash"))

        # Should NOT raise — error is caught and error message is sent
        await router.route_message(text_message)

        # Lock still released despite error
        mock_redis.delete.assert_called_once()
        # Error message sent to user
        assert mock_sender.send_message.call_count >= 1


# =============================================================================
# Successful dispatch
# =============================================================================


class TestSuccessfulDispatch:
    """Tests for successful message dispatching."""

    @pytest.mark.asyncio
    @patch(_PATCH_HITL_STORE)
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value="conv-123")
    @patch(_PATCH_USER_SERVICE)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_dispatches_to_inbound_handler(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_service_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        mock_hitl_store_cls: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Happy path: message dispatched to InboundMessageHandler.handle()."""
        mock_db_ctx.return_value = _make_db_context()
        user_id = uuid4()
        binding = _make_binding(user_id=user_id)
        user = _make_user(user_id=user_id, language="en", timezone="America/New_York")

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        mock_user_svc = mock_user_service_cls.return_value
        mock_user_svc.get_user_by_id = AsyncMock(return_value=user)

        mock_hitl_store = mock_hitl_store_cls.return_value
        mock_hitl_store.get_interrupt = AsyncMock(return_value=None)

        mock_handler = mock_handler_cls.return_value
        mock_handler.handle = AsyncMock()

        await router.route_message(text_message)

        # Handler was called with correct params
        mock_handler.handle.assert_called_once()
        call_kwargs = mock_handler.handle.call_args[1]
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["user_language"] == "en"
        assert call_kwargs["user_timezone"] == "America/New_York"
        assert call_kwargs["conversation_id"] == "conv-123"
        assert call_kwargs["pending_hitl"] is None

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Unbound message")
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_SERVICE)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_inactive_user_sends_unbound(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_service_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Inactive user with valid binding → unbound message."""
        mock_db_ctx.return_value = _make_db_context()
        user_id = uuid4()
        binding = _make_binding(user_id=user_id)
        user = _make_user(user_id=user_id, is_active=False)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        mock_user_svc = mock_user_service_cls.return_value
        mock_user_svc.get_user_by_id = AsyncMock(return_value=user)

        await router.route_message(text_message)

        # Handler NOT called, unbound message sent
        mock_handler_cls.return_value.handle.assert_not_called()
        mock_sender.send_message.assert_called_once()

    @pytest.mark.asyncio
    @patch(_PATCH_HITL_STORE)
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value="conv-456")
    @patch(_PATCH_USER_SERVICE)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_pending_hitl_passed_to_handler(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_service_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        mock_hitl_store_cls: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Pending HITL data should be passed to the handler."""
        mock_db_ctx.return_value = _make_db_context()
        user_id = uuid4()
        binding = _make_binding(user_id=user_id)
        user = _make_user(user_id=user_id)

        pending_data = {
            "schema_version": 1,
            "interrupt_ts": "2026-03-03T00:00:00",
            "interrupt_data": {"action_requests": [], "original_run_id": "run_abc"},
        }

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        mock_user_svc = mock_user_service_cls.return_value
        mock_user_svc.get_user_by_id = AsyncMock(return_value=user)

        mock_hitl_store = mock_hitl_store_cls.return_value
        mock_hitl_store.get_interrupt = AsyncMock(return_value=pending_data)

        mock_handler = mock_handler_cls.return_value
        mock_handler.handle = AsyncMock()

        await router.route_message(text_message)

        call_kwargs = mock_handler.handle.call_args[1]
        assert call_kwargs["pending_hitl"] == pending_data
        assert call_kwargs["conversation_id"] == "conv-456"
