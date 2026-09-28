"""
Channel message router — dispatches inbound messages to handlers.

Routes inbound channel messages through: binding lookup, rate limiting,
the person's turn claim, and dispatch to InboundMessageHandler. Sends
appropriate refusals (unbound, account inactive, channel disabled, busy,
error) via the channel sender.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.core.constants import (
    CHANNEL_MESSAGE_LOCK_PREFIX,
    CHANNEL_RATE_LIMIT_REDIS_PREFIX,
    CHANNEL_RATE_WINDOW_SECONDS,
    CHANNEL_REFUSAL_NOTICE_REDIS_PREFIX,
)
from src.core.i18n import language_scope
from src.domains.channels.abstractions import (
    ChannelInboundMessage,
    ChannelOutboundMessage,
)
from src.domains.channels.preferences import resolve_channel_preferences
from src.infrastructure.locks.redis_claim import ClaimLost, held_claim, try_claim
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_message_processing_duration_seconds,
    channel_messages_received_total,
    channel_messages_rejected_total,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from src.domains.channels.abstractions import BaseChannelSender
    from src.domains.channels.models import UserChannelBinding
    from src.domains.users.models import User

logger = get_logger(__name__)


async def read_pending_question(conversation_id: str) -> dict[str, Any] | None:
    """The question the conversation's graph waits on, read where the ENGINE keeps it.

    The engine saves a pending HITL interrupt through the CACHE client
    (``get_redis_cache``, ``agents/api/service.py``); both channel doors read it
    here. They used to read it through the SESSION client they claim turns on —
    another Redis database, so every button press was told its question had
    expired, and a typed answer, which the checkpoint still resumed, ran under a
    fresh run and left the question's record behind until its TTL (review 12;
    the test conftest forces both databases to one index, which hid it).

    Args:
        conversation_id: The conversation whose question is read.

    Returns:
        The question as every door that resumes one reads it
        (``HITLStore.get_pending``: flattened, ``run_id`` the run it was
        asked on), or None when nothing waits.
    """
    from src.core.config import settings
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.infrastructure.cache.redis import get_redis_cache

    store = HITLStore(await get_redis_cache(), ttl_seconds=settings.hitl_pending_data_ttl_seconds)
    return await store.get_pending(conversation_id)


async def take_turn_claim(redis: aioredis.Redis, user_id: UUID) -> str | None:
    """Claim the person's turn: the owner token when taken, None when held.

    One claim per person for every door that runs a turn — a message and a HITL
    button alike — so a double tap never resumes the graph twice. The claim
    lives ``CHANNEL_MESSAGE_LOCK_TTL_SECONDS`` — a crash bound, shorter than a
    turn may run — so the turn runs under :func:`hold_turn_claim`, which
    re-arms it and releases it.

    Args:
        redis: The session client (the turn claim lives in the session DB).
        user_id: The person whose turn it is.

    Returns:
        The owner token to hold the claim with, or None when another turn
        holds it.

    Raises:
        Exception: Whatever the cache raised — the caller answers the person.
    """
    from src.core.config import settings

    token = uuid.uuid4().hex
    taken = await try_claim(
        redis,
        f"{CHANNEL_MESSAGE_LOCK_PREFIX}{user_id}",
        token,
        ttl_seconds=settings.channel_message_lock_ttl_seconds,
    )
    return token if taken else None


def hold_turn_claim(
    redis: aioredis.Redis, user_id: UUID, token: str
) -> AbstractAsyncContextManager[None]:
    """Hold the person's turn claim while their turn runs.

    Re-armed while the turn runs, the turn stopped at the next refresh once
    another turn holds it or once it outlives the longest hold
    (``ClaimLost``), released by its token on every exit that still owns it —
    a successor's claim is left alone.

    Args:
        redis: The session client (the turn claim lives in the session DB).
        user_id: The person whose turn it is.
        token: The owner token :func:`take_turn_claim` returned.

    Returns:
        The context manager holding the claim.
    """
    from src.core.config import settings

    # A hold has an end: a turn running longer than the platform's longest
    # plausible run is wedged, and stopping it frees the person rather than
    # answering « busy » until the worker restarts.
    return held_claim(
        redis,
        f"{CHANNEL_MESSAGE_LOCK_PREFIX}{user_id}",
        token,
        ttl_seconds=settings.channel_message_lock_ttl_seconds,
        max_hold_seconds=settings.background_runs_stream_safety_ttl_seconds,
    )


async def read_binding_and_person(
    channel_type: str, channel_user_id: str
) -> tuple[UserChannelBinding, User] | None:
    """A channel user's binding and the person it names, in one short session.

    Both are read whatever their state: every refusal to someone the bot knows
    speaks their language, and a deactivated account or a switched-off binding
    is TOLD so (ADR-323) — :func:`refusal_for` decides which. Shared by the
    inbound route and the HITL button callback.

    The person is the ``User`` ROW, never the profile DTO: the channel
    preferences read ``journals_enabled`` and ``psyche_enabled``, which the DTO
    does not carry, so every Telegram turn ran with both off; and the DTO's
    strict language validator refused a stored code the instance no longer
    lists, which answered « error » to that person on every message.

    Args:
        channel_type: The channel (``telegram``).
        channel_user_id: The user's id on that channel.

    Returns:
        The binding and the person, or None when no binding exists (or its
        account row is gone).

    Raises:
        Exception: Whatever the database read raises — both callers answer it
            as a failed lookup.
    """
    from src.domains.channels.repository import UserChannelBindingRepository
    from src.domains.users.repository import UserRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        binding = await UserChannelBindingRepository(db).get_by_channel_id(
            channel_type, channel_user_id, include_inactive=True
        )
        if binding is None:
            return None
        person = await UserRepository(db).get_by_id(binding.user_id, include_inactive=True)
        if person is None:
            return None
        return binding, person


def refusal_for(binding: UserChannelBinding, person: User) -> str | None:
    """Why a known person's account refuses their message, or None.

    The value is both the bot message key and the rejection counter's reason. A
    deactivated account comes first: switching the channel back on would not
    help it. The rate limit is read after it (:func:`_over_rate_limit`).

    Args:
        binding: The person's binding on this channel.
        person: The account it names.

    Returns:
        ``account_inactive``, ``channel_disabled``, or None when the message may run.
    """
    if not person.is_active:
        return "account_inactive"
    if not binding.is_active:
        return "channel_disabled"
    return None


@dataclass(frozen=True, slots=True)
class Recipient:
    """Who a message came from, and where and in which language to answer."""

    channel_type: str
    channel_user_id: str
    user_id: UUID
    language: str


#: The log event of a refusal, when it is not ``channel_message_refused``.
_REFUSAL_EVENTS: dict[str, str] = {"rate_limited": "channel_message_rate_limited"}


async def answer_refusal(
    redis: aioredis.Redis, sender: BaseChannelSender, where: Recipient, reason: str
) -> None:
    """Count a known person's refusal, and answer it once per rate window.

    Both doors answer through here — a message and a HITL button — so an
    account that keeps writing or pressing, deactivated, switched off or over
    its rate, draws one reply per window rather than one per act — every act
    while the cache cannot say whether the window's reply went out. The
    answer names the account's state; over the rate it is ``busy``. Every
    refusal is counted, answered or not; each door logs its own event.

    Args:
        redis: The session cache, which holds the window's notice.
        sender: The channel's sender.
        where: The person and the conversation to answer in.
        reason: ``account_inactive``, ``channel_disabled`` or ``rate_limited``.
    """
    from src.infrastructure.channels.telegram.formatter import get_bot_message

    channel_messages_rejected_total.labels(channel_type=where.channel_type, reason=reason).inc()
    if not await _first_notice_in_window(redis, where):
        return
    text = get_bot_message("busy" if reason == "rate_limited" else reason, where.language)
    await sender.send_message(where.channel_user_id, ChannelOutboundMessage(text=text))


@dataclass(frozen=True, slots=True)
class ClaimEvents:
    """The log events a door names its turn claim's refusals with.

    Attributes:
        lock_failed: The cache could not be asked for the claim.
        locked: Another turn of the person's holds it.
        claim_lost: The claim stopped protecting the running turn.
    """

    lock_failed: str
    locked: str
    claim_lost: str


#: The message door's events.
MESSAGE_CLAIM_EVENTS = ClaimEvents(
    lock_failed="channel_message_lock_failed",
    locked="channel_message_locked",
    claim_lost="channel_message_claim_lost",
)


async def claim_turn_or_answer(
    redis: aioredis.Redis, sender: BaseChannelSender, where: Recipient, events: ClaimEvents
) -> str | None:
    """Take the person's turn claim, or answer why the turn will not run.

    Both doors claim through here — a message and a HITL button — so one
    person's turns never run side by side, whichever door they came through.
    An owner token, and a claim HELD for the whole turn: a turn outlives the
    claim's TTL, so it is re-armed while the turn runs (:func:`hold_turn_claim`).

    Args:
        redis: The session cache.
        sender: The channel's sender.
        where: The person and the conversation to answer in.
        events: The door's log events.

    Returns:
        The owner token, or None when the turn was answered instead —
        ``busy`` while another turn holds the claim, ``error`` when the cache
        could not be asked.
    """
    from src.infrastructure.channels.telegram.formatter import get_bot_message

    log_fields = {"channel_type": where.channel_type, "user_id": str(where.user_id)}
    try:
        token = await take_turn_claim(redis, where.user_id)
    except Exception:
        logger.error(events.lock_failed, exc_info=True, **log_fields)
        reason, answer = "lock_failed", "error"
    else:
        if token is not None:
            return token
        logger.info(events.locked, **log_fields)
        reason, answer = "locked", "busy"
    channel_messages_rejected_total.labels(channel_type=where.channel_type, reason=reason).inc()
    text = get_bot_message(answer, where.language)
    await sender.send_message(where.channel_user_id, ChannelOutboundMessage(text=text))
    return None


def note_claim_lost(where: Recipient, lost: ClaimLost, events: ClaimEvents) -> None:
    """Log and count a turn its claim stopped protecting; the door answers it.

    Another turn of the person's took the claim, or the turn outlived the
    longest hold: it was stopped rather than left to write beside the next one.

    Args:
        where: The person whose turn stopped.
        lost: Why the claim stopped protecting it.
        events: The door's log events.
    """
    logger.warning(
        events.claim_lost,
        channel_type=where.channel_type,
        user_id=str(where.user_id),
        claim_loss=lost.reason,
    )
    channel_messages_rejected_total.labels(
        channel_type=where.channel_type, reason="claim_lost"
    ).inc()


async def _first_notice_in_window(redis: aioredis.Redis, where: Recipient) -> bool:
    """Whether no refusal was answered to this person in the current window.

    A cache that cannot be asked answers True: the notice bounds the replies
    and is never a reason to leave a person unanswered — the rate limiter
    fails open for the same reason.

    Args:
        redis: The session cache.
        where: The person refused.

    Returns:
        True when this refusal is the window's first, or when nobody can tell.
    """
    notice = f"{CHANNEL_REFUSAL_NOTICE_REDIS_PREFIX}{where.channel_type}:{where.user_id}"
    try:
        return bool(await redis.set(notice, "1", nx=True, ex=CHANNEL_RATE_WINDOW_SECONDS))
    except Exception as exc:  # noqa: BLE001 — an unreachable cache answers, never silences
        logger.warning(
            "channel_refusal_notice_unavailable",
            channel_type=where.channel_type,
            user_id=str(where.user_id),
            error_type=type(exc).__name__,
        )
        return True


async def _over_rate_limit(channel_type: str, user_id: UUID) -> str | None:
    """``rate_limited`` when the person is over their per-minute rate, else None.

    The shared limiter (cache Redis): every rate limiter lives in the cache
    DB, and a per-instance one paid a SCRIPT LOAD per inbound message.

    Args:
        channel_type: The channel (``telegram``).
        user_id: The person writing.

    Returns:
        ``rate_limited``, or None when the message is within the rate.
    """
    from src.core.config import settings
    from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

    limiter = await get_rate_limiter()
    allowed = await limiter.acquire(
        key=f"{CHANNEL_RATE_LIMIT_REDIS_PREFIX}{channel_type}:{user_id}",
        max_calls=settings.channel_rate_limit_per_user_per_minute,
        window_seconds=CHANNEL_RATE_WINDOW_SECONDS,
    )
    return None if allowed else "rate_limited"


class ChannelMessageRouter:
    """
    Routes inbound channel messages through security checks and dispatching.

    Flow:
    1. Look up the UserChannelBinding and the person it names, in one short
       session — a failed read answers "error" in the declared language, no
       binding answers "unbound"
    2. Refuse a deactivated account or a switched-off binding, then a person
       over the per-user rate (shared RedisRateLimiter) — told in their own
       language, at most once per rate window (every refusal while the
       cache cannot say whether the window's answer went out)
    3. Claim the person's turn (non-blocking: held → "busy"; the cache
       unreachable → "error")
    4. Check a pending HITL interaction
    5. Dispatch to InboundMessageHandler, in the person's language
    6. Release the claim while it is still this turn's (``held_claim`` does,
       on every exit)

    Args:
        redis: Async Redis client (session DB) for the per-user claim and the
            refusal notice — the pending question lives in the cache DB, where
            the engine writes it (:func:`read_pending_question`).
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
        from src.domains.channels.inbound_handler import InboundMessageHandler
        from src.infrastructure.cache.conversation_cache import get_conversation_id_cached

        channel_user_id = message.channel_user_id
        channel_type = message.channel_type.value
        message_type = "voice" if message.voice_file_id else "text"

        # Track inbound message
        channel_messages_received_total.labels(
            channel_type=channel_type,
            message_type=message_type,
        ).inc()
        start_time = time.monotonic()

        # === 1. Lookup binding, and the person it names ===
        # One short session: from here the person is known, and every refusal
        # below speaks their language (ADR-323). A failed lookup is answered —
        # nobody is known yet, so in the declared language.
        try:
            found = await read_binding_and_person(channel_type, channel_user_id)
        except Exception:
            from src.infrastructure.channels.telegram.formatter import get_bot_message

            logger.error(
                "channel_message_lookup_failed",
                channel_type=channel_type,
                exc_info=True,
            )
            channel_messages_rejected_total.labels(
                channel_type=channel_type,
                reason="lookup_failed",
            ).inc()
            await self.sender.send_message(
                channel_user_id,
                ChannelOutboundMessage(text=get_bot_message("error")),
            )
            return

        if found is None:
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

        binding, user = found
        user_id = binding.user_id
        # One reading of the person's language for every sentence below.
        prefs = resolve_channel_preferences(user)
        where = Recipient(channel_type, channel_user_id, user_id, prefs.language)

        # === 2. Refusals: the account's state, then the rate limit ===
        refusal = refusal_for(binding, user) or await _over_rate_limit(channel_type, user_id)
        if refusal is not None:
            await self._refuse(where, refusal)
            return

        # === 3. Per-user claim (non-blocking), owned by this message ===
        lock_token = await claim_turn_or_answer(
            self.redis, self.sender, where, MESSAGE_CLAIM_EVENTS
        )
        if lock_token is None:
            return

        try:
            async with hold_turn_claim(self.redis, user_id, lock_token):
                # === 4. Check pending HITL ===
                conversation_id = await get_conversation_id_cached(user_id)
                pending_hitl = None

                if conversation_id:
                    pending_hitl = await read_pending_question(conversation_id)

                # === 5. Dispatch to handler ===
                inbound_handler = InboundMessageHandler(
                    sender=self.sender,
                )

                # A channel turn has no request of its own: whatever it writes
                # without an explicit language speaks the person's (ADR-323). A
                # scope, not a declaration — the polling bot runs every update in
                # ONE task.
                with language_scope(prefs.language):
                    await inbound_handler.handle(
                        message=message,
                        user_id=user_id,
                        user_language=prefs.language,
                        user_timezone=prefs.timezone,
                        user_memory_enabled=prefs.memory_enabled,
                        user_journals_enabled=prefs.journals_enabled,
                        user_psyche_enabled=prefs.psyche_enabled,
                        conversation_id=conversation_id,
                        pending_hitl=pending_hitl,
                        user_display_name=prefs.display_name,
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
        except Exception as exc:
            await self._answer_failure(where, exc)

    async def _refuse(self, where: Recipient, reason: str) -> None:
        """Log a known person's refusal, then count and answer it (:func:`answer_refusal`).

        Args:
            where: The person and the conversation to answer in.
            reason: ``account_inactive``, ``channel_disabled`` or ``rate_limited``.
        """
        logger.warning(
            _REFUSAL_EVENTS.get(reason, "channel_message_refused"),
            channel_type=where.channel_type,
            user_id=str(where.user_id),
            reason=reason,
        )
        await answer_refusal(self.redis, self.sender, where, reason)

    async def _answer_failure(self, where: Recipient, exc: Exception) -> None:
        """Answer a turn that failed, and say why it failed.

        Args:
            where: The person and the conversation to answer in.
            exc: What stopped the turn.
        """
        from src.infrastructure.channels.telegram.formatter import get_bot_message

        if isinstance(exc, ClaimLost):
            note_claim_lost(where, exc, MESSAGE_CLAIM_EVENTS)
        else:
            logger.error(
                "channel_message_routing_error",
                exc_info=True,
                channel_type=where.channel_type,
                user_id=str(where.user_id),
            )
        try:
            text = get_bot_message("error", where.language)
            await self.sender.send_message(where.channel_user_id, ChannelOutboundMessage(text=text))
        except Exception:
            logger.error("channel_error_message_send_failed", exc_info=True)
