"""Fenced peer delivery claims and atomic, conditional state transitions.

The message UUID is the durable delivery key. Every writer also supplies its
unique owner token and monotonically increasing generation; a lost lease may
neither renew nor change a row. Sessions are owned and committed by callers.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.config import settings
from src.core.repository import BaseRepository
from src.core.security.utils import encrypt_data
from src.domains.peers.models import PeerMessage


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    """Immutable identity retained even when an ORM row is later refreshed."""

    message_id: UUID
    owner: UUID
    generation: int


class DeliveryLeaseLost(RuntimeError):
    """The worker must stop all later effects after losing authority."""


def claim_of(message: PeerMessage) -> DeliveryClaim:
    """Capture the acquired authority without retaining mutable ORM state."""
    if message.claim_token is None:
        raise DeliveryLeaseLost("No peer delivery claim")
    return DeliveryClaim(message.id, message.claim_token, message.claim_generation)


def _owned(claim: DeliveryClaim) -> ColumnElement[bool]:
    return and_(
        PeerMessage.id == claim.message_id,
        PeerMessage.status == "delivering",
        PeerMessage.claim_token == claim.owner,
        PeerMessage.claim_generation == claim.generation,
        PeerMessage.lease_expires_at > func.clock_timestamp(),
    )


class PeerDeliveryRepository(BaseRepository[PeerMessage]):
    """One owner for delivery claims, generation checkpoints and settlements."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, PeerMessage)

    async def claim_pending_messages(
        self, limit: int = 1, *, exclude: tuple[UUID, ...] = ()
    ) -> list[PeerMessage]:
        """Claim an ordered bounded prefix; the caller commits before any wait."""
        ids = list(
            (
                await self.db.scalars(
                    select(PeerMessage.id)
                    .where(PeerMessage.status == "pending", PeerMessage.id.not_in(exclude))
                    .order_by(PeerMessage.created_at, PeerMessage.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        claimed: list[PeerMessage] = []
        for message_id in ids:
            row = await self.db.scalar(
                update(PeerMessage)
                .where(PeerMessage.id == message_id)
                .values(
                    status="delivering",
                    claim_token=uuid4(),
                    claim_generation=PeerMessage.claim_generation + 1,
                    lease_expires_at=func.clock_timestamp()
                    + timedelta(seconds=settings.peers_delivery_lease_seconds),
                )
                .returning(PeerMessage)
                .execution_options(populate_existing=True)
            )
            if row is not None:
                claimed.append(row)
        return claimed

    async def _change(self, claim: DeliveryClaim, values: dict[str, object]) -> bool:
        result = await self.db.scalar(
            update(PeerMessage).where(_owned(claim)).values(**values).returning(PeerMessage.id)
        )
        return result is not None

    async def lock_owned(self, claim: DeliveryClaim) -> PeerMessage | None:
        """Fence an atomic archive/settle transaction; no network waits inside."""
        result = await self.db.scalars(
            select(PeerMessage)
            .where(_owned(claim))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.one_or_none()

    async def renew(self, claim: DeliveryClaim) -> bool:
        """Only a live owner may extend its lease; expiry cannot be undone."""
        return await self._change(
            claim,
            {
                "lease_expires_at": func.clock_timestamp()
                + timedelta(seconds=settings.peers_delivery_lease_seconds)
            },
        )

    async def start_generation(self, claim: DeliveryClaim) -> bool:
        """Persist the possibility of spend before sending a model request."""
        result = await self.db.scalar(
            update(PeerMessage)
            .where(
                _owned(claim),
                PeerMessage.generation_started.is_(False),
                PeerMessage.prepared_text_encrypted.is_(None),
                or_(
                    PeerMessage.expires_at.is_(None),
                    PeerMessage.expires_at > func.clock_timestamp(),
                ),
            )
            .values(generation_started=True)
            .returning(PeerMessage.id)
        )
        return result is not None

    async def store_prepared(self, claim: DeliveryClaim, text: str) -> bool:
        """Keep the rendition for dispatch retries without purchasing it again."""
        result = await self.db.scalar(
            update(PeerMessage)
            .where(
                _owned(claim),
                PeerMessage.generation_started.is_(True),
                PeerMessage.prepared_text_encrypted.is_(None),
                or_(
                    PeerMessage.expires_at.is_(None),
                    PeerMessage.expires_at > func.clock_timestamp(),
                ),
            )
            .values(prepared_text_encrypted=encrypt_data(text))
            .returning(PeerMessage.id)
        )
        return result is not None

    async def mark_message_delivered(
        self, claim: DeliveryClaim, *, now: datetime, delivered_text: str
    ) -> bool:
        """Settle in the SAME transaction that archives the notification."""
        return await self._change(
            claim,
            {
                "status": "delivered",
                "delivered_at": now,
                "delivered_text": delivered_text,
                "prepared_text_encrypted": None,
                "last_error": None,
                "claim_token": None,
                "lease_expires_at": None,
            },
        )

    async def mark_message_failed(
        self, claim: DeliveryClaim, error_code: str, *, max_attempts: int, retryable: bool = True
    ) -> str | None:
        """Count one failure atomically; a stale owner has no resulting status."""
        terminal = (PeerMessage.attempts + 1 >= max_attempts) if retryable else true()
        return await self.db.scalar(
            update(PeerMessage)
            .where(_owned(claim))
            .values(
                attempts=PeerMessage.attempts + 1,
                status=case((terminal, "failed"), else_="pending"),
                last_error=error_code,
                claim_token=None,
                lease_expires_at=None,
                generation_started=False,
            )
            .returning(PeerMessage.status)
        )

    async def cancel_message(self, claim: DeliveryClaim, error_code: str) -> bool:
        """Cancel only this owner's claim, preserving the sender's retention."""
        return await self._change(
            claim,
            {
                "status": "cancelled",
                "last_error": error_code,
                "claim_token": None,
                "lease_expires_at": None,
                "prepared_text_encrypted": None,
            },
        )

    async def recover_stale_delivering(self) -> int:
        """Recover safe checkpoints; an unrecorded model outcome is terminal."""
        unknown = and_(
            PeerMessage.generation_started.is_(True), PeerMessage.prepared_text_encrypted.is_(None)
        )
        result = await self.db.execute(
            update(PeerMessage)
            .where(
                PeerMessage.status == "delivering",
                PeerMessage.lease_expires_at <= func.clock_timestamp(),
            )
            .values(
                status=case((unknown, "failed"), else_="pending"),
                last_error=case(
                    (unknown, "generation_outcome_unknown"), else_=PeerMessage.last_error
                ),
                claim_token=None,
                lease_expires_at=None,
            )
            .returning(PeerMessage.id)
        )
        return len(result.all())
