"""Durable per-destination dispatch; SQL fences never span transport I/O."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.effects.scheduled_notification import (
    NotificationEffect,
    abandon_notification,
    claim_notification,
    close_notification,
)
from src.domains.ingestion.delivery_repository import (
    claim_next,
    expand_fanout,
    mark_sending,
    recover_expired_send,
    settle_delivery,
)
from src.domains.ingestion.delivery_types import (
    DeliveryClaim,
    DeliveryDestination,
    DeliveryDisposition,
    DeliveryResult,
)
from src.domains.ingestion.models import IngestionDelivery, IngestionReceipt
from src.domains.ingestion.registry import IngestionResource
from src.domains.notifications.models import UserFCMToken
from src.domains.sms.notifications import notice_for
from src.infrastructure.observability.metrics_ingestion import ingestion_delivery_outcomes_total

logger = structlog.get_logger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True, slots=True)
class DeliveryEnvelope:
    user_id: UUID
    message_id: UUID
    occurrence: UUID
    destination_key: str
    device_id: UUID | None
    title: str
    body: str
    token: str | None = field(default=None, repr=False)
    language: str | None = None


class DeliveryTransport(Protocol):
    async def send(self, envelope: DeliveryEnvelope) -> DeliveryResult: ...


class IngestionDeliveryWorker:
    def __init__(self, sessions: SessionFactory, transport: DeliveryTransport) -> None:
        self.sessions = sessions
        self.transport = transport
        self.worker = uuid4()

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        async with asyncio.timeout(settings.ingestion_delivery_sql_timeout_seconds):
            async with self.sessions() as db:
                yield db

    async def run_once(self, *, now: datetime | None = None, limit: int = 50) -> None:
        stamp = now or datetime.now(UTC)
        deadline = monotonic() + settings.ingestion_delivery_sweep_seconds
        for _ in range(limit):
            if monotonic() >= deadline or not await self._recover(stamp):
                break
        for _ in range(limit):
            if monotonic() >= deadline:
                break
            stamp = now or datetime.now(UTC)
            async with self._transaction() as db:
                claim = await claim_next(
                    db,
                    self.worker,
                    now=stamp,
                    lease_seconds=settings.ingestion_delivery_lease_seconds,
                    resource=IngestionResource.SMS,
                )
                await db.commit()
            if claim is None:
                break
            await self._dispatch(claim, now)

    async def _dispatch(self, claim: DeliveryClaim, now: datetime | None) -> None:
        prepared = await self._prepare(claim, now or datetime.now(UTC))
        if prepared is None:
            return
        envelope, ticket = prepared
        try:
            async with asyncio.timeout(settings.ingestion_delivery_timeout_seconds):
                result = await self.transport.send(envelope)
        except Exception as error:
            logger.warning("ingestion_transport_ack_unknown", error_type=type(error).__name__)
            result = DeliveryResult(DeliveryDisposition.UNKNOWN, "DELIVERY_ACK_UNKNOWN")
        await self._settle(claim, ticket, result, now or datetime.now(UTC))

    async def _settle(
        self,
        claim: DeliveryClaim,
        ticket: NotificationEffect,
        result: DeliveryResult,
        now: datetime,
    ) -> None:
        async with self._transaction() as db:
            settled = await settle_delivery(db, claim, result, now=now)
            if settled:
                await close_notification(
                    db, ticket, outcome=result.disposition.value, error_code=result.error_code
                )
                await self._device_result(db, claim, result, now)
            else:
                await abandon_notification(db, claim.user_id, ticket.id)
            await db.commit()
        if settled:
            ingestion_delivery_outcomes_total.labels(
                destination="sse" if claim.device_id is None else "device",
                outcome=result.disposition.value,
            ).inc()

    @staticmethod
    async def _device_result(
        db: AsyncSession, claim: DeliveryClaim, result: DeliveryResult, now: datetime
    ) -> None:
        if claim.device_id is None:
            return
        device = await db.get(UserFCMToken, claim.device_id)
        if device is None or device.user_id != claim.user_id:
            return
        if result.disposition == DeliveryDisposition.ACCEPTED:
            device.last_used_at = now
        elif result.error_code == "DEVICE_INVALID":
            device.is_active = False
            device.last_error = "DEVICE_INVALID"

    async def _recover(self, now: datetime) -> bool:
        async with self._transaction() as db:
            expired = await recover_expired_send(db, now=now, resource=IngestionResource.SMS)
            if expired is not None:
                await abandon_notification(db, expired.user_id, expired.effect_id)
            await db.commit()
            if expired is not None:
                ingestion_delivery_outcomes_total.labels(
                    destination="device" if expired.device_id else "sse", outcome="unknown"
                ).inc()
            return expired is not None

    async def _prepare(
        self, claim: DeliveryClaim, now: datetime
    ) -> tuple[DeliveryEnvelope, NotificationEffect] | None:
        async with self._transaction() as db:
            # Reacquire through mark_sending/expand before inspecting current
            # policy: the owner fence is the send's authority linearization.
            if not await mark_sending(db, claim, now=now):
                return None
            notice = await notice_for(db, claim.user_id, claim.receipt_id)
            row = await db.get(IngestionDelivery, claim.id)
            if row is None:
                return None
            if notice is None:
                row.state = "cancelled"
                row.lease_owner = None
                row.lease_until = None
                await db.commit()
                return None
            if claim.destination_key == "fanout":
                row.state = "pending"
                row.attempts -= 1
                receipt = await db.get(IngestionReceipt, claim.receipt_id)
                if receipt is None:
                    return None
                devices = (
                    await db.scalars(
                        select(UserFCMToken).where(
                            UserFCMToken.user_id == claim.user_id,
                            UserFCMToken.is_active.is_(True),
                            UserFCMToken.created_at <= receipt.created_at,
                        )
                    )
                ).all()
                targets = (
                    DeliveryDestination("sse"),
                    *(DeliveryDestination(f"device:{d.id}", d.id) for d in devices),
                )
                await db.flush()
                await expand_fanout(db, claim, targets, now=now)
                await db.commit()
                return None
            token = None
            if claim.device_id is not None:
                device = await db.get(UserFCMToken, claim.device_id, populate_existing=True)
                if device is None or device.user_id != claim.user_id or not device.is_active:
                    row.state = "cancelled"
                    row.lease_owner = None
                    row.lease_until = None
                    await db.commit()
                    return None
                token = device.token
            ticket = await claim_notification(
                db,
                owner=claim.user_id,
                occurrence=claim.receipt_id,
                delivery=claim.id,
                attempt=row.attempts,
                retry_of=row.effect_id,
            )
            if ticket is None:
                row.state = "unknown"
                row.last_error_code = "EFFECT_CLAIM_REFUSED"
                row.lease_owner = None
                row.lease_until = None
                await db.commit()
                return None
            row.effect_id = ticket.id
            envelope = DeliveryEnvelope(
                claim.user_id,
                notice.message_id,
                claim.receipt_id,
                claim.destination_key,
                claim.device_id,
                notice.title,
                notice.body,
                token,
                language=notice.language,
            )
            await db.commit()
            return envelope, ticket
