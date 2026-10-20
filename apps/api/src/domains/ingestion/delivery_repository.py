"""Owner-first leases. No network I/O and no implicit transaction commit."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.ingestion.delivery_types import (
    DeliveryClaim,
    DeliveryDestination,
    DeliveryDisposition,
    DeliveryResult,
)
from src.domains.ingestion.models import IngestionDelivery, IngestionReceipt, IngestionSource
from src.domains.ingestion.registry import IngestionResource
from src.domains.users.models import User

MAX_DELIVERY_ATTEMPTS = 5


def _claim(row: IngestionDelivery) -> DeliveryClaim:
    if row.lease_owner is None or row.lease_until is None:
        raise ValueError("Delivery has no lease")
    return DeliveryClaim(
        row.id,
        row.user_id,
        row.receipt_id,
        row.destination_key,
        row.device_id,
        row.fence,
        row.lease_owner,
        row.lease_until,
        row.attempts,
        row.effect_id,
    )


async def _candidate(
    db: AsyncSession, now: datetime, *, sending: bool, resource: IngestionResource
) -> IngestionDelivery | None:
    eligible = (
        and_(IngestionDelivery.state == "sending", IngestionDelivery.lease_until <= now)
        if sending
        else and_(
            IngestionDelivery.state == "pending",
            or_(
                IngestionDelivery.next_attempt_at.is_(None),
                IngestionDelivery.next_attempt_at <= now,
            ),
            or_(IngestionDelivery.lease_until.is_(None), IngestionDelivery.lease_until <= now),
        )
    )
    # Writers always lock User first. Locking a delivery first would deadlock
    # against erasure/revocation, which update deliveries under that owner fence.
    candidate = await db.execute(
        select(User, IngestionDelivery.id)
        .join(IngestionDelivery, IngestionDelivery.user_id == User.id)
        .join(IngestionReceipt, IngestionReceipt.id == IngestionDelivery.receipt_id)
        .join(IngestionSource, IngestionSource.id == IngestionReceipt.source_id)
        .where(eligible, IngestionSource.resource == resource.value)
        .order_by(IngestionDelivery.created_at, IngestionDelivery.id)
        .limit(1)
        .with_for_update(of=User, skip_locked=True)
        .execution_options(populate_existing=True)
    )
    found = candidate.first()
    if found is None:
        return None
    result = await db.scalars(
        select(IngestionDelivery)
        .where(IngestionDelivery.id == found[1], eligible)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def claim_next(
    db: AsyncSession,
    worker: UUID,
    *,
    now: datetime,
    lease_seconds: int = 60,
    resource: IngestionResource = IngestionResource.SMS,
) -> DeliveryClaim | None:
    if not 1 <= lease_seconds <= 3600:
        raise ValueError("Invalid delivery lease")
    row = await _candidate(db, now, sending=False, resource=resource)
    if row is None:
        return None
    row.fence += 1
    row.lease_owner = worker
    row.lease_until = now + timedelta(seconds=lease_seconds)
    await db.flush()
    return _claim(row)


async def _owned(db: AsyncSession, claim: DeliveryClaim, state: str) -> IngestionDelivery | None:
    await db.scalar(select(User.id).where(User.id == claim.user_id).with_for_update())
    result = await db.scalars(
        select(IngestionDelivery)
        .where(
            IngestionDelivery.id == claim.id,
            IngestionDelivery.user_id == claim.user_id,
            IngestionDelivery.fence == claim.fence,
            IngestionDelivery.lease_owner == claim.worker,
            IngestionDelivery.state == state,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.one_or_none()


async def mark_sending(db: AsyncSession, claim: DeliveryClaim, *, now: datetime) -> bool:
    row = await _owned(db, claim, "pending")
    if row is None or row.lease_until is None or row.lease_until <= now:
        return False
    row.state = "sending"
    row.attempts += 1
    await db.flush()
    return True


async def expand_fanout(
    db: AsyncSession,
    claim: DeliveryClaim,
    destinations: tuple[DeliveryDestination, ...],
    *,
    now: datetime,
) -> bool:
    if len({d.key for d in destinations}) != len(destinations):
        raise ValueError("Duplicate delivery destination")
    row = await _owned(db, claim, "pending")
    if (
        row is None
        or row.destination_key != "fanout"
        or row.lease_until is None
        or row.lease_until <= now
    ):
        return False
    db.add_all(
        [
            IngestionDelivery(
                user_id=row.user_id,
                receipt_id=row.receipt_id,
                destination_key=d.key,
                device_id=d.device_id,
            )
            for d in destinations
        ]
    )
    row.state = "expanded"
    row.lease_until = None
    row.lease_owner = None
    await db.flush()
    return True


async def settle_delivery(
    db: AsyncSession, claim: DeliveryClaim, result: DeliveryResult, *, now: datetime
) -> bool:
    row = await _owned(db, claim, "sending")
    if row is None:
        return False
    states = {
        DeliveryDisposition.ACCEPTED: "sent",
        DeliveryDisposition.PERMANENT: "failed",
        DeliveryDisposition.UNKNOWN: "unknown",
        DeliveryDisposition.CANCELLED: "cancelled",
    }
    if result.disposition == DeliveryDisposition.RETRYABLE:
        row.state = "pending" if row.attempts < MAX_DELIVERY_ATTEMPTS else "failed"
        row.next_attempt_at = now + timedelta(
            seconds=max(result.retry_after_seconds, min(3600, 60 * 2 ** (row.attempts - 1)))
        )
    else:
        row.state = states[result.disposition]
        row.next_attempt_at = None
    row.last_error_code = result.error_code
    row.lease_until = None
    row.lease_owner = None
    await db.flush()
    return True


async def recover_expired_send(
    db: AsyncSession, *, now: datetime, resource: IngestionResource = IngestionResource.SMS
) -> DeliveryClaim | None:
    row = await _candidate(db, now, sending=True, resource=resource)
    if row is None:
        return None
    previous = _claim(row)
    row.state = "unknown"
    row.last_error_code = "DELIVERY_ACK_UNKNOWN"
    row.fence += 1
    row.lease_owner = None
    row.lease_until = None
    await db.flush()
    return previous
