"""The calls a webhook routine accepted, from its address to the run that serves them.

ADR-386. One repository for every statement on ``routine_webhook_deliveries`` and
for the routine reads the door needs:

- the door finds a routine by its address key WITHOUT a lock (the signature is
  checked on that read), then takes the routine's row lock for the write: the
  duplicate check, the backlog bound and the insert are decided one call at a
  time per routine, and a run's settle — which takes the same lock — cannot
  slip between them;
- a delivery the sender names is stored once per routine (a partial unique
  index, ``ON CONFLICT DO NOTHING``), served or not;
- the body is stored as text, encrypted, and erased when a run serves it; the
  row stays a week so the same delivery, sent again, is still recognised.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.scheduled_actions.models import (
    RoutineWebhookDelivery,
    RoutineWebhookDeliveryStatus,
    ScheduledAction,
    TriggerKind,
)
from src.domains.scheduled_actions.webhooks import WaitingCall

logger = structlog.get_logger(__name__)

_PENDING = RoutineWebhookDeliveryStatus.PENDING.value
_SERVED = RoutineWebhookDeliveryStatus.SERVED.value


class RoutineWebhookRepository:
    """Statements on a webhook routine's address and on the calls it accepted."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def find_by_key(self, key: str) -> ScheduledAction | None:
        """The webhook routine this address names, read without a lock.

        Args:
            key: The address key, as the caller spelled it.

        Returns:
            The routine, or None when no webhook routine has this address.
        """
        result = await self.db.execute(
            select(ScheduledAction).where(
                ScheduledAction.webhook_key == key,
                ScheduledAction.trigger_kind == TriggerKind.WEBHOOK.value,
            )
        )
        return result.scalar_one_or_none()

    async def lock_routine(self, action_id: UUID) -> ScheduledAction | None:
        """Lock the routine's row for a call's write, and read it afresh.

        Args:
            action_id: The routine found by its address.

        Returns:
            The locked row, refreshed; None when it was deleted meanwhile.
        """
        result = await self.db.execute(
            select(ScheduledAction)
            .where(ScheduledAction.id == action_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def already_received(self, action_id: UUID, delivery_id: str) -> bool:
        """Whether this routine already accepted a delivery of this id, served or not."""
        statement = select(
            exists().where(
                RoutineWebhookDelivery.scheduled_action_id == action_id,
                RoutineWebhookDelivery.delivery_id == delivery_id,
            )
        )
        return bool((await self.db.execute(statement)).scalar())

    async def count_pending(self, action_id: UUID) -> int:
        """How many calls of this routine wait for a run."""
        statement = select(func.count()).where(
            RoutineWebhookDelivery.scheduled_action_id == action_id,
            RoutineWebhookDelivery.status == _PENDING,
        )
        return int((await self.db.execute(statement)).scalar_one())

    async def has_pending(self, action_id: UUID) -> bool:
        """Whether any call of this routine waits for a run."""
        statement = select(
            exists().where(
                RoutineWebhookDelivery.scheduled_action_id == action_id,
                RoutineWebhookDelivery.status == _PENDING,
            )
        )
        return bool((await self.db.execute(statement)).scalar())

    async def store(
        self,
        action_id: UUID,
        *,
        delivery_id: str | None,
        content_type: str | None,
        body: bytes,
        at: datetime,
    ) -> bool:
        """Keep one accepted call, its body encrypted.

        Args:
            action_id: The routine called.
            delivery_id: The sender's id for the delivery, when it gave one.
            content_type: The media type it declared, if any.
            body: The raw body; read as UTF-8 text, any byte that is not replaced.
            at: When it was accepted (UTC).

        Returns:
            True when stored; False when this delivery id was already stored
            for this routine (a sender's retry).
        """
        text = body.decode("utf-8", errors="replace")
        statement = (
            pg_insert(RoutineWebhookDelivery)
            .values(
                scheduled_action_id=action_id,
                delivery_id=delivery_id,
                received_at=at,
                content_type=content_type,
                body_bytes=len(body),
                body=encrypt_data(text),
                status=_PENDING,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    RoutineWebhookDelivery.scheduled_action_id,
                    RoutineWebhookDelivery.delivery_id,
                ],
                index_where=RoutineWebhookDelivery.delivery_id.is_not(None),
            )
            .returning(RoutineWebhookDelivery.id)
        )
        return (await self.db.execute(statement)).scalar_one_or_none() is not None

    async def pending(self, action_id: UUID, *, limit: int) -> list[WaitingCall]:
        """The calls a run serves: this routine's oldest waiting ones, decrypted.

        Args:
            action_id: The routine.
            limit: How many one run serves.

        Returns:
            At most ``limit`` calls, oldest first. A body that cannot be
            decrypted comes back as ``text=None`` (logged by its row id) — the
            run is told the call happened and that its body could not be read.
        """
        result = await self.db.execute(
            select(RoutineWebhookDelivery)
            .where(
                RoutineWebhookDelivery.scheduled_action_id == action_id,
                RoutineWebhookDelivery.status == _PENDING,
            )
            .order_by(RoutineWebhookDelivery.received_at, RoutineWebhookDelivery.id)
            .limit(limit)
        )
        return [_waiting(row) for row in result.scalars().all()]

    async def serve(self, action_id: UUID, ids: Sequence[UUID], *, at: datetime) -> int:
        """Mark the calls a run that answered has read as served, their bodies erased.

        Args:
            action_id: The routine (a call of another routine is never touched).
            ids: The calls the run read.
            at: When the run's outcome was settled (UTC).

        Returns:
            How many calls changed (a call already served is not counted).
        """
        if not ids:
            return 0
        result = await self.db.execute(
            update(RoutineWebhookDelivery)
            .where(
                RoutineWebhookDelivery.scheduled_action_id == action_id,
                RoutineWebhookDelivery.id.in_(list(ids)),
                RoutineWebhookDelivery.status == _PENDING,
            )
            .values(status=_SERVED, served_at=at, body=None)
            .returning(RoutineWebhookDelivery.id)
        )
        return len(result.scalars().all())

    async def discard(self, action_id: UUID) -> int:
        """Forget every call of a routine that no longer runs on calls.

        Args:
            action_id: The routine whose clock changed.

        Returns:
            How many rows went.
        """
        result = await self.db.execute(
            delete(RoutineWebhookDelivery)
            .where(RoutineWebhookDelivery.scheduled_action_id == action_id)
            .returning(RoutineWebhookDelivery.id)
        )
        return len(result.scalars().all())

    async def purge_served_before(self, cutoff: datetime) -> int:
        """Drop the served calls older than the retention, whatever their routine.

        Args:
            cutoff: Served before this instant (UTC) is old enough to go.

        Returns:
            How many rows went.
        """
        result = await self.db.execute(
            delete(RoutineWebhookDelivery)
            .where(
                RoutineWebhookDelivery.status == _SERVED,
                RoutineWebhookDelivery.served_at < cutoff,
            )
            .returning(RoutineWebhookDelivery.id)
        )
        return len(result.scalars().all())


def _waiting(row: RoutineWebhookDelivery) -> WaitingCall:
    """One stored call as a run reads it, its body decrypted when it can be."""
    text: str | None = None
    if row.body is not None:
        try:
            text = decrypt_data(row.body)
        except ValueError:
            # A body the current key cannot read (a rotated key): the run is
            # told the call came and its body could not be read.
            logger.warning("routine_webhook_body_unreadable", delivery_row_id=str(row.id))
    return WaitingCall(
        id=row.id,
        delivery_id=row.delivery_id,
        received_at=row.received_at,
        content_type=row.content_type,
        body_bytes=row.body_bytes,
        text=text,
    )


__all__ = ["RoutineWebhookRepository"]
