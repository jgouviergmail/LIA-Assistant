"""Receipt-backed archive outbox; notification IO follows the durable commit."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select, update

from src.core.config import settings
from src.core.constants import PROACTIVE_MESSAGE_TYPE_PREFIX
from src.core.i18n_capability_sharing import capability_shared_body
from src.domains.peers.capability_contracts import TransferStatus
from src.domains.peers.capability_models import PeerCapabilityTransfer
from src.domains.shared.markdown_literal import markdown_data_literal
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.proactive.notification import NotificationDispatcher

logger = get_logger(__name__)
TASK_TYPE = "peer_capability_shared"


async def deliver_capability_receipt(transfer_id: UUID) -> None:
    if not settings.peers_enabled:
        return
    try:
        async with get_db_context() as db:
            receipt = (
                await db.execute(
                    select(PeerCapabilityTransfer)
                    .where(PeerCapabilityTransfer.id == transfer_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if (
                receipt is None
                or receipt.notification_sent
                or receipt.status not in {TransferStatus.INSTALLED, TransferStatus.PARTIAL}
            ):
                return
            recipient = await db.get(User, receipt.recipient_id)
            if recipient is None or not recipient.is_active or recipient.deleted_at is not None:
                return
            body = capability_shared_body(markdown_data_literal(receipt.name), recipient.language)
            metadata = {
                "type": f"{PROACTIVE_MESSAGE_TYPE_PREFIX}{TASK_TYPE}",
                "target_id": str(receipt.id),
                "feedback_enabled": False,
                "sent_at": datetime.now(UTC).isoformat(),
            }
            dispatcher = NotificationDispatcher()
            await dispatcher._archive_message(recipient, body, metadata, db)
            receipt.notification_sent = True
            recipient_id = receipt.recipient_id
    except Exception as exc:
        logger.warning(
            "peer_capability_notification_pending",
            transfer_id=str(transfer_id),
            error_type=type(exc).__name__,
        )
        return
    # No transaction, row lock, model or second action record around the publish.
    try:
        await dispatcher._publish_sse(
            recipient_id, body, body, TASK_TYPE, str(transfer_id), metadata
        )
    except Exception as exc:
        logger.warning(
            "peer_capability_live_delivery_failed",
            transfer_id=str(transfer_id),
            error_type=type(exc).__name__,
        )


async def maintain_capability_transfers() -> None:
    async with get_db_context() as db:
        expired = (PeerCapabilityTransfer.expires_at <= func.clock_timestamp()) & or_(
            PeerCapabilityTransfer.lease_expires_at.is_(None),
            PeerCapabilityTransfer.lease_expires_at <= func.clock_timestamp(),
        )
        await db.execute(
            update(PeerCapabilityTransfer)
            .where(expired, PeerCapabilityTransfer.snapshot.is_not(None))
            .values(
                snapshot=None,
                lease_owner=None,
                lease_expires_at=None,
                fence=PeerCapabilityTransfer.fence + 1,
                error_code="peers_capability_expired",
            )
        )
        await db.execute(
            update(PeerCapabilityTransfer)
            .where(
                expired,
                PeerCapabilityTransfer.status.in_(
                    [TransferStatus.PREPARING, TransferStatus.INSTALLING]
                ),
            )
            .values(status=TransferStatus.CANCELLED.value)
        )
        if not settings.peers_enabled:
            return  # Expiry commits on context exit; delivery stays disabled.
        pending = list(
            await db.scalars(
                select(PeerCapabilityTransfer.id)
                .where(
                    PeerCapabilityTransfer.status.in_(
                        [TransferStatus.INSTALLED, TransferStatus.PARTIAL]
                    ),
                    PeerCapabilityTransfer.notification_sent.is_(False),
                )
                .order_by(PeerCapabilityTransfer.created_at)
                .limit(settings.peers_capability_sender_daily_limit)
            )
        )
    for transfer_id in pending:
        await deliver_capability_receipt(transfer_id)
