"""Existing SSE, FCM and channel diffusion after one durable archive commit."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.notification_privacy import (
    PRIVATE_NOTIFICATION_MARKER,
    NotificationPrivacy,
    notification_preview,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.notifications.service import FCMNotificationService, FCMSendResult
from src.domains.proactive_discussions.models import DiscussionOutbox
from src.domains.proactive_discussions.outbox_repository import (
    DiscussionDelivery,
    DiscussionOutboxRepository,
)
from src.domains.shared.consultation_sink import consultation_collector
from src.infrastructure.cache.user_channel import publish_to_user
from src.infrastructure.database.session import get_db_context
from src.infrastructure.proactive.discussion_delivery_authority import delivery_sources_permitted
from src.infrastructure.proactive.notification import (
    plain_text_for_notification,
    send_notification_to_channels,
)

logger = structlog.get_logger(__name__)


async def _may_send(envelope: DiscussionDelivery) -> bool:
    if not settings.proactive_discussions_enabled:
        return False
    async with get_db_context() as db:
        try:
            await require_capability_fresh(db, PlatformCapability.PROACTIVE_DISCUSSIONS)
        except AuthorizationError:
            return False
        current = await DiscussionOutboxRepository(db).may_send(envelope, now=datetime.now(UTC))
    if not current:
        return False
    try:
        # Reading the proofs again opens the person's sources: filed under the run.
        async with consultation_collector(str(envelope.run_id)):
            return await delivery_sources_permitted(
                envelope.owner_id, envelope.run_id, envelope.metadata.get("discussion_proofs", [])
            )
    except Exception as exc:
        # Doubt never sends; it is still a fault to see, not a refusal.
        logger.warning(
            "discussion_delivery_authority_failed",
            user_id=str(envelope.owner_id),
            opening_id=str(envelope.opening_id),
            error_type=type(exc).__name__,
        )
        return False


async def dispatch_discussion(owner: UUID, opening_id: UUID) -> bool:
    """Deliver one published opening once: chat stream, pushes and external channels.

    The attempt is claimed first and every send asks again whether it may still go
    out; a private opening masks its push and never reaches an external channel.
    The attempt is settled whatever happens; an interrupted one stays uncertain and
    is never replayed.

    Args:
        owner: The account.
        opening_id: The opening.

    Returns:
        True when at least one transport accepted the opening.
    """
    async with get_db_context() as db:
        envelope = await DiscussionOutboxRepository(db).claim_delivery(
            owner, opening_id, now=datetime.now(UTC)
        )
    if envelope is None:
        return False
    accepted, uncertain = False, False
    try:
        if not await _may_send(envelope):
            return False
        accepted = bool(
            await publish_to_user(
                owner,
                {
                    "type": "proactive_discussion",
                    "content": envelope.text,
                    "title": "LIA",
                    "target_id": str(envelope.opening_id),
                    "message_id": str(envelope.message_id),
                    "conversation_id": str(envelope.conversation_id),
                    "metadata": {
                        **envelope.metadata,
                        "feedback_enabled": False,
                        "message_id": str(envelope.message_id),
                    },
                },
            )
        )
        accepted = await _send_pushes(envelope) or accepted
        if settings.channels_enabled and not envelope.sensitive and await _may_send(envelope):
            accepted = (
                bool(
                    await send_notification_to_channels(
                        owner,
                        "LIA",
                        envelope.text,
                        "proactive_discussion",
                        str(envelope.opening_id),
                    )
                )
                or accepted
            )
        return accepted
    except BaseException:
        uncertain = True
        raise
    finally:

        async def settle() -> None:
            async with get_db_context() as db:
                await DiscussionOutboxRepository(db).settle_delivery(
                    envelope, accepted=accepted, uncertain=uncertain
                )

        await asyncio.shield(settle())


async def dispatch_pending_discussions() -> None:
    """Recover stalled attempts, then deliver the oldest pending openings.

    At most ``discussion_delivery_batch_size`` per call; one owner's failure is logged
    and never stops the others.
    """
    async with get_db_context() as db:
        await DiscussionOutboxRepository(db).recover_deliveries(now=datetime.now(UTC))
        pending = tuple(
            (
                await db.execute(
                    select(DiscussionOutbox.user_id, DiscussionOutbox.opening_id)
                    .where(DiscussionOutbox.state == "pending")
                    .order_by(DiscussionOutbox.created_at)
                    .limit(settings.discussion_delivery_batch_size)
                )
            )
            .tuples()
            .all()
        )
    for owner, opening in pending:
        try:
            await dispatch_discussion(owner, opening)
        except Exception as exc:
            # The durable uncertain receipt prevents replay after a lost acknowledgement.
            logger.warning(
                "discussion_delivery_failed",
                user_id=str(owner),
                opening_id=str(opening),
                error_type=type(exc).__name__,
            )


async def _send_pushes(envelope: DiscussionDelivery) -> bool:
    privacy = (
        NotificationPrivacy.IN_APP_SENSITIVE if envelope.sensitive else NotificationPrivacy.NORMAL
    )
    title, body = notification_preview(
        privacy, envelope.language, "LIA", plain_text_for_notification(envelope.text)[:150]
    )
    async with get_db_context() as db:
        service = FCMNotificationService(db)
        tokens = tuple(
            (token.id, token.token) for token in await service.get_active_tokens(envelope.owner_id)
        )
    sent: list[tuple[UUID, str, FCMSendResult]] = []
    for token_id, token in tokens:
        if not await _may_send(envelope):
            break
        result = await service.send_to_device(
            token=token,
            title=title,
            body=body,
            occurrence_key=str(envelope.opening_id),
            data={
                "type": "proactive_discussion",
                "target_id": str(envelope.opening_id),
                "message_id": str(envelope.message_id),
                "conversation_id": str(envelope.conversation_id),
                "run_id": str(envelope.run_id),
                "feedback_enabled": "false",
                PRIVATE_NOTIFICATION_MARKER: "true" if envelope.sensitive else "false",
                "click_action": "OPEN_CHAT",
            },
        )
        sent.append((token_id, token, result))
    # Every send first, every status write after (ADR-304), like the batch sender.
    if sent:
        async with get_db_context() as db:
            repository = FCMNotificationService(db).repository
            for token_id, token, result in sent:
                if result.success:
                    await repository.update_last_used(token_id)
                elif result.token_invalid:
                    await repository.deactivate_token(token, result.error)
    return any(result.success for _, _, result in sent)
