"""Run one peer message with bounded ownership and no repeated model generation."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog

from src.core.config import settings
from src.core.constants import PEERS_DELIVERY_CANCELLATION_GRACE_ATTEMPTS
from src.core.i18n_proactive import ProactiveMessages
from src.core.security.utils import decrypt_data
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.peers.constants import PEER_CONNECTION_TASK_TYPE, PEER_MESSAGE_TASK_TYPE
from src.domains.peers.delivery_repository import (
    DeliveryClaim,
    DeliveryLeaseLost,
    PeerDeliveryRepository,
    claim_of,
)
from src.domains.peers.message_authority import lock_message_authority
from src.domains.peers.models import PeerMessage
from src.domains.peers.repository import PeersRepository
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User
from src.infrastructure.async_utils import write_through_cancellation
from src.infrastructure.database.session import get_db_context
from src.infrastructure.proactive.notification import NotificationDispatcher
from src.infrastructure.scheduler.peer_delivery_archive import (
    commit_delivery,
    peer_message_metadata,
)
from src.infrastructure.scheduler.peer_delivery_lease import delivery_lease
from src.infrastructure.utils.request_outcome import outcome_unknown

logger = structlog.get_logger(__name__)
Generate = Callable[[PeerMessage, User, User, int], Awaitable[str]]


async def _fail(claim: DeliveryClaim, code: str, *, retryable: bool) -> str:
    async with get_db_context() as db:
        outcome = await PeerDeliveryRepository(db).mark_message_failed(
            claim, code, max_attempts=settings.peers_delivery_max_attempts, retryable=retryable
        )
    return outcome or "lost"


async def _cancel(claim: DeliveryClaim, code: str) -> str:
    async with get_db_context() as db:
        won = await PeerDeliveryRepository(db).cancel_message(claim, code)
    return code if won else "lost"


async def _admit(message: PeerMessage, claim: DeliveryClaim) -> tuple[User, User, int] | str:
    if not await is_capability_enabled(PlatformCapability.PEERS):
        return await _cancel(claim, "cancelled_disabled")
    if not (message.content or "").strip() or (
        message.expires_at is not None and message.expires_at <= datetime.now(UTC)
    ):
        return await _cancel(claim, "cancelled_content_expired")
    if await UsageLimitService.is_user_blocked_for_llm(
        message.sender_id, layer="peer_message_delivery"
    ):
        return await _cancel(claim, "cancelled_sender_blocked")
    async with get_db_context() as db:
        people = await lock_message_authority(
            db, message.sender_id, message.connection_id, message.recipient_id
        )
        if people is None:
            won = await PeerDeliveryRepository(db).cancel_message(claim, "cancelled_not_connected")
            return "cancelled_not_connected" if won else "lost"
        count = await PeersRepository(db).count_messages_today_for_pair(
            message.sender_id, message.recipient_id, now=datetime.now(UTC)
        )
        await db.commit()
        return people[0], people[1], count


async def _prepare(
    message: PeerMessage, claim: DeliveryClaim, people: tuple[User, User, int], generate: Generate
) -> str:
    if message.prepared_text_encrypted is not None:
        return decrypt_data(message.prepared_text_encrypted)
    async with get_db_context() as db:
        if not await PeerDeliveryRepository(db).start_generation(claim):
            raise DeliveryLeaseLost("Cannot start a generation without the live claim")
    text = await generate(message, *people)
    if not text.strip():
        raise ValueError("Peer rendition is empty")
    async with get_db_context() as db:
        if not await PeerDeliveryRepository(db).store_prepared(claim, text):
            raise DeliveryLeaseLost("Cannot retain a generation under a lost claim")
    return text


async def _process(message: PeerMessage, claim: DeliveryClaim, generate: Generate) -> str:
    people = await _admit(message, claim)
    if isinstance(people, str):
        return people
    try:
        text = await _prepare(message, claim, people, generate)
    except DeliveryLeaseLost:
        raise
    except Exception as error:
        # Provider retries belong to the client. A scheduler never resets that
        # budget, and an unknown paid outcome must not purchase a second answer.
        code = "generation_outcome_unknown" if outcome_unknown(error) else "llm_error"
        logger.warning(
            "peers_delivery_generation_failed",
            message_id=str(message.id),
            error_type=type(error).__name__,
        )
        return await _fail(claim, code, retryable=False)
    try:
        return await commit_delivery(message, claim, text)
    except DeliveryLeaseLost:
        raise
    except Exception as error:
        logger.warning(
            "peers_delivery_archive_failed",
            message_id=str(message.id),
            error_type=type(error).__name__,
        )
        return await _fail(claim, "dispatch_error", retryable=True)


async def run_delivery(message: PeerMessage, generate: Generate) -> str:
    """Close cancellation, stop on lost ownership, and notify only settled acts."""
    claim = claim_of(message)
    try:
        async with delivery_lease(claim):
            outcome = await _process(message, claim, generate)
    except DeliveryLeaseLost:
        return "lost"
    except asyncio.CancelledError:

        async def close() -> None:
            await _fail(claim, "generation_outcome_unknown", retryable=False)

        await write_through_cancellation(
            close,
            attempts=PEERS_DELIVERY_CANCELLATION_GRACE_ATTEMPTS,
            label="peer_delivery_cancelled",
        )
        raise
    except Exception as error:
        logger.warning(
            "peers_delivery_unexpected_error",
            message_id=str(message.id),
            error_type=type(error).__name__,
        )
        outcome = await _fail(claim, "unexpected_error", retryable=False)
    await notify_result(message, outcome)
    return outcome


async def notify_result(message: PeerMessage, outcome: str) -> None:
    """Best-effort notifications after the durable transition, never replayed."""
    if outcome in {"pending", "lost"}:
        return
    try:
        async with get_db_context() as db:
            sender = await db.get(User, message.sender_id)
            recipient = await db.get(User, message.recipient_id)
            current = await db.get(PeerMessage, message.id)
            await db.commit()
            if sender is None or recipient is None or current is None:
                return
            if outcome == "delivered" and current.delivered_text:
                pushed = await NotificationDispatcher(archive_enabled=False).dispatch(
                    user=recipient,
                    content=current.delivered_text,
                    task_type=PEER_MESSAGE_TASK_TYPE,
                    target_id=str(message.id),
                    metadata=peer_message_metadata(message, sender),
                    db=db,
                )
                logger.debug(
                    "peer_delivery_transport_result",
                    message_id=str(message.id),
                    durable_transport=pushed.durably_delivered,
                )
            body = (
                ProactiveMessages.peer_message_delivered_body
                if outcome == "delivered"
                else ProactiveMessages.peer_message_failed_body
            )(recipient.full_name or "?", sender.language)
            notice = await NotificationDispatcher().dispatch(
                user=sender,
                content=body,
                task_type=PEER_CONNECTION_TASK_TYPE,
                target_id=str(message.id),
                metadata={"peer_message_notice": True},
                db=db,
            )
            logger.debug(
                "peer_delivery_sender_notice",
                message_id=str(message.id),
                durably_delivered=notice.durably_delivered,
            )
    except Exception as error:
        logger.warning(
            "peer_delivery_notice_failed",
            message_id=str(message.id),
            error_type=type(error).__name__,
        )
