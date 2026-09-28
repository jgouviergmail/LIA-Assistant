"""Tests for ChannelMessageRouter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import CHANNEL_RATE_WINDOW_SECONDS
from src.core.i18n import resolve_language
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.message_router import ChannelMessageRouter
from src.domains.channels.models import ChannelType
from src.infrastructure.locks.redis_claim import RELEASE_SCRIPT

# Patch targets — source modules (lazy imports inside functions)
_PATCH_DB_CTX = "src.infrastructure.database.session.get_db_context"
_PATCH_REPO = "src.domains.channels.repository.UserChannelBindingRepository"
# get_rate_limiter is an async factory: @patch swaps it for an AsyncMock, so
# `await get_rate_limiter()` yields mock.return_value (the limiter mock).
_PATCH_RATE_LIMITER = "src.infrastructure.rate_limiting.redis_limiter.get_rate_limiter"
_PATCH_USER_REPO = "src.domains.users.repository.UserRepository"
_PATCH_CONV_CACHE = "src.infrastructure.cache.conversation_cache.get_conversation_id_cached"
_PATCH_INBOUND_HANDLER = "src.domains.channels.inbound_handler.InboundMessageHandler"
_PATCH_HITL_STORE = "src.domains.agents.utils.hitl_store.HITLStore"
# The cache client the store reads through: the store is faked, so is it.
_PATCH_REDIS_CACHE = "src.infrastructure.cache.redis.get_redis_cache"
_PATCH_BOT_MESSAGE = "src.infrastructure.channels.telegram.formatter.get_bot_message"

#: The person's language — not the instance default, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)


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


def _make_user(user_id=None, is_active=True, language=_PERSON, timezone="Europe/Paris"):
    """A real ``User`` row — the shape the reader returns, never a mock.

    A mock's attributes are all truthy: it hid that the profile DTO the
    reader used to return carried neither ``journals_enabled`` nor
    ``psyche_enabled``, so every Telegram turn ran with both off.
    """
    from src.domains.users.models import User

    return User(
        id=user_id or uuid4(),
        email="person@example.com",
        full_name="Person",
        is_active=is_active,
        language=language,
        timezone=timezone,
        memory_enabled=True,
        journals_enabled=True,
        psyche_enabled=True,
    )


def _make_db_context(mock_db=None):
    """Create a mock async context manager for get_db_context()."""
    if mock_db is None:
        mock_db = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# =============================================================================
# A failed lookup
# =============================================================================


class TestLookupFailure:
    """A failed binding or person lookup is answered, never swallowed."""

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_failed_person_read_sends_the_error_message(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_db_ctx.return_value = _make_db_context()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=_make_binding())
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            side_effect=RuntimeError("database unavailable")
        )

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()
        assert mock_sender.send_message.call_args[0][1].text == "Error message"
        mock_bot_msg.assert_called_once_with("error")

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_failed_binding_read_sends_the_error_message(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_db_ctx.return_value = _make_db_context()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(
            side_effect=RuntimeError("database unavailable")
        )

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()
        mock_bot_msg.assert_called_once_with("error")


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
    @patch(_PATCH_BOT_MESSAGE, return_value="Channel disabled message")
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_switched_off_binding_is_told_so_in_the_person_s_language(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_handler_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The person switched the channel off: never the link hint, which cannot
        help (the binding exists), and never the declared language."""
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding(is_active=False)
        reads: list[bool] = []

        async def _read_binding(channel_type, channel_user_id, *, include_inactive=False):
            reads.append(include_inactive)
            return binding if include_inactive else None

        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(side_effect=_read_binding)
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=_make_user(user_id=binding.user_id)
        )

        with patch(_PATCH_RATE_LIMITER) as mock_limiter_cls:
            mock_limiter_cls.return_value.acquire = AsyncMock(return_value=True)
            await router.route_message(text_message)

        assert reads == [True]
        mock_handler_cls.return_value.handle.assert_not_called()
        mock_sender.send_message.assert_called_once()
        mock_bot_msg.assert_called_once_with("channel_disabled", _PERSON)

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Unbound message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_binding_whose_account_row_is_gone_reads_as_unbound(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_db_ctx.return_value = _make_db_context()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=_make_binding())
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()
        mock_bot_msg.assert_called_once_with("unbound")


