"""Peers repository — pair-canonical queries + atomic lifecycle transitions.

Every pair lookup goes through ``canonical_pair`` before touching
``user_a_id``/``user_b_id`` — the UNIQUE(user_a, user_b) constraint is only
meaningful because no code path ever writes an unordered pair. Share upserts
are server-side atomic (``ON CONFLICT DO UPDATE`` on the named constraint —
health_metrics precedent); the repository never commits (sessions belong to
the service/router layer — open_loops doctrine).
"""

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.peers.models import (
    PeerAccessLog,
    PeerBlock,
    PeerConnection,
    PeerConnectionStatus,
    PeerDomainShare,
    PeerMessage,
    PeerMessageStatus,
    canonical_pair,
)

logger = structlog.get_logger(__name__)


def utc_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Return the [start, end) bounds of the UTC calendar day containing ``now``.

    Args:
        now: Timezone-aware UTC datetime.

    Returns:
        Tuple of (day start, next day start), both timezone-aware UTC.
    """
    start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


class PeersRepository(BaseRepository[PeerConnection]):
    """Repository for peer connections, blocks, shares, messages and audit."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, PeerConnection)

    # ------------------------------------------------------------------
    # Connections (one row per pair — transitions, never duplicates)
    # ------------------------------------------------------------------

    async def get_pair(self, u1: UUID, u2: UUID) -> PeerConnection | None:
        """Fetch the single pair row for two users, whatever the order given.

        Args:
            u1: One side of the pair.
            u2: The other side.

        Returns:
            The pair row or None.
        """
        user_a, user_b = canonical_pair(u1, u2)
        stmt = select(PeerConnection).where(
            PeerConnection.user_a_id == user_a,
            PeerConnection.user_b_id == user_b,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_fresh(self, connection_id: UUID) -> PeerConnection | None:
        """Re-SELECT a pair row bypassing stale identity-map attributes.

        Conditional UPDATEs below bypass the ORM; a previously loaded instance
        would otherwise be returned with its pre-transition attributes.
        """
        stmt = (
            select(PeerConnection)
            .where(PeerConnection.id == connection_id)
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def insert_pair_request(
        self,
        requester_id: UUID,
        addressee_id: UUID,
        context_message: str | None,
        *,
        now: datetime,
    ) -> PeerConnection:
        """INSERT a new canonical pending pair row.

        Raises ``IntegrityError`` when a concurrent request created the pair
        first — the service re-dispatches its state machine once (spec §13,
        pair uniqueness under concurrent requests belongs to the DB).

        Args:
            requester_id: Initiating user.
            addressee_id: Target user.
            context_message: Optional note shown to the addressee.
            now: Timezone-aware UTC request instant.

        Returns:
            The pending pair row.
        """
        user_a, user_b = canonical_pair(requester_id, addressee_id)
        connection = PeerConnection(
            user_a_id=user_a,
            user_b_id=user_b,
            requested_by_id=requester_id,
            status=PeerConnectionStatus.PENDING.value,
            context_message=context_message,
            requested_at=now,
        )
        self.db.add(connection)
        await self.db.flush()
        return connection

    async def revive_request(
        self,
        connection_id: UUID,
        requester_id: UUID,
        context_message: str | None,
        *,
        now: datetime,
    ) -> PeerConnection | None:
        """Conditionally revive a ``declined``/``removed`` row back to pending.

        Server-side conditional UPDATE (open_loops doctrine — never
        SELECT → mutate → flush): the revival claims the row exactly once,
        whatever the concurrency.

        Args:
            connection_id: Pair row id.
            requester_id: New requesting side.
            context_message: Optional note shown to the addressee.
            now: Timezone-aware UTC request instant.

        Returns:
            The fresh pending row, or None when the row was not in a
            revivable status (concurrent change — caller re-dispatches).
        """
        stmt = (
            update(PeerConnection)
            .where(
                PeerConnection.id == connection_id,
                PeerConnection.status.in_(
                    (
                        PeerConnectionStatus.DECLINED.value,
                        PeerConnectionStatus.REMOVED.value,
                    )
                ),
            )
            .values(
                status=PeerConnectionStatus.PENDING.value,
                requested_by_id=requester_id,
                context_message=context_message,
                requested_at=now,
                responded_at=None,
                removed_at=None,
            )
        )
        result = await self.db.execute(stmt)
        if not getattr(result, "rowcount", 0):
            return None
        return await self._get_fresh(connection_id)

    async def transition_status(
        self,
        connection_id: UUID,
        new_status: PeerConnectionStatus,
        *,
        expected_from: tuple[str, ...],
        now: datetime,
    ) -> PeerConnection | None:
        """Atomically transition a pair row, claiming it exactly once.

        Server-side conditional UPDATE (open_loops doctrine): the transition
        only applies while the row is still in one of ``expected_from`` —
        two concurrent responders cannot both win.

        Args:
            connection_id: Pair row id.
            new_status: Target status.
            expected_from: Statuses the row must currently be in.
            now: Timezone-aware UTC timestamp to stamp.

        Returns:
            The fresh row after the transition, or None when the row was not
            claimed (concurrent change — caller decides how to answer).
        """
        values: dict[str, object] = {"status": new_status.value}
        if new_status in (PeerConnectionStatus.ACCEPTED, PeerConnectionStatus.DECLINED):
            values["responded_at"] = now
        elif new_status is PeerConnectionStatus.REMOVED:
            values["removed_at"] = now
        stmt = (
            update(PeerConnection)
            .where(
                PeerConnection.id == connection_id,
                PeerConnection.status.in_(expected_from),
            )
            .values(**values)
        )
        result = await self.db.execute(stmt)
        if not getattr(result, "rowcount", 0):
            return None
        return await self._get_fresh(connection_id)

    async def list_pending_for_user(self, user_id: UUID) -> list[PeerConnection]:
        """List pending requests where the user sits on either side.

        Args:
            user_id: The user.

        Returns:
            Pending pair rows, newest request first.
        """
        stmt = (
            select(PeerConnection)
            .where(
                PeerConnection.status == PeerConnectionStatus.PENDING.value,
                or_(
                    PeerConnection.user_a_id == user_id,
                    PeerConnection.user_b_id == user_id,
                ),
            )
            .order_by(PeerConnection.requested_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_accepted_for_user(self, user_id: UUID) -> list[PeerConnection]:
        """List accepted connections for a user, most recent response first.

        Args:
            user_id: The user.

        Returns:
            Accepted pair rows.
        """
        stmt = (
            select(PeerConnection)
            .where(
                PeerConnection.status == PeerConnectionStatus.ACCEPTED.value,
                or_(
                    PeerConnection.user_a_id == user_id,
                    PeerConnection.user_b_id == user_id,
                ),
            )
            .order_by(PeerConnection.responded_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def expire_stale_pending(self, older_than: datetime) -> int:
        """Silently expire pending requests older than the given instant.

        Args:
            older_than: Requests requested before this UTC instant expire.

        Returns:
            Number of rows transitioned to removed.
        """
        stmt = (
            update(PeerConnection)
            .where(
                PeerConnection.status == PeerConnectionStatus.PENDING.value,
                PeerConnection.requested_at < older_than,
            )
            .values(
                status=PeerConnectionStatus.REMOVED.value,
                removed_at=datetime.now(UTC),
            )
        )
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    # ------------------------------------------------------------------
    # Blocks (directional, independent of connections)
    # ------------------------------------------------------------------

    async def has_block_between(self, u1: UUID, u2: UUID) -> bool:
        """Whether a block exists in EITHER direction between two users.

        Args:
            u1: One user.
            u2: The other user.

        Returns:
            True if either has blocked the other.
        """
        stmt = select(
            exists().where(
                or_(
                    (PeerBlock.blocker_id == u1) & (PeerBlock.blocked_id == u2),
                    (PeerBlock.blocker_id == u2) & (PeerBlock.blocked_id == u1),
                )
            )
        )
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def create_block(self, blocker_id: UUID, blocked_id: UUID) -> PeerBlock:
        """Place a directional block (idempotent on the UNIQUE pair).

        Args:
            blocker_id: User placing the block.
            blocked_id: User being blocked.

        Returns:
            The block row (existing one if already placed).
        """
        stmt = select(PeerBlock).where(
            PeerBlock.blocker_id == blocker_id,
            PeerBlock.blocked_id == blocked_id,
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing
        block = PeerBlock(blocker_id=blocker_id, blocked_id=blocked_id)
        self.db.add(block)
        await self.db.flush()
        return block

    async def delete_block(self, blocker_id: UUID, blocked_id: UUID) -> bool:
        """Remove a directional block.

        Args:
            blocker_id: User who placed the block.
            blocked_id: User who was blocked.

        Returns:
            True if a block row was deleted.
        """
        stmt = delete(PeerBlock).where(
            PeerBlock.blocker_id == blocker_id,
            PeerBlock.blocked_id == blocked_id,
        )
        result = await self.db.execute(stmt)
        return bool(getattr(result, "rowcount", 0))

    async def list_blocks(self, blocker_id: UUID) -> list[PeerBlock]:
        """List blocks placed BY a user (never who blocked them — spec §12.2).

        Args:
            blocker_id: The blocker.

        Returns:
            Block rows, newest first.
        """
        stmt = (
            select(PeerBlock)
            .where(PeerBlock.blocker_id == blocker_id)
            .order_by(PeerBlock.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Domain shares (absence of row = not shared)
    # ------------------------------------------------------------------

    async def upsert_share(
        self,
        connection_id: UUID,
        owner_user_id: UUID,
        domain: str,
        level: str,
    ) -> None:
        """Atomically create or update one share level (never SELECT → mutate).

        Args:
            connection_id: Connection the share belongs to.
            owner_user_id: Side of the pair sharing its data.
            domain: PeerShareDomain value.
            level: PeerShareLevel value.
        """
        now = datetime.now(UTC)
        stmt = pg_insert(PeerDomainShare).values(
            id=uuid.uuid4(),
            connection_id=connection_id,
            owner_user_id=owner_user_id,
            domain=domain,
            level=level,
            created_at=now,
            updated_at=now,
        )
        upsert = stmt.on_conflict_do_update(
            constraint="uq_peer_domain_shares_owner_domain",
            set_={"level": stmt.excluded.level, "updated_at": func.now()},
        )
        await self.db.execute(upsert)

    async def delete_share(
        self,
        connection_id: UUID,
        owner_user_id: UUID,
        domain: str,
    ) -> bool:
        """Remove one share (back to the default not-shared state).

        Args:
            connection_id: Connection the share belongs to.
            owner_user_id: Owner side.
            domain: PeerShareDomain value.

        Returns:
            True if a share row was deleted.
        """
        stmt = delete(PeerDomainShare).where(
            PeerDomainShare.connection_id == connection_id,
            PeerDomainShare.owner_user_id == owner_user_id,
            PeerDomainShare.domain == domain,
        )
        result = await self.db.execute(stmt)
        return bool(getattr(result, "rowcount", 0))

    async def delete_shares_for_connection(self, connection_id: UUID) -> int:
        """Remove every share on a connection (removal/block severs sharing).

        Args:
            connection_id: The connection.

        Returns:
            Number of share rows deleted.
        """
        stmt = delete(PeerDomainShare).where(PeerDomainShare.connection_id == connection_id)
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def list_shares(self, connection_id: UUID) -> list[PeerDomainShare]:
        """List every share on a connection (both owners — spec both-directions).

        Args:
            connection_id: The connection.

        Returns:
            Share rows.
        """
        stmt = select(PeerDomainShare).where(PeerDomainShare.connection_id == connection_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Messages (delivery ledger — Lot 4 consumes the pending queue)
    # ------------------------------------------------------------------

    async def count_messages_today(self, sender_id: UUID, *, now: datetime) -> int:
        """Count messages a sender enqueued during the current UTC day.

        Args:
            sender_id: The sender.
            now: Timezone-aware UTC reference instant.

        Returns:
            Number of messages (all statuses — enqueuing is what is quota'd).
        """
        start, end = utc_day_bounds(now)
        stmt = select(func.count(PeerMessage.id)).where(
            PeerMessage.sender_id == sender_id,
            PeerMessage.created_at >= start,
            PeerMessage.created_at < end,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def count_messages_today_for_pair(
        self,
        sender_id: UUID,
        recipient_id: UUID,
        *,
        now: datetime,
    ) -> int:
        """Count messages a sender enqueued toward one recipient today (UTC).

        Args:
            sender_id: The sender.
            recipient_id: The recipient.
            now: Timezone-aware UTC reference instant.

        Returns:
            Number of messages.
        """
        start, end = utc_day_bounds(now)
        stmt = select(func.count(PeerMessage.id)).where(
            PeerMessage.sender_id == sender_id,
            PeerMessage.recipient_id == recipient_id,
            PeerMessage.created_at >= start,
            PeerMessage.created_at < end,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def claim_pending_messages(self, limit: int = 10) -> list[PeerMessage]:
        """Claim pending messages for delivery, exactly once per row.

        ``FOR UPDATE SKIP LOCKED`` + transition to ``delivering`` in the same
        transaction (scheduled_actions doctrine) — two sweep instances never
        deliver the same message.

        Args:
            limit: Max rows claimed per sweep tick.

        Returns:
            Claimed rows, oldest first, already transitioned to delivering.
        """
        stmt = (
            select(PeerMessage)
            .where(PeerMessage.status == PeerMessageStatus.PENDING.value)
            .order_by(PeerMessage.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())
        for message in messages:
            message.status = PeerMessageStatus.DELIVERING.value
        await self.db.flush()
        return messages

    async def mark_message_delivered(self, message_id: UUID, *, now: datetime) -> bool:
        """Finish a delivery: delivered + content scrubbed (spec §8.4).

        Conditional on the ``delivering`` claim — a concurrent transition
        (crash recovery racing the finish) loses cleanly.

        Args:
            message_id: The message.
            now: Timezone-aware UTC delivery instant.

        Returns:
            True when this call performed the transition.
        """
        stmt = (
            update(PeerMessage)
            .where(
                PeerMessage.id == message_id,
                PeerMessage.status == PeerMessageStatus.DELIVERING.value,
            )
            .values(
                status=PeerMessageStatus.DELIVERED.value,
                delivered_at=now,
                content=None,
                last_error=None,
            )
        )
        result = await self.db.execute(stmt)
        return bool(getattr(result, "rowcount", 0))

    async def mark_message_failed(
        self,
        message_id: UUID,
        error_code: str,
        *,
        max_attempts: int,
    ) -> str:
        """Record one REAL delivery failure (deferrals never call this).

        attempts+1; below the cap the message returns to ``pending`` for the
        next sweep, at the cap it becomes ``failed`` (sender then notified).

        Args:
            message_id: The message.
            error_code: Typed code — never raw exception text (spec §12.5).
            max_attempts: settings.peers_delivery_max_attempts.

        Returns:
            The resulting status value ("pending" or "failed").
        """
        message = await self.db.get(PeerMessage, message_id)
        if message is None:  # purged concurrently — nothing to record
            return PeerMessageStatus.FAILED.value
        attempts = message.attempts + 1
        target = (
            PeerMessageStatus.FAILED.value
            if attempts >= max_attempts
            else PeerMessageStatus.PENDING.value
        )
        stmt = (
            update(PeerMessage)
            .where(
                PeerMessage.id == message_id,
                PeerMessage.status == PeerMessageStatus.DELIVERING.value,
            )
            .values(attempts=attempts, status=target, last_error=error_code[:50])
        )
        await self.db.execute(stmt)
        return target

    async def cancel_message(self, message_id: UUID, error_code: str) -> None:
        """Cancel a claimed message (revalidation failed — block/removal/inactive).

        Args:
            message_id: The message.
            error_code: Typed reason code.
        """
        stmt = (
            update(PeerMessage)
            .where(
                PeerMessage.id == message_id,
                PeerMessage.status == PeerMessageStatus.DELIVERING.value,
            )
            .values(
                status=PeerMessageStatus.CANCELLED.value,
                content=None,
                last_error=error_code[:50],
            )
        )
        await self.db.execute(stmt)

    async def recover_stale_delivering(self, *, older_than: datetime) -> int:
        """Return crash-stranded ``delivering`` rows to ``pending``.

        Args:
            older_than: Claims updated before this UTC instant are stale.

        Returns:
            Number of rows recovered.
        """
        stmt = (
            update(PeerMessage)
            .where(
                PeerMessage.status == PeerMessageStatus.DELIVERING.value,
                PeerMessage.updated_at < older_than,
            )
            .values(status=PeerMessageStatus.PENDING.value)
        )
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def enqueue_message(
        self,
        connection_id: UUID,
        sender_id: UUID,
        recipient_id: UUID,
        content: str,
    ) -> PeerMessage:
        """Persist a pending relayed message (delivery is Lot 4's sweep).

        Args:
            connection_id: Connection the message travels on.
            sender_id: Sender (pays the LLM cost — spec A4).
            recipient_id: Recipient.
            content: Sender directive text (scrubbed after delivery).

        Returns:
            The pending message row.
        """
        message = PeerMessage(
            connection_id=connection_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            status=PeerMessageStatus.PENDING.value,
        )
        self.db.add(message)
        await self.db.flush()
        return message

    # ------------------------------------------------------------------
    # Access log (immutable audit + owner transparency)
    # ------------------------------------------------------------------

    async def log_access(
        self,
        accessor_id: UUID,
        owner_id: UUID,
        connection_id: UUID | None,
        domain: str,
        tool_name: str,
    ) -> None:
        """Record one cross-user read (immutable — AdminAuditLog pattern).

        Args:
            accessor_id: User whose assistant performed the read.
            owner_id: User whose data was read.
            connection_id: Connection the share was checked on.
            domain: PeerShareDomain value.
            tool_name: Reading tool name.
        """
        self.db.add(
            PeerAccessLog(
                accessor_id=accessor_id,
                owner_id=owner_id,
                connection_id=connection_id,
                domain=domain,
                tool_name=tool_name,
            )
        )
        await self.db.flush()

    async def list_access_log_for_owner(
        self,
        owner_id: UUID,
        limit: int = 50,
    ) -> list[PeerAccessLog]:
        """List reads OF the owner's data, newest first (transparency view).

        Args:
            owner_id: Data owner.
            limit: Cap on returned rows.

        Returns:
            Audit rows.
        """
        stmt = (
            select(PeerAccessLog)
            .where(PeerAccessLog.owner_id == owner_id)
            .order_by(PeerAccessLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def prune_access_log(self, older_than: datetime) -> int:
        """Delete audit rows older than the retention horizon (Lot 5 sweep).

        Args:
            older_than: Rows created before this UTC instant are pruned.

        Returns:
            Number of rows deleted.
        """
        stmt = delete(PeerAccessLog).where(PeerAccessLog.created_at < older_than)
        result = await self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)
