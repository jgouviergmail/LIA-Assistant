"""The sent-broadcasts history an administrator reads under the send form (ADR-312).

A read model, kept apart from the send service: one page of broadcasts, the
exact total, each row's audience with a sample of its recipients, its expiry
and its read receipts. Every figure is an aggregate over the whole set (ADR-185)
— never the length of a capped page — and the whole page costs four queries
whatever its size (page, total, reads, recipient samples).

The message is shown as the admin wrote it: reading the history never triggers
the lazy translation the recipients' unread listing performs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import BROADCAST_HISTORY_RECIPIENTS_SHOWN
from src.domains.notifications.models import AdminBroadcast, BroadcastAudience
from src.domains.notifications.repository import BroadcastRepository, RecipientSample
from src.domains.notifications.schemas import (
    BroadcastHistoryItem,
    BroadcastHistoryResponse,
    BroadcastRecipientView,
)

_SECONDS_PER_DAY = 86_400


def expiry_delay_days(sent_at: datetime, expires_at: datetime | None) -> int | None:
    """The expiry delay the admin chose, in whole days.

    Only the instant is stored; it was computed as ``now + N days`` a few
    milliseconds before the row's ``created_at``, so rounding recovers N.

    Args:
        sent_at: The broadcast's creation instant.
        expires_at: Its expiry instant, or None for « never ».

    Returns:
        The delay in days, or None when the broadcast never expires.
    """
    if expires_at is None:
        return None
    return max(0, round((expires_at - sent_at).total_seconds() / _SECONDS_PER_DAY))


def _sender_name(broadcast: AdminBroadcast) -> str | None:
    """The sending admin's name, or their e-mail — None once the account is gone."""
    sender = broadcast.sender
    if sender is None:
        return None
    return sender.full_name or sender.email


def _history_item(
    broadcast: AdminBroadcast,
    *,
    read_count: int,
    sample: RecipientSample | None,
    now: datetime,
) -> BroadcastHistoryItem:
    """One row of the history, every figure taken from its own aggregate."""
    users = sample.users if sample is not None else ()
    return BroadcastHistoryItem(
        id=broadcast.id,
        message=broadcast.message,
        sent_at=broadcast.created_at,
        sender_name=_sender_name(broadcast),
        audience=BroadcastAudience(broadcast.audience),
        recipients=[
            BroadcastRecipientView(id=row.user_id, full_name=row.full_name, email=row.email)
            for row in users
        ],
        recipients_total=sample.total if sample is not None else 0,
        reached_count=broadcast.total_recipients,
        expires_at=broadcast.expires_at,
        expires_in_days=expiry_delay_days(broadcast.created_at, broadcast.expires_at),
        is_expired=broadcast.expires_at is not None and broadcast.expires_at <= now,
        fcm_sent=broadcast.fcm_sent,
        fcm_failed=broadcast.fcm_failed,
        read_count=read_count,
    )


async def broadcast_history(
    db: AsyncSession, *, limit: int, offset: int, now: datetime | None = None
) -> BroadcastHistoryResponse:
    """One page of the sent broadcasts, newest first, with the exact total.

    Args:
        db: A session the caller owns.
        limit: Rows per page (bounded by the route).
        offset: Rows skipped before the page.
        now: The instant « expired » is judged at; the current time by default.

    Returns:
        The page as the admin history draws it.
    """
    repo = BroadcastRepository(db)
    broadcasts, total = await repo.list_page(limit=limit, offset=offset)
    ids = [broadcast.id for broadcast in broadcasts]
    reads = await repo.read_counts(ids)
    samples = await repo.recipient_samples(ids, per_broadcast=BROADCAST_HISTORY_RECIPIENTS_SHOWN)
    moment = now or datetime.now(UTC)
    return BroadcastHistoryResponse(
        items=[
            _history_item(
                broadcast,
                read_count=reads.get(broadcast.id, 0),
                sample=samples.get(broadcast.id),
                now=moment,
            )
            for broadcast in broadcasts
        ],
        total=total,
    )