# =============================================================================
# Rate limiting
# =============================================================================


class TestRateLimiting:
    """Tests for rate limiting."""

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Busy message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_rate_limited_sends_busy_message(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Rate limited user receives 'busy' message, in their language (ADR-323)."""
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=_make_user(user_id=binding.user_id, language=_PERSON)
        )

        # Rate limit exceeded
        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=False)

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()
        sent_msg = mock_sender.send_message.call_args[0][1]
        assert sent_msg.text == "Busy message"
        mock_bot_msg.assert_called_once_with("busy", _PERSON)


# =============================================================================
# Per-user lock
# =============================================================================


class TestUserLock:
    """Tests for per-user Redis lock."""

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Busy message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_lock_not_acquired_sends_busy(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """If lock is already held, send 'busy' message, in the person's language."""
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding()
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=_make_user(user_id=binding.user_id, language=_PERSON)
        )

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)

        # Lock NOT acquired (another message being processed)
        mock_redis.set = AsyncMock(return_value=False)

        await router.route_message(text_message)

        mock_sender.send_message.assert_called_once()
        mock_bot_msg.assert_called_once_with("busy", _PERSON)

    @pytest.mark.asyncio
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_lock_released_after_success(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
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

        mock_user_repo = mock_user_repo_cls.return_value
        mock_user_repo.get_by_id = AsyncMock(return_value=user)

        mock_handler_cls.return_value.handle = AsyncMock()

        await router.route_message(text_message)

        # The lock is released by its owner token, never deleted blindly.
        mock_redis.delete.assert_not_called()
        taken = mock_redis.set.call_args
        released = mock_redis.eval.call_args.args
        assert released[0] == RELEASE_SCRIPT
        assert released[2] == taken.args[0]
        assert "channel_msg_lock:" in released[2]
        assert released[3] == taken.args[1]  # the same owner token
        assert taken.kwargs == {"ex": settings.channel_message_lock_ttl_seconds, "nx": True}

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_lock_released_after_handler_error(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
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

        mock_user_repo = mock_user_repo_cls.return_value
        mock_user_repo.get_by_id = AsyncMock(return_value=user)

        mock_handler_cls.return_value.handle = AsyncMock(side_effect=RuntimeError("Pipeline crash"))

        # Should NOT raise — error is caught and error message is sent
        await router.route_message(text_message)

        # Lock still released despite error
        mock_redis.delete.assert_not_called()
        assert mock_redis.eval.call_args.args[0] == RELEASE_SCRIPT
        # Error message sent to user
        assert mock_sender.send_message.call_count >= 1


# =============================================================================
# Successful dispatch
# =============================================================================


class TestSuccessfulDispatch:
    """Tests for successful message dispatching."""

    @pytest.mark.asyncio
    @patch(_PATCH_REDIS_CACHE, new=AsyncMock(return_value=MagicMock()))
    @patch(_PATCH_HITL_STORE)
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value="conv-123")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_dispatches_to_inbound_handler(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        mock_hitl_store_cls: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Happy path: message dispatched to InboundMessageHandler.handle(), in the
        person's language — declared for the turn, then restored (ADR-323)."""
        mock_db_ctx.return_value = _make_db_context()
        user_id = uuid4()
        binding = _make_binding(user_id=user_id)
        person = next(code for code in ("en", "es") if code != settings.default_language)
        user = _make_user(user_id=user_id, language=person, timezone="America/New_York")

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        mock_user_repo = mock_user_repo_cls.return_value
        mock_user_repo.get_by_id = AsyncMock(return_value=user)

        mock_hitl_store = mock_hitl_store_cls.return_value
        mock_hitl_store.get_pending = AsyncMock(return_value=None)

        heard: list[str] = []
        mock_handler = mock_handler_cls.return_value
        mock_handler.handle = AsyncMock(side_effect=lambda **_: heard.append(resolve_language()))

        await router.route_message(text_message)

        # Handler was called with correct params
        mock_handler.handle.assert_called_once()
        call_kwargs = mock_handler.handle.call_args[1]
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["user_language"] == person
        assert heard == [person]
        assert resolve_language() == settings.default_language
        assert call_kwargs["user_timezone"] == "America/New_York"
        assert call_kwargs["conversation_id"] == "conv-123"
        assert call_kwargs["pending_hitl"] is None
        # The account's own long-term-state choices reach the turn (the profile
        # DTO the reader used to return carried neither flag: both read False).
        assert call_kwargs["user_journals_enabled"] is True
        assert call_kwargs["user_psyche_enabled"] is True
        assert call_kwargs["user_memory_enabled"] is True

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Account inactive message")
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_deactivated_account_is_told_so_in_its_language(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """A deactivated account is told so, in its own language — never the link hint.

        The fake reads the way the real repository does: a deactivated account
        is found only when the caller asks for it (``include_inactive``).
        """
        mock_db_ctx.return_value = _make_db_context()
        user_id = uuid4()
        binding = _make_binding(user_id=user_id)
        user = _make_user(user_id=user_id, is_active=False, language=_PERSON)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        async def _read(read_id, include_inactive=False):
            return user if include_inactive else None

        mock_user_repo = mock_user_repo_cls.return_value
        mock_user_repo.get_by_id = AsyncMock(side_effect=_read)

        await router.route_message(text_message)

        mock_handler_cls.return_value.handle.assert_not_called()
        mock_sender.send_message.assert_called_once()
        mock_bot_msg.assert_called_once_with("account_inactive", _PERSON)

    @pytest.mark.asyncio
    @patch(_PATCH_REDIS_CACHE, new=AsyncMock(return_value=MagicMock()))
    @patch(_PATCH_HITL_STORE)
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value="conv-456")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_pending_hitl_passed_to_handler(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
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

        # As HITLStore.get_pending returns it: flattened, the run it was asked on.
        pending_data = {
            "action_requests": [{"type": "plan_approval"}],
            "run_id": "run_abc",
            "interrupt_ts": "2026-03-03T00:00:00+00:00",
        }

        mock_repo = mock_repo_cls.return_value
        mock_repo.get_by_channel_id = AsyncMock(return_value=binding)

        mock_limiter = mock_limiter_cls.return_value
        mock_limiter.acquire = AsyncMock(return_value=True)
        mock_redis.set = AsyncMock(return_value=True)

        mock_user_repo = mock_user_repo_cls.return_value
        mock_user_repo.get_by_id = AsyncMock(return_value=user)

        mock_hitl_store = mock_hitl_store_cls.return_value
        mock_hitl_store.get_pending = AsyncMock(return_value=pending_data)

        mock_handler = mock_handler_cls.return_value
        mock_handler.handle = AsyncMock()

        await router.route_message(text_message)

        call_kwargs = mock_handler.handle.call_args[1]
        assert call_kwargs["pending_hitl"] == pending_data
        assert call_kwargs["conversation_id"] == "conv-456"


# =============================================================================
# The claim's failure paths, and the counters every refusal moves
# =============================================================================


def _rejected(reason: str) -> float:
    from src.infrastructure.observability.metrics_channels import (
        channel_messages_rejected_total,
    )

    return channel_messages_rejected_total.labels(
        channel_type="telegram", reason=reason
    )._value.get()


def _wired(
    mock_db_ctx: MagicMock,
    mock_repo_cls: MagicMock,
    mock_limiter_cls: MagicMock,
    mock_user_repo_cls: MagicMock,
) -> None:
    mock_db_ctx.return_value = _make_db_context()
    binding = _make_binding()
    mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=binding)
    mock_user_repo_cls.return_value.get_by_id = AsyncMock(
        return_value=_make_user(user_id=binding.user_id, language=_PERSON)
    )
    mock_limiter_cls.return_value.acquire = AsyncMock(return_value=True)


class TestThePendingQuestionIsReadWhereTheEngineSavedIt:
    @pytest.mark.asyncio
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_typed_answer_resumes_the_question_the_engine_saved(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_handler_cls: MagicMock,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Read from the session database the doors claim turns on, the
        question saved in the cache database was never there: a typed answer
        ran under a fresh run and left the question behind (review 12). Two
        keyspaces of one in-memory server (``tests/helpers/redis_databases``)."""
        from src.core.constants import REDIS_CACHE_DB, REDIS_SESSION_DB
        from src.domains.agents.utils.hitl_store import HITLStore
        from tests.helpers.redis_databases import RedisServer

        server = RedisServer()
        engine_cache, door_session = server.client(REDIS_CACHE_DB), server.client(REDIS_SESSION_DB)
        conversation_id = str(uuid4())
        await HITLStore(redis_client=engine_cache, ttl_seconds=60).save_interrupt(
            conversation_id, {"action_requests": [], "run_id": "run-1"}
        )
        _wired(mock_db_ctx, mock_repo_cls, mock_limiter_cls, mock_user_repo_cls)
        mock_handler_cls.return_value.handle = AsyncMock()
        router = ChannelMessageRouter(redis=door_session, sender=mock_sender)

        with (
            patch(_PATCH_CONV_CACHE, new=AsyncMock(return_value=conversation_id)),
            patch(_PATCH_REDIS_CACHE, new=AsyncMock(return_value=engine_cache)),
        ):
            await router.route_message(text_message)

        pending = mock_handler_cls.return_value.handle.await_args.kwargs["pending_hitl"]
        assert pending is not None
        assert pending["run_id"] == "run-1"


class TestTheClaimFailsLoudly:
    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_an_unreachable_cache_is_answered_and_counted(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """``try_claim`` propagates a cache failure: the router answers the person."""
        from structlog.testing import capture_logs

        _wired(mock_db_ctx, mock_repo_cls, mock_limiter_cls, mock_user_repo_cls)
        mock_redis.set = AsyncMock(side_effect=ConnectionError("cache down"))
        before = _rejected("lock_failed")

        with capture_logs() as logs:
            await router.route_message(text_message)

        mock_bot_msg.assert_called_once_with("error", _PERSON)
        mock_sender.send_message.assert_called_once()
        assert _rejected("lock_failed") == before + 1
        assert [
            (entry["log_level"], entry.get("exc_info"))
            for entry in logs
            if entry["event"] == "channel_message_lock_failed"
        ] == [("error", True)]

    @pytest.mark.asyncio
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_claim_a_successor_holds_is_left_alone_and_logged(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The release script answered 0: the key held another token (or was gone)."""
        from structlog.testing import capture_logs

        _wired(mock_db_ctx, mock_repo_cls, mock_limiter_cls, mock_user_repo_cls)
        mock_handler_cls.return_value.handle = AsyncMock()
        mock_redis.eval = AsyncMock(return_value=0)

        with capture_logs() as logs:
            await router.route_message(text_message)

        mock_redis.delete.assert_not_called()
        assert any(entry["event"] == "redis_claim_not_released" for entry in logs)

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_INBOUND_HANDLER)
    @patch(_PATCH_CONV_CACHE, new_callable=AsyncMock, return_value=None)
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_turn_whose_claim_another_took_is_told_and_logged(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_conv_cache: AsyncMock,
        mock_handler_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_sender: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The claim's keeper stopped the turn: the person is told, and the
        log names the takeover rather than a routing error."""
        from structlog.testing import capture_logs

        from src.infrastructure.locks.redis_claim import ClaimLost

        _wired(mock_db_ctx, mock_repo_cls, mock_limiter_cls, mock_user_repo_cls)
        mock_handler_cls.return_value.handle = AsyncMock(side_effect=ClaimLost("k", "taken_over"))
        before = _rejected("claim_lost")

        with capture_logs() as logs:
            await router.route_message(text_message)

        mock_bot_msg.assert_called_once_with("error", _PERSON)
        mock_sender.send_message.assert_called_once()
        events = {entry["event"]: entry for entry in logs}
        assert events["channel_message_claim_lost"]["claim_loss"] == "taken_over"
        assert events["channel_message_claim_lost"]["log_level"] == "warning"
        assert "channel_message_routing_error" not in events
        assert _rejected("claim_lost") == before + 1

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Busy message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_RATE_LIMITER)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_held_claim_is_counted(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_limiter_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        from structlog.testing import capture_logs

        _wired(mock_db_ctx, mock_repo_cls, mock_limiter_cls, mock_user_repo_cls)
        mock_redis.set = AsyncMock(return_value=False)
        before = _rejected("locked")

        with capture_logs() as logs:
            await router.route_message(text_message)

        assert _rejected("locked") == before + 1
        assert [
            entry["log_level"] for entry in logs if entry["event"] == "channel_message_locked"
        ] == ["info"]


class TestEveryRefusalIsCounted:
    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Unbound message")
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_an_unknown_chat_is_counted_unbound(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_db_ctx.return_value = _make_db_context()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=None)
        before = _rejected("unbound")

        await router.route_message(text_message)

        assert _rejected("unbound") == before + 1

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Error message")
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_failed_lookup_is_counted(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_db_ctx.return_value = _make_db_context()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(side_effect=RuntimeError("db"))
        before = _rejected("lookup_failed")

        await router.route_message(text_message)

        assert _rejected("lookup_failed") == before + 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("account_active", "binding_active", "reason"),
        [(False, True, "account_inactive"), (True, False, "channel_disabled")],
    )
    @patch(_PATCH_BOT_MESSAGE, return_value="Refusal")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_refusal_is_counted_by_its_reason(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        account_active: bool,
        binding_active: bool,
        reason: str,
        router: ChannelMessageRouter,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding(is_active=binding_active)
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=binding)
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=_make_user(user_id=binding.user_id, is_active=account_active)
        )
        before = _rejected(reason)

        with patch(_PATCH_RATE_LIMITER) as mock_limiter_cls:
            mock_limiter_cls.return_value.acquire = AsyncMock(return_value=True)
            await router.route_message(text_message)

        mock_bot_msg.assert_called_once_with(reason, _PERSON)
        assert _rejected(reason) == before + 1

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Refused message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_refused_account_is_told_once_per_window(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """Answered message by message, an account that kept writing drew as many
        replies as it sent. Every message is counted; one is answered, with the
        account's state — never « busy », which would say a turn is running."""
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=binding)
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=_make_user(user_id=binding.user_id, is_active=False)
        )
        refused_before = _rejected("account_inactive")
        # The notice is taken by the first message, and is held for the second.
        mock_redis.set = AsyncMock(side_effect=[True, None])

        with patch(_PATCH_RATE_LIMITER) as mock_limiter_cls:
            mock_limiter_cls.return_value.acquire = AsyncMock(return_value=False)
            await router.route_message(text_message)
            await router.route_message(text_message)

        mock_bot_msg.assert_called_once_with("account_inactive", _PERSON)
        assert router.sender.send_message.await_count == 1
        assert _rejected("account_inactive") == refused_before + 2
        key, value = mock_redis.set.call_args.args
        assert key == f"channel_rate:notice:telegram:{binding.user_id}"
        assert mock_redis.set.call_args.kwargs == {"nx": True, "ex": CHANNEL_RATE_WINDOW_SECONDS}

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Busy message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_person_over_the_rate_is_told_once_per_window(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=binding)
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=_make_user(user_id=binding.user_id)
        )
        from structlog.testing import capture_logs

        limited_before = _rejected("rate_limited")
        mock_redis.set = AsyncMock(side_effect=[True, None])

        with patch(_PATCH_RATE_LIMITER) as mock_limiter_cls, capture_logs() as logs:
            mock_limiter_cls.return_value.acquire = AsyncMock(return_value=False)
            await router.route_message(text_message)
            await router.route_message(text_message)

        mock_bot_msg.assert_called_once_with("busy", _PERSON)
        assert router.sender.send_message.await_count == 1
        assert _rejected("rate_limited") == limited_before + 2
        # Its own event, logged for every message, answered or not.
        limited = [e for e in logs if e.get("reason") == "rate_limited"]
        assert [(e["event"], e["log_level"]) for e in limited] == [
            ("channel_message_rate_limited", "warning")
        ] * 2

    @pytest.mark.asyncio
    @patch(_PATCH_BOT_MESSAGE, return_value="Refused message")
    @patch(_PATCH_USER_REPO)
    @patch(_PATCH_REPO)
    @patch(_PATCH_DB_CTX)
    async def test_a_refusal_the_notice_cannot_record_is_still_answered(
        self,
        mock_db_ctx: MagicMock,
        mock_repo_cls: MagicMock,
        mock_user_repo_cls: MagicMock,
        mock_bot_msg: MagicMock,
        router: ChannelMessageRouter,
        mock_redis: AsyncMock,
        text_message: ChannelInboundMessage,
    ) -> None:
        """The notice bounds the replies; an unreachable cache must not turn it
        into silence — its failure used to leave ``route_message`` unanswered."""
        from structlog.testing import capture_logs

        mock_db_ctx.return_value = _make_db_context()
        binding = _make_binding()
        mock_repo_cls.return_value.get_by_channel_id = AsyncMock(return_value=binding)
        mock_user_repo_cls.return_value.get_by_id = AsyncMock(
            return_value=_make_user(user_id=binding.user_id, is_active=False)
        )
        mock_redis.set = AsyncMock(side_effect=ConnectionError("cache down"))
        before = _rejected("account_inactive")

        with capture_logs() as logs:
            await router.route_message(text_message)

        mock_bot_msg.assert_called_once_with("account_inactive", _PERSON)
        assert router.sender.send_message.await_count == 1
        assert _rejected("account_inactive") == before + 1
        refused = [e for e in logs if e["event"] == "channel_message_refused"]
        assert [(e["reason"], e["log_level"]) for e in refused] == [("account_inactive", "warning")]
        unavailable = [e for e in logs if e["event"] == "channel_refusal_notice_unavailable"]
        assert [(e["error_type"], e["log_level"]) for e in unavailable] == [
            ("ConnectionError", "warning")
        ]


class TestTheTurnHasAnEnd:
    @pytest.mark.asyncio
    async def test_a_turn_past_the_longest_plausible_run_is_stopped(self) -> None:
        """A wedged turn frees the person rather than answering « busy » until
        the worker restarts: the hold is bounded by the platform's longest run."""
        from src.domains.channels.message_router import hold_turn_claim
        from src.infrastructure.locks.redis_claim import ClaimLost

        redis = AsyncMock()
        redis.eval = AsyncMock(return_value=1)  # every refresh succeeds
        with (
            patch.object(settings, "channel_message_lock_ttl_seconds", 1),
            patch.object(settings, "background_runs_stream_safety_ttl_seconds", 0),
            pytest.raises(ClaimLost) as lost,
        ):
            async with hold_turn_claim(redis, uuid4(), "token"):
                await asyncio.sleep(settings.channel_message_lock_ttl_seconds * 3)

        assert lost.value.reason == "hold_exhausted"
