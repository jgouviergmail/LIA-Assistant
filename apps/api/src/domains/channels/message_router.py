"""
Channel message router — dispatches inbound messages to handlers.

Routes inbound channel messages through: binding lookup, rate limiting,
per-user Redis lock, and dispatch to InboundMessageHandler. Sends
appropriate error messages (unbound, busy, rate limited) via the
channel sender.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from src.core.constants import (
    CHANNEL_MESSAGE_LOCK_PREFIX,
    CHANNEL_RATE_LIMIT_PER_USER_PER_MINUTE_DEFAULT,
    CHANNEL_RATE_LIMIT_REDIS_PREFIX,
)
from src.domains.channels.abstractions import (
    ChannelInboundMessage,
    ChannelOutboundMessage,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_message_processing_duration_seconds,
    channel_messages_received_total,
    channel_messages_rejected_total,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from src.domains.channels.abstractions import BaseChannelSender

logger = get_logger(__name__)


class ChannelMessageRouter:
    """
    Routes inbound channel messages through security checks and dispatching.

    Flow:
    1. Lookup UserChannelBinding by (channel_type, channel_user_id)
    2. If no active binding → send "unbound" message, return
    3. Rate limit check (per-user, per-minute via RedisRateLimiter)
    4. Acquire per-user Redis lock (non-blocking: if held → send "busy")
    5. Load User object (timezone, language, memory_enabled)
    6. Dispatch to InboundMessageHandler
    7. Release lock (finally block)

    Args:
        redis: Async Redis client for locks and rate limiting.
        sender: Channel-specific sender for error/status messages.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        sender: BaseChannelSender,
    ) -> None:
        self.redis = redis
        self.sender = sender

    async def route_message(self, message: ChannelInboundMessage) -> None:
        """
        Route an inbound channel message through the full pipeline.

        Args:
            message: Parsed inbound message from the webhook handler.
        """
        from src.core.config import settings
        from src.domains.channels.inbound_handler import InboundMessageHandler
        from src.domains.channels.repository import UserChannelBindingRepository
        from src.domains.users.service import UserService
        from src.infrastructure.cache.conversation_cache import get_conversation_id_cached
        from src.infrastructure.database.session import get_db_context
        from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

        channel_user_id = message.channel_user_id
        channel_type = message.channel_type.value
        message_type = "voice" if message.voice_file_id else "text"

        # Track inbound message
        channel_messages_received_total.labels(
            channel_type=channel_type,
            message_type=message_type,
        ).inc()
        start_time = time.monotonic()

        # === 1. Lookup binding ===
        async with get_db_context() as db:
            repo = UserChannelBindingRepository(db)
            binding = await repo.get_by_channel_id(channel_type, channel_user_id)

        if binding is None or not binding.is_active:
            from src.infrastructure.channels.telegram.formatter import get_bot_message

            logger.info(
                "channel_message_no_binding",
                channel_type=channel_type,
                channel_user_id=channel_user_id,
            )
            channel_messages_rejected_total.labels(
                channel_type=channel_type,
                reason="unbound",
            ).inc()
            await self.sender.send_message(
                channel_user_id,
                ChannelOutboundMessage(text=get_bot_message("unbound")),
            )
            return

        user_id = binding.user_id

        # === 2. Rate limit check ===
        rate_limit_key = f"{CHANNEL_RATE_LIMIT_REDIS_PREFIX}{channel_type}:{user_id}"
        rate_limit = getattr(
            settings,
            "channel_rate_limit_per_user_per_minute",
            CHANNEL_RATE_LIMIT_PER_USER_PER_MINUTE_DEFAULT,
        )

        limiter = RedisRateLimiter(self.redis)
        allowed = await limiter.acquire(
            key=rate_limit_key,
            max_calls=rate_limit,
            window_seconds=60,
        )

        if not allowed:
            from src.infrastructure.channels.telegram.formatter import get_bot_message

            logger.warning(
                "channel_message_rate_limited",
                channel_type=channel_type,
                user_id=str(user_id),
            )
            channel_messages_rejected_total.labels(
                channel_type=channel_type,
                reason="rate_limited",
            ).inc()
            await self.sender.send_message(
                channel_user_id,
                ChannelOutboundMessage(text=get_bot_message("busy")),
            )
            return

        # === 3. Per-user lock (non-blocking) ===
        lock_ttl = getattr(
            settings,
            "channel_message_lock_ttl_seconds",
            120,
        )
        lock_key = f"{CHANNEL_MESSAGE_LOCK_PREFIX}{user_id}"

        lock_acquired = await self.redis.set(
            lock_key,
            "locked",
            nx=True,
            ex=lock_ttl,
        )

        if not lock_acquired:
            from src.infrastructure.channels.telegram.formatter import get_bot_message

            logger.info(
                "channel_message_locked",
                channel_type=channel_type,
                user_id=str(user_id),
            )
            channel_messages_rejected_total.labels(
                channel_type=channel_type,
                reason="locked",
            ).inc()
            await self.sender.send_message(
                channel_user_id,
                ChannelOutboundMessage(text=get_bot_message("busy")),
            )
            return

        try:
            # === 4. Load user ===
            async with get_db_context() as db:
                user_service = UserService(db)
                user = await user_service.get_user_by_id(user_id)

            if not user or not user.is_active:
                from src.infrastructure.channels.telegram.formatter import get_bot_message

                logger.warning(
                    "channel_message_user_inactive",
                    channel_type=channel_type,
                    user_id=str(user_id),
                )
                await self.sender.send_message(
                    channel_user_id,
                    ChannelOutboundMessage(text=get_bot_message("unbound")),
                )
                return

            user_language = getattr(user, "language", None) or "fr"
            user_timezone = getattr(user, "timezone", None) or "Europe/Paris"
            user_memory_enabled = getattr(user, "memory_enabled", True)

            # === 5. Check pending HITL ===
            conversation_id = await get_conversation_id_cached(user_id)
            pending_hitl = None

            if conversation_id:
                from src.domains.agents.utils.hitl_store import HITLStore

                hitl_store = HITLStore(self.redis, ttl_seconds=3600)
                pending_hitl = await hitl_store.get_interrupt(conversation_id)

            # === 6. Dispatch to handler ===
            inbound_handler = InboundMessageHandler(
                sender=self.sender,
            )

            await inbound_handler.handle(
                message=message,
                user_id=user_id,
                user_language=user_language,
                user_timezone=user_timezone,
                user_memory_enabled=user_memory_enabled,
                conversation_id=conversation_id,
                pending_hitl=pending_hitl,
            )

            # Track successful processing duration
            channel_message_processing_duration_seconds.labels(
                channel_type=channel_type,
            ).observe(time.monotonic() - start_time)

        except asyncio.CancelledError:
            logger.warning(
                "channel_message_cancelled",
                channel_type=channel_type,
                user_id=str(user_id),
            )
            raise
        except Exception:
            from src.infrastructure.channels.telegram.formatter import get_bot_message

            logger.error(
                "channel_message_routing_error",
                channel_type=channel_type,
                user_id=str(user_id),
                exc_info=True,
            )
            try:
                # user_language may not be defined if the error occurred
                # before the user object was loaded (step 4).
                lang = user_language if "user_language" in locals() else "fr"
                await self.sender.send_message(
                    channel_user_id,
                    ChannelOutboundMessage(
                        text=get_bot_message("error", lang),
                    ),
                )
            except Exception:
                logger.error("channel_error_message_send_failed", exc_info=True)
        finally:
            # Always release lock
            try:
                await self.redis.delete(lock_key)
            except Exception:
                logger.error(
                    "channel_message_lock_release_failed",
                    lock_key=lock_key,
                    exc_info=True,
                )
