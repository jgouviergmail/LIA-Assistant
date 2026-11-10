"""Atomic peer delivery: one message key, one archive and one owned settlement.

Conversation creation precedes the fenced transaction because that service
commits internally. Dispatch in the transaction has every external transport
disabled. Push/SSE/Telegram are conveniences AFTER the atomic commit, never a
reason to repeat an already durable message.
"""

from datetime import UTC, datetime
from uuid import UUID

from src.core.exceptions import AuthorizationError
from src.core.i18n_proactive import ProactiveMessages
from src.domains.conversations.service import ConversationService
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.constants import (
    PEER_MESSAGE_TASK_TYPE,
    PEER_META_MESSAGE_FLAG,
    PEER_META_SENDER_ID,
    PEER_META_SENDER_NAME,
    PEER_UNKNOWN_DISPLAY_NAME,
)
from src.domains.peers.delivery_repository import (
    DeliveryClaim,
    DeliveryLeaseLost,
    PeerDeliveryRepository,
)
from src.domains.peers.message_authority import lock_message_authority
from src.domains.peers.models import PeerMessage
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.proactive.notification import (
    NotificationDispatcher,
    NotificationNotDelivered,
)


def peer_message_metadata(message: PeerMessage, sender: User) -> dict[str, object]:
    """Use the same identity on the archive and its later optional transports."""
    return {
        PEER_META_MESSAGE_FLAG: True,
        PEER_META_SENDER_ID: str(message.sender_id),
        PEER_META_SENDER_NAME: sender.full_name or PEER_UNKNOWN_DISPLAY_NAME,
    }


async def _prepare_conversation(recipient_id: UUID) -> UUID | None:
    """Complete potentially committing conversation creation BEFORE claim locks."""
    async with get_db_context() as db:
        recipient = await db.get(User, recipient_id)
        if recipient is None:
            return None
        conversation = await ConversationService().get_or_create_conversation(
            recipient.id, db, language=recipient.language
        )
        conversation_id = conversation.id
        await db.commit()
        return conversation_id


async def commit_delivery(message: PeerMessage, claim: DeliveryClaim, text: str) -> str:
    """Revalidate and archive with settlement in one SQL transaction.

    Returns delivered only from the won, committed transition. The unique
    PeerMessage row is the durable notification key; an expired or repeated
    caller reaches no archive. No provider or channel is contacted here.
    """
    conversation_id = await _prepare_conversation(message.recipient_id)
    if conversation_id is None:
        return "lost"
    async with get_db_context() as db:
        people = await lock_message_authority(
            db, message.sender_id, message.connection_id, message.recipient_id
        )
        repo = PeerDeliveryRepository(db)
        current = await repo.lock_owned(claim)
        if current is None:
            return "lost"
        try:
            await require_capability_fresh(db, PlatformCapability.PEERS)
        except AuthorizationError:
            won = await repo.cancel_message(claim, "cancelled_disabled")
            await db.commit()
            return "cancelled_disabled" if won else "lost"
        if people is None:
            won = await repo.cancel_message(claim, "cancelled_not_connected")
            await db.commit()
            return "cancelled_not_connected" if won else "lost"
        if current.expires_at is not None and current.expires_at <= datetime.now(UTC):
            won = await repo.cancel_message(claim, "cancelled_content_expired")
            await db.commit()
            return "cancelled_content_expired" if won else "lost"
        sender, recipient = people
        result = await NotificationDispatcher(
            fcm_enabled=False, sse_enabled=False, channel_enabled=False
        ).dispatch(
            user=recipient,
            content=text,
            task_type=PEER_MESSAGE_TASK_TYPE,
            target_id=str(message.id),
            metadata=peer_message_metadata(message, sender),
            db=db,
            title=ProactiveMessages.notification_title(PEER_MESSAGE_TASK_TYPE, recipient.language),
            archive_conversation_id=conversation_id,
            commit_before_notification=False,
            require_durable=True,
        )
        if not result.durably_delivered or not result.archived:
            raise NotificationNotDelivered(result)
        if not await repo.mark_message_delivered(claim, now=datetime.now(UTC), delivered_text=text):
            raise DeliveryLeaseLost("Lease expired before atomic peer settlement")
        await db.commit()
    return "delivered"
