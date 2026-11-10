"""One transactional admission command for direct and historical draft relays.

The caller's execution gate owns idempotency. This command owns current pair
authority and quotas: account fences precede the pair lock, count and insert.
Delivery is asynchronous; an enqueue receipt never claims delivery.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.peers.message_authority import lock_message_authority
from src.domains.peers.repository import PeersRepository
from src.domains.usage_limits.service import UsageLimitService
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


class PeerMessageRefusal(str, Enum):
    """Neutral admission verdicts shared by both execution paths."""

    DISABLED = "peers_disabled"
    INVALID_MESSAGE = "peers_invalid_message"
    NOT_CONNECTED = "peers_not_connected"
    QUOTA_REACHED = "peers_quota_reached"


@dataclass(frozen=True)
class PeerMessageReceipt:
    """A committed queue receipt, with the recipient's current display name."""

    message_id: UUID
    recipient_name: str


def valid_peer_message(message: str) -> bool:
    """Publish the same text bound to the tool preflight and the final admission."""
    return bool(message.strip()) and len(message) <= settings.peers_message_max_chars


async def _quota_available(repo: PeersRepository, sender: UUID, recipient: UUID) -> bool:
    """Count admissions while the sender's account fence serializes all targets."""
    now = datetime.now(UTC)
    if await repo.count_messages_today(sender, now=now) >= settings.peers_message_max_per_day:
        return False
    return (
        await repo.count_messages_today_for_pair(sender, recipient, now=now)
        < settings.peers_message_max_per_day_per_pair
    )


async def enqueue_peer_message(
    sender_id: UUID, connection_id: UUID, recipient_id: UUID, message: str
) -> PeerMessageReceipt | PeerMessageRefusal:
    """Revalidate, quota-check and commit exactly one authorized queue admission.

    Args:
        sender_id: The execution's owner, never a model-selected sender.
        connection_id: Previously resolved or historical connection identity.
        recipient_id: Expected counterpart, verified against that connection.
        message: The sender's directive, retained under the existing TTL.

    Returns:
        A committed pending message or a neutral typed refusal.

    Raises:
        SQLAlchemyError: A failed transaction; the context rolls it back.
    """
    if not valid_peer_message(message):
        return PeerMessageRefusal.INVALID_MESSAGE
    if sender_id == recipient_id:
        return PeerMessageRefusal.NOT_CONNECTED
    # Both potentially external admission reads precede any SQL session/lock.
    if not await is_capability_enabled(PlatformCapability.PEERS):
        return PeerMessageRefusal.DISABLED
    if await UsageLimitService.is_user_blocked_for_llm(sender_id, layer="peer_message_send"):
        return PeerMessageRefusal.QUOTA_REACHED
    async with get_db_context() as db:
        people = await lock_message_authority(db, sender_id, connection_id, recipient_id)
        if people is None:
            return PeerMessageRefusal.NOT_CONNECTED
        repo = PeersRepository(db)
        if not await _quota_available(repo, sender_id, recipient_id):
            return PeerMessageRefusal.QUOTA_REACHED
        row = await repo.enqueue_message(connection_id, sender_id, recipient_id, message)
        receipt = PeerMessageReceipt(row.id, people[1].full_name or "")
        await db.commit()
    logger.info("peer_message_enqueued", user_id=str(sender_id), message_id=str(receipt.message_id))
    return receipt
