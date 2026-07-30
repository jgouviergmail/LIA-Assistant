"""Peers service — discovery search and connection lifecycle guards (Lot 1).

Guard doctrine (spec §5, §12.2): anything a stranger could probe answers with
the SAME neutral 404 (``raise_not_found_or_unauthorized("peer", …)``) — an
unknown user, a blocked pair, a cooldown window and a non-participant
connection id are indistinguishable by construction. State-changing methods
append a :class:`PeerEvent` to ``pending_events``; Lot 3 turns those into
chat notifications (no notification concern lives here).

Logging: ids and counters only at INFO — never names, emails or note content.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.constants import PEERS_CONTEXT_MESSAGE_MAX_CHARS
from src.core.exceptions import raise_invalid_input, raise_not_found_or_unauthorized
from src.domains.peers.discovery import mask_email
from src.domains.peers.models import (
    PeerConnection,
    PeerConnectionStatus,
    PeerShareDomain,
    PeerShareLevel,
)
from src.domains.peers.repository import PeersRepository
from src.domains.peers.schemas import (
    AccessLogEntry,
    BlockView,
    ConnectionStateView,
    ConnectionView,
    DiscoveryMatch,
    PeerEvent,
    ShareItem,
)
from src.domains.shared.text_normalization import fold_name
from src.domains.users.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Discovery-result relationship annotation (Lot 7): only statuses the searcher
# already knows about are surfaced — DECLINED/REMOVED map to the absent key
# and read "none" (indistinguishable from no history, spec §12.2).
_DISCOVERY_RELATIONSHIP: dict[str, Literal["pending", "connected"]] = {
    PeerConnectionStatus.PENDING.value: "pending",
    PeerConnectionStatus.ACCEPTED.value: "connected",
}

# v1 share matrix (spec A1): which levels each domain admits.
_VALID_SHARE_LEVELS: dict[str, frozenset[str]] = {
    PeerShareDomain.CALENDAR.value: frozenset(
        {PeerShareLevel.AVAILABILITY.value, PeerShareLevel.DETAILS.value}
    ),
    PeerShareDomain.TASK.value: frozenset({PeerShareLevel.TITLES.value}),
}


class PeersService:
    """Discovery, connection lifecycle, blocks and shares (spec §4-§5)."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the session and create the repository (service-layer pattern).

        Args:
            db: Request-scoped async session (router owns the transaction).
        """
        self.db = db
        self.repo = PeersRepository(db)
        self.pending_events: list[PeerEvent] = []

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    async def get_discovery_state(self, user_id: UUID) -> bool:
        """Return the caller's discovery opt-in.

        Args:
            user_id: The caller.

        Returns:
            Current ``discovery_enabled`` value.
        """
        user = await self.db.get(User, user_id)
        return bool(user is not None and user.discovery_enabled)

    async def set_discovery(self, user_id: UUID, enabled: bool) -> None:
        """Toggle the caller's discovery opt-in.

        Args:
            user_id: The caller.
            enabled: New opt-in value.
        """
        user = await self.db.get(User, user_id)
        if user is None:  # defensive — the session dependency already resolved them
            raise_not_found_or_unauthorized("peer", user_id)
        user.discovery_enabled = enabled
        await self.db.flush()
        logger.info("peers_discovery_toggled", user_id=str(user_id), enabled=enabled)

    async def search_discoverable(self, searcher_id: UUID, full_name: str) -> list[DiscoveryMatch]:
        """Exact folded-name search over opted-in active users (spec §5.1).

        O(N) scan over discoverable users with Python-side folding: the folding
        is NFKD-based and has no portable SQL equivalent, and a self-hosted
        instance holds tens of users, not millions (documented trade-off). No
        prefix or substring matching, ever (anti-enumeration).

        Args:
            searcher_id: The caller (excluded from results).
            full_name: Name to match exactly after folding.

        Returns:
            Matches with the A6 masked email hint; empty for blank queries.
        """
        folded = fold_name(full_name)
        if not folded:
            return []
        stmt = select(User.id, User.full_name, User.email).where(
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.discovery_enabled.is_(True),
            User.full_name.is_not(None),
            User.id != searcher_id,
        )
        rows = (await self.db.execute(stmt)).all()
        matches: list[DiscoveryMatch] = []
        for user_id, name, email in rows:
            if fold_name(name) != folded:
                continue
            if await self.repo.has_block_between(searcher_id, user_id):
                continue  # indistinguishable from no-match (spec §12.2)
            pair = await self.repo.get_pair(searcher_id, user_id)
            relationship = _DISCOVERY_RELATIONSHIP.get(pair.status if pair else "", "none")
            matches.append(
                DiscoveryMatch(
                    peer_id=user_id,
                    display_name=name,
                    email_hint=mask_email(email),
                    relationship=relationship,
                )
            )
        logger.info(
            "peers_discovery_search",
            searcher_id=str(searcher_id),
            matches=len(matches),
        )
        return matches

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def _get_discoverable_user(self, user_id: UUID) -> User | None:
        """Load a user only if they are active, non-deleted and opted-in.

        Args:
            user_id: Target user id.

        Returns:
            The user row, or None when not discoverable (caller answers 404).
        """
        stmt = select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            User.discovery_enabled.is_(True),
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    def _emit(self, kind: str, connection: PeerConnection, actor_id: UUID) -> None:
        """Append a lifecycle event for Lot 3's notification dispatch."""
        self.pending_events.append(
            PeerEvent(
                kind=kind,
                connection_id=connection.id,
                actor_id=actor_id,
                affected_ids=(connection.user_a_id, connection.user_b_id),
            )
        )

    def _declined_cooldown_active(
        self, connection: PeerConnection, requester_id: UUID, now: datetime
    ) -> bool:
        """Whether the decline cooldown blocks this requester (spec §5.2).

        The cooldown protects the DECLINER from nagging: it only applies when
        the requester is the side whose request was declined. The decliner
        changing their mind may re-request immediately.
        """
        if connection.status != PeerConnectionStatus.DECLINED.value:
            return False
        if connection.requested_by_id != requester_id:
            return False
        if connection.responded_at is None:
            return False
        horizon = connection.responded_at + timedelta(days=settings.peers_request_cooldown_days)
        return now < horizon

    async def request_connection(
        self,
        requester_id: UUID,
        addressee_id: UUID,
        context_message: str | None,
        *,
        _retry_allowed: bool = True,
    ) -> ConnectionStateView:
        """Create (or revive) a connection request with every guard (spec §5.2).

        Concurrency: every state change is a claim (conditional UPDATE or the
        pair UNIQUE). When a claim is lost to a concurrent request, the whole
        state machine re-dispatches exactly once against the fresh state — a
        crossing request that beat us by milliseconds then lands in the
        auto-accept branch instead of a 500.

        Args:
            requester_id: Initiating user.
            addressee_id: Target user (from a discovery search).
            context_message: Optional note for the addressee.
            _retry_allowed: Internal re-dispatch budget (single retry).

        Returns:
            Minimal state view (pending, or accepted on crossing requests).
        """
        if requester_id == addressee_id:
            raise_invalid_input("peers_self_request")
        if context_message is not None and len(context_message) > PEERS_CONTEXT_MESSAGE_MAX_CHARS:
            raise_invalid_input("peers_context_message_too_long")

        addressee = await self._get_discoverable_user(addressee_id)
        if addressee is None or await self.repo.has_block_between(requester_id, addressee_id):
            raise_not_found_or_unauthorized("peer", addressee_id)

        now = datetime.now(UTC)
        existing = await self.repo.get_pair(requester_id, addressee_id)
        if existing is not None:
            if existing.status == PeerConnectionStatus.ACCEPTED.value:
                raise_invalid_input("peers_already_connected")
            if existing.status == PeerConnectionStatus.PENDING.value:
                if existing.requested_by_id == requester_id:
                    # Idempotent: same request again is a no-op.
                    return ConnectionStateView(id=existing.id, status=existing.status)
                # Crossing requests: their pending + our request = acceptance.
                accepted = await self.repo.transition_status(
                    existing.id,
                    PeerConnectionStatus.ACCEPTED,
                    expected_from=(PeerConnectionStatus.PENDING.value,),
                    now=now,
                )
                if accepted is None:
                    return await self._redispatch_request(
                        requester_id, addressee_id, context_message, _retry_allowed
                    )
                self._emit("request_accepted", accepted, requester_id)
                logger.info(
                    "peers_crossing_requests_accepted",
                    connection_id=str(accepted.id),
                )
                return ConnectionStateView(id=accepted.id, status=accepted.status)
            if self._declined_cooldown_active(existing, requester_id, now):
                # Nagging inside the cooldown looks exactly like a missing user.
                raise_not_found_or_unauthorized("peer", addressee_id)
            revived = await self.repo.revive_request(
                existing.id, requester_id, context_message, now=now
            )
            if revived is None:
                return await self._redispatch_request(
                    requester_id, addressee_id, context_message, _retry_allowed
                )
            self._emit("request_created", revived, requester_id)
            logger.info("peers_request_created", connection_id=str(revived.id))
            return ConnectionStateView(id=revived.id, status=revived.status)

        try:
            connection = await self.repo.insert_pair_request(
                requester_id, addressee_id, context_message, now=now
            )
        except IntegrityError:
            # A concurrent request won the pair UNIQUE: reset the failed
            # transaction (nothing but reads happened before the INSERT) and
            # re-dispatch against the row that now exists.
            await self.db.rollback()
            return await self._redispatch_request(
                requester_id, addressee_id, context_message, _retry_allowed
            )
        self._emit("request_created", connection, requester_id)
        logger.info("peers_request_created", connection_id=str(connection.id))
        return ConnectionStateView(id=connection.id, status=connection.status)

    async def _redispatch_request(
        self,
        requester_id: UUID,
        addressee_id: UUID,
        context_message: str | None,
        retry_allowed: bool,
    ) -> ConnectionStateView:
        """Re-run the request state machine once after a lost concurrency claim."""
        if not retry_allowed:  # two consecutive races — answer conservatively
            raise_invalid_input("peers_conflict")
        self.pending_events.clear()
        return await self.request_connection(
            requester_id, addressee_id, context_message, _retry_allowed=False
        )

    async def _get_participant_connection(
        self, user_id: UUID, connection_id: UUID
    ) -> PeerConnection:
        """Load a connection the caller participates in, or answer neutrally.

        Args:
            user_id: The caller.
            connection_id: Pair row id.

        Returns:
            The pair row.
        """
        connection = await self.repo.get_by_id(connection_id)
        if connection is None or user_id not in (connection.user_a_id, connection.user_b_id):
            raise_not_found_or_unauthorized("peer", connection_id)
        return connection

    async def respond_request(
        self, user_id: UUID, connection_id: UUID, accept: bool
    ) -> ConnectionStateView:
        """Accept or decline a pending request (addressee side only — spec §5.2).

        Args:
            user_id: The responder.
            connection_id: Pending pair row id.
            accept: True accepts, False declines.

        Returns:
            Minimal state view after the transition.
        """
        from src.core.exceptions import raise_permission_denied

        connection = await self._get_participant_connection(user_id, connection_id)
        if connection.status != PeerConnectionStatus.PENDING.value:
            raise_invalid_input("peers_not_pending")
        if connection.requested_by_id == user_id:
            raise_permission_denied(
                action="respond to", resource_type="own peer request", user_id=user_id
            )

        now = datetime.now(UTC)
        target = PeerConnectionStatus.ACCEPTED if accept else PeerConnectionStatus.DECLINED
        updated = await self.repo.transition_status(
            connection.id,
            target,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        if updated is None:  # claimed by a concurrent change since the guard read
            raise_invalid_input("peers_not_pending")
        self._emit("request_accepted" if accept else "request_declined", updated, user_id)
        logger.info(
            "peers_request_responded",
            connection_id=str(connection_id),
            accepted=accept,
        )
        return ConnectionStateView(id=updated.id, status=updated.status)

    async def remove_connection(self, user_id: UUID, connection_id: UUID) -> ConnectionStateView:
        """Remove an accepted connection — both sides get notified (Lot 3).

        Args:
            user_id: The remover (either side).
            connection_id: Accepted pair row id.

        Returns:
            Minimal state view after the removal.
        """
        connection = await self._get_participant_connection(user_id, connection_id)
        if connection.status != PeerConnectionStatus.ACCEPTED.value:
            raise_invalid_input("peers_not_connected")
        updated = await self.repo.transition_status(
            connection.id,
            PeerConnectionStatus.REMOVED,
            expected_from=(PeerConnectionStatus.ACCEPTED.value,),
            now=datetime.now(UTC),
        )
        if updated is None:  # already removed by a concurrent action
            raise_invalid_input("peers_not_connected")
        await self.repo.delete_shares_for_connection(connection.id)
        self._emit("connection_removed", updated, user_id)
        logger.info("peers_connection_removed", connection_id=str(connection_id))
        return ConnectionStateView(id=updated.id, status=updated.status)

    # ------------------------------------------------------------------
    # Blocks (silent by design — spec A2, §12.2)
    # ------------------------------------------------------------------

    async def block_peer(self, blocker_id: UUID, blocked_id: UUID) -> None:
        """Block a user: sever any pair state silently, never notify.

        Args:
            blocker_id: User placing the block.
            blocked_id: User being blocked.
        """
        if blocker_id == blocked_id:
            raise_invalid_input("peers_self_block")
        await self.repo.create_block(blocker_id, blocked_id)
        connection = await self.repo.get_pair(blocker_id, blocked_id)
        if connection is not None and connection.status in (
            PeerConnectionStatus.PENDING.value,
            PeerConnectionStatus.ACCEPTED.value,
        ):
            # Claim-or-ignore: a concurrent removal reaching first is fine —
            # shares deletion below is idempotent either way.
            await self.repo.transition_status(
                connection.id,
                PeerConnectionStatus.REMOVED,
                expected_from=(
                    PeerConnectionStatus.PENDING.value,
                    PeerConnectionStatus.ACCEPTED.value,
                ),
                now=datetime.now(UTC),
            )
            await self.repo.delete_shares_for_connection(connection.id)
        # Deliberately NO event: the blocked user must observe nothing.
        logger.info("peers_block_placed", blocker_id=str(blocker_id))

    async def unblock_peer(self, blocker_id: UUID, blocked_id: UUID) -> bool:
        """Lift a block (restores nothing — spec A2).

        Args:
            blocker_id: User who placed the block.
            blocked_id: User who was blocked.

        Returns:
            True if a block existed and was removed.
        """
        removed = await self.repo.delete_block(blocker_id, blocked_id)
        logger.info("peers_block_lifted", blocker_id=str(blocker_id), removed=removed)
        return removed

    async def list_blocks(self, blocker_id: UUID) -> list[BlockView]:
        """List blocks placed by the caller, with display names when available.

        Args:
            blocker_id: The caller.

        Returns:
            Block views, newest first.
        """
        blocks = await self.repo.list_blocks(blocker_id)
        if not blocks:
            return []
        names = await self._display_names({b.blocked_id for b in blocks})
        return [
            BlockView(
                blocked_id=b.blocked_id,
                blocked_display_name=names.get(b.blocked_id),
                created_at=b.created_at,
            )
            for b in blocks
        ]

    # ------------------------------------------------------------------
    # Shares (spec A1 matrix; absence = not shared)
    # ------------------------------------------------------------------

    async def set_share(
        self,
        user_id: UUID,
        connection_id: UUID,
        domain: PeerShareDomain,
        level: PeerShareLevel | None,
    ) -> None:
        """Upsert or remove one of MY shares on an accepted connection.

        Args:
            user_id: The share owner (caller).
            connection_id: Accepted pair row id.
            domain: Domain to (un)share.
            level: Granularity; None removes the share.
        """
        connection = await self._get_participant_connection(user_id, connection_id)
        if connection.status != PeerConnectionStatus.ACCEPTED.value:
            raise_invalid_input("peers_not_connected")
        if level is None:
            await self.repo.delete_share(connection.id, user_id, domain.value)
            logger.info(
                "peers_share_removed",
                connection_id=str(connection_id),
                domain=domain.value,
            )
            return
        if level.value not in _VALID_SHARE_LEVELS[domain.value]:
            raise_invalid_input("peers_invalid_share_level")
        await self.repo.upsert_share(connection.id, user_id, domain.value, level.value)
        logger.info(
            "peers_share_set",
            connection_id=str(connection_id),
            domain=domain.value,
            level=level.value,
        )

    # ------------------------------------------------------------------
    # Listings (both share directions — explicit requirement)
    # ------------------------------------------------------------------

    async def _display_names(self, user_ids: set[UUID]) -> dict[UUID, str]:
        """Batch-load display names for a set of users.

        Args:
            user_ids: Ids to resolve.

        Returns:
            Mapping id → full_name (missing/blank names omitted).
        """
        if not user_ids:
            return {}
        stmt = select(User.id, User.full_name).where(User.id.in_(user_ids))
        rows = (await self.db.execute(stmt)).all()
        return {uid: name for uid, name in rows if name}

    async def _peer_directory(self, user_ids: set[UUID]) -> dict[UUID, tuple[str, str]]:
        """Batch-load (display name, email hint) for peers in listings.

        Args:
            user_ids: Peer ids to resolve.

        Returns:
            Mapping id → (full_name or empty, masked email hint).
        """
        if not user_ids:
            return {}
        stmt = select(User.id, User.full_name, User.email).where(User.id.in_(user_ids))
        rows = (await self.db.execute(stmt)).all()
        return {uid: (name or "", mask_email(email)) for uid, name, email in rows}

    def _peer_of(self, connection: PeerConnection, user_id: UUID) -> UUID:
        """Return the OTHER side of a pair row."""
        return connection.user_b_id if connection.user_a_id == user_id else connection.user_a_id

    async def get_connections(self, user_id: UUID) -> list[ConnectionView]:
        """List accepted connections with BOTH share directions (spec §10).

        Args:
            user_id: The caller.

        Returns:
            Connection views, most recently accepted first.
        """
        connections = await self.repo.list_accepted_for_user(user_id)
        if not connections:
            return []
        directory = await self._peer_directory({self._peer_of(c, user_id) for c in connections})
        views: list[ConnectionView] = []
        for connection in connections:
            peer_id = self._peer_of(connection, user_id)
            name, hint = directory.get(peer_id, ("", ""))
            shares = await self.repo.list_shares(connection.id)
            views.append(
                ConnectionView(
                    id=connection.id,
                    peer_id=peer_id,
                    peer_display_name=name,
                    peer_email_hint=hint,
                    status=connection.status,
                    direction=None,
                    requested_at=connection.requested_at,
                    responded_at=connection.responded_at,
                    my_shares=[
                        ShareItem(domain=s.domain, level=s.level)
                        for s in shares
                        if s.owner_user_id == user_id
                    ],
                    their_shares=[
                        ShareItem(domain=s.domain, level=s.level)
                        for s in shares
                        if s.owner_user_id == peer_id
                    ],
                )
            )
        return views

    async def get_pending(self, user_id: UUID) -> list[ConnectionView]:
        """List pending requests (incoming + outgoing) with peer identity.

        Args:
            user_id: The caller.

        Returns:
            Pending views, newest request first.
        """
        pending = await self.repo.list_pending_for_user(user_id)
        if not pending:
            return []
        directory = await self._peer_directory({self._peer_of(c, user_id) for c in pending})
        views: list[ConnectionView] = []
        for connection in pending:
            peer_id = self._peer_of(connection, user_id)
            name, hint = directory.get(peer_id, ("", ""))
            incoming = connection.requested_by_id != user_id
            views.append(
                ConnectionView(
                    id=connection.id,
                    peer_id=peer_id,
                    peer_display_name=name,
                    peer_email_hint=hint,
                    status=connection.status,
                    direction="incoming" if incoming else "outgoing",
                    requested_at=connection.requested_at,
                    # The note travels to the ADDRESSEE only.
                    context_message=connection.context_message if incoming else None,
                )
            )
        return views

    async def get_access_log(self, user_id: UUID, limit: int = 50) -> list[AccessLogEntry]:
        """List reads OF the caller's data (transparency view — spec §12.4).

        Args:
            user_id: Data owner.
            limit: Cap on returned rows.

        Returns:
            Access entries, newest first.
        """
        rows = await self.repo.list_access_log_for_owner(user_id, limit)
        if not rows:
            return []
        names = await self._display_names({r.accessor_id for r in rows})
        return [
            AccessLogEntry(
                accessor_display_name=names.get(r.accessor_id, ""),
                domain=r.domain,
                tool_name=r.tool_name,
                created_at=r.created_at,
            )
            for r in rows
        ]
