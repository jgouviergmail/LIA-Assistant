"""Short SQL transactions fence a bounded fair queue; none spans provider I/O."""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import case, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.repository import UserRepository
from src.domains.world.message_models import WorldMessageAttempt as Record
from src.infrastructure.database.session import get_db_context

TRANSLATION_SECONDS = 8
QUEUE_SECONDS = 20
ATTEMPT_SECONDS = 15
PAID_PARALLEL = 2
PAID_WAITING = 5
TOMBSTONE_DAYS = 2


class AttemptBusy(ValueError):
    """Bounded waiting is full, or this payer already owns pending work."""


class AttemptConflict(ValueError):
    """An id was already used with a different owned request."""


class MessageAttempts:
    def __init__(self, namespace: str) -> None:
        """Bind durable content-free translation fences to the exact message namespace."""
        self.namespace = namespace

    async def _lock(self, db: AsyncSession, now: datetime) -> None:
        """Serialize queue decisions with a namespace advisory lock and reconcile expired attempts."""
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": "world_messages:" + self.namespace},
        )
        await db.execute(
            update(Record)
            .where(
                Record.namespace == self.namespace,
                Record.status == "running",
                Record.running_until <= now,
            )
            .values(status="uncertain", updated_at=now)
        )
        await db.execute(
            update(Record)
            .where(
                Record.namespace == self.namespace,
                Record.status == "queued",
                Record.queued_until <= now,
            )
            .values(status="failed", updated_at=now)
        )

    async def replay(
        self, message: UUID, sender: UUID, recipient: UUID, fingerprint: str
    ) -> Record | None:
        """Read the matching owned request fence without creating or retrying an effect."""
        async with get_db_context() as db:
            row = await db.get(Record, message)
            if row is None:
                return None
            if (row.namespace, row.user_id, row.recipient_id, row.fingerprint) != (
                self.namespace,
                sender,
                recipient,
                fingerprint,
            ):
                raise AttemptConflict("world_message_conflict")
            return row

    async def enqueue(
        self,
        message: UUID,
        sender: UUID,
        recipient: UUID,
        fingerprint: str,
        *,
        translated: bool,
        now: datetime,
    ) -> tuple[Record, bool]:
        """Lock participants and reserve one immutable intent with bounded paid waiting capacity."""
        async with get_db_context() as db:
            # Native soft deletion keeps users rows, so an FK alone is insufficient.
            for owner in sorted({sender, recipient}):
                if await UserRepository(db).get_by_id_for_preference_update(owner) is None:
                    raise ValueError("world_message_unavailable")
            await self._lock(db, now)
            existing = await db.get(Record, message)
            if existing is not None:
                if (
                    existing.namespace,
                    existing.user_id,
                    existing.recipient_id,
                    existing.fingerprint,
                ) != (self.namespace, sender, recipient, fingerprint):
                    raise AttemptConflict("world_message_conflict")
                return existing, False
            if translated:
                pending = list(
                    (
                        await db.scalars(
                            select(Record.user_id)
                            .where(
                                Record.namespace == self.namespace,
                                Record.status.in_(["queued", "running"]),
                            )
                            .limit(PAID_WAITING + PAID_PARALLEL)
                        )
                    ).all()
                )
                if sender in pending or len(pending) >= PAID_WAITING:
                    raise AttemptBusy("world_message_busy")
            row = Record(
                id=message,
                user_id=sender,
                recipient_id=recipient,
                namespace=self.namespace,
                fingerprint=fingerprint,
                status="queued" if translated else "reserved",
                created_at=now,
                updated_at=now,
                queued_until=now + timedelta(seconds=QUEUE_SECONDS),
                expires_at=now + timedelta(days=TOMBSTONE_DAYS),
            )
            db.add(row)
            await db.flush()
            await self._purge_expired(db, now)
            return row, True

    async def _purge_expired(self, db: AsyncSession, now: datetime) -> None:
        # Retired scene/instance scopes must not retain tombstones forever.
        # Expiry is global; the indexed batch stays bounded and never touches
        # a live fence in another namespace.
        """Delete one indexed batch of expired tombstones across retired namespaces."""
        expired = (
            select(Record.id)
            .where(Record.expires_at <= now)
            .order_by(Record.expires_at, Record.id)
            .limit(100)
        )
        await db.execute(delete(Record).where(Record.id.in_(expired)))

    async def mark_ready(self, message: UUID, token: UUID, *, now: datetime) -> bool:
        """Only the creator, after acknowledged Redis staging, may dispatch."""
        async with get_db_context() as db:
            result = await db.execute(
                update(Record)
                .where(
                    Record.namespace == self.namespace,
                    Record.id == message,
                    Record.token == token,
                    Record.content_ready.is_(False),
                    Record.status.in_(["queued", "reserved"]),
                    Record.queued_until > now,
                )
                .values(
                    content_ready=True,
                    updated_at=now,
                    status=case((Record.status == "reserved", "delivered"), else_=Record.status),
                )
                .returning(Record.id)
            )
            return result.scalar_one_or_none() is not None

    async def mark_cached(self, message: UUID, token: UUID, *, now: datetime) -> bool:
        """An acknowledged authorized variant wins a dispatch race without spend."""
        async with get_db_context() as db:
            result = await db.execute(
                update(Record)
                .where(
                    Record.namespace == self.namespace,
                    Record.id == message,
                    Record.token == token,
                    Record.status.in_(["queued", "reserved"]),
                    Record.content_ready.is_(False),
                    Record.queued_until > now,
                )
                .values(status="delivered", content_ready=True, updated_at=now)
                .returning(Record.id)
            )
            return result.scalar_one_or_none() is not None

    async def start(self, message: UUID, token: UUID, *, now: datetime) -> bool:
        """Claim an acknowledged queued attempt in FIFO order under the paid concurrency limit."""
        async with get_db_context() as db:
            await self._lock(db, now)
            pending = list(
                (
                    await db.scalars(
                        select(Record)
                        .where(
                            Record.namespace == self.namespace,
                            Record.status.in_(["queued", "running"]),
                        )
                        .order_by(Record.created_at, Record.id)
                        .limit(PAID_WAITING + PAID_PARALLEL)
                    )
                ).all()
            )
            slots = PAID_PARALLEL - sum(row.status == "running" for row in pending)
            eligible = [row for row in pending if row.status == "queued"][: max(0, slots)]
            row = next(
                (
                    row
                    for row in eligible
                    if row.id == message and row.token == token and row.content_ready
                ),
                None,
            )
            if row is None:
                return False
            row.status, row.updated_at = "running", now
            row.running_until = now + timedelta(seconds=ATTEMPT_SECONDS)
            return True

    async def finish(
        self,
        message: UUID,
        token: UUID,
        status: Literal["succeeded", "failed", "uncertain"],
        *,
        now: datetime,
    ) -> bool:
        """Close owned paid execution; success alone never acknowledges Redis publication."""
        async with get_db_context() as db:
            result = await db.execute(
                update(Record)
                .where(
                    Record.namespace == self.namespace,
                    Record.id == message,
                    Record.token == token,
                    Record.status == "running",
                    Record.running_until > now,
                )
                .values(status=status, updated_at=now)
                .returning(Record.id)
            )
            return result.scalar_one_or_none() is not None

    async def mark_delivered(self, message: UUID, token: UUID, *, now: datetime) -> bool:
        """Acknowledge publication only for this token's completed, unexpired paid execution."""
        async with get_db_context() as db:
            result = await db.execute(
                update(Record)
                .where(
                    Record.namespace == self.namespace,
                    Record.id == message,
                    Record.token == token,
                    Record.status == "succeeded",
                    Record.content_ready.is_(True),
                    Record.expires_at > now,
                )
                .values(status="delivered", updated_at=now)
                .returning(Record.id)
            )
            return result.scalar_one_or_none() is not None

    async def status(self, message: UUID, token: UUID, *, now: datetime) -> str | None:
        """Project durable attempt state; expired or unacknowledged work remains uncertain."""
        async with get_db_context() as db:
            row = await db.get(Record, message)
            if row is None or row.namespace != self.namespace or row.token != token:
                return None
            if not row.content_ready or row.status == "succeeded":
                return "uncertain"
            if row.status == "queued" and row.queued_until <= now:
                return "failed"
            if row.status == "running" and (row.running_until is None or row.running_until <= now):
                return "uncertain"
            return row.status

    async def owned_status(
        self, message: UUID, owner: UUID, *, now: datetime
    ) -> Literal["delivered", "pending", "uncertain"] | None:
        """Read a request outcome only for its owning payer and namespace."""
        async with get_db_context() as db:
            row = await db.scalar(
                select(Record).where(
                    Record.id == message,
                    Record.namespace == self.namespace,
                    Record.user_id == owner,
                    Record.expires_at > now,
                )
            )
            if row is None:
                return None
            if not row.content_ready or row.status in {
                "reserved",
                "succeeded",
                "failed",
                "uncertain",
            }:
                return "uncertain"
            if row.status == "queued" and row.queued_until <= now:
                return "uncertain"
            if row.status == "running" and (row.running_until is None or row.running_until <= now):
                return "uncertain"
            return "delivered" if row.status == "delivered" else "pending"
