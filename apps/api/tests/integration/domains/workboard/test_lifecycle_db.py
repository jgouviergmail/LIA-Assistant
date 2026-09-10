"""What only PostgreSQL can prove about a ticket's lifecycle (ADR-276).

This file exists because a defect in the FIRST design of these tables was
invisible to every unit test and surfaced only against a real server: the
ticket carried a ``peer_connection_id`` with a CHECK tying it to
``assignee_user_id``, and deleting the peer's account fires TWO independent
foreign-key actions on the same row. PostgreSQL applied them in an order that
made the CHECK reject the intermediate state — and no order is guaranteed, so
every cross-column CHECK here was violable. ``CHECK`` constraints cannot be
``DEFERRABLE``, so the column went and the invariant moved to the service.

The three assertions below are that proof, kept as a regression guard:

1. a departing PEER releases the ticket instead of destroying it;
2. their words survive as an authorless tombstone on the owner's ticket;
3. a departing OWNER takes the ticket and its children with it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Select, delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.account_deletion_service import build_workboard_release
from src.domains.users.models import User
from src.domains.workboard.constants import AssigneeKind, TicketPriority, TicketStatus
from src.domains.workboard.models import WorkboardComment, WorkboardTicket, WorkboardTicketEvent

pytestmark = pytest.mark.integration


def _user(email: str, name: str) -> User:
    return User(
        email=email,
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name=name,
    )


def _ticket(owner: User, *, assignee: User | None = None, **overrides: object) -> WorkboardTicket:
    """A ticket in its simplest valid shape.

    Args:
        owner: The board it belongs to.
        assignee: The account holding it; ``None`` means the owner does.
        **overrides: Any column to set differently.

    Returns:
        The unsaved row.
    """
    values: dict[str, object] = {
        "owner_user_id": owner.id,
        "title": "Book the venue",
        "status": TicketStatus.TODO.value,
        "priority": TicketPriority.MEDIUM.value,
        "assignee_kind": AssigneeKind.HUMAN.value,
        "assignee_user_id": None if assignee is None else assignee.id,
        "position": 0,
        "created_by": "user",
        "status_changed_at": datetime.now(UTC),
        "run_attempts": 0,
        "run_count": 0,
        "nudge_count": 0,
    }
    values.update(overrides)
    return WorkboardTicket(**values)


@pytest.fixture
async def pair(async_session: AsyncSession) -> tuple[User, User]:
    """Two accounts: an owner and the peer they hand a ticket to."""
    owner = _user("wb_owner@test.local", "Board Owner")
    peer = _user("wb_peer@test.local", "Board Peer")
    async_session.add_all([owner, peer])
    await async_session.commit()
    return owner, peer


class TestDepartingPeer:
    """A peer leaving must never cost the owner their own work."""

    async def test_the_ticket_is_released_not_destroyed(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        owner_id, peer_id = owner.id, peer.id
        ticket = _ticket(owner, assignee=peer, follow_assignee=True)
        async_session.add(ticket)
        await async_session.commit()
        ticket_id = ticket.id

        await async_session.execute(delete(User).where(User.id == peer_id))
        await async_session.commit()
        # ``expire_all`` invalidates every loaded object, ``owner`` included —
        # so the ids are read BEFORE it, never through an expired instance.
        async_session.expire_all()

        released = await async_session.get(WorkboardTicket, ticket_id)
        assert released is not None, "the owner's ticket must survive their peer's departure"
        assert released.assignee_user_id is None
        assert released.effective_assignee_id == owner_id

    async def test_their_words_survive_without_naming_them(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        """SET NULL, not CASCADE: a comment on someone else's ticket belongs to
        that ticket, and its author becomes a dated tombstone."""
        owner, peer = pair
        peer_id = peer.id
        ticket = _ticket(owner, assignee=peer)
        async_session.add(ticket)
        await async_session.commit()
        comment = WorkboardComment(
            ticket_id=ticket.id, author_kind="peer", author_user_id=peer_id, body="On it."
        )
        async_session.add(comment)
        await async_session.commit()
        comment_id = comment.id

        await async_session.execute(delete(User).where(User.id == peer_id))
        await async_session.commit()
        async_session.expire_all()

        kept = await async_session.get(WorkboardComment, comment_id)
        assert kept is not None
        assert kept.body == "On it."
        assert kept.author_user_id is None


class TestDepartingOwner:
    """The owner's board goes with them, children and history included."""

    async def test_everything_hanging_off_the_ticket_goes(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        owner_id, peer_id = owner.id, peer.id
        parent = _ticket(owner)
        async_session.add(parent)
        await async_session.commit()
        child = _ticket(owner, parent_id=parent.id, title="Call the caterer")
        comment = WorkboardComment(
            ticket_id=parent.id, author_kind="peer", author_user_id=peer_id, body="Noted."
        )
        event = WorkboardTicketEvent(
            ticket_id=parent.id, actor_kind="user", actor_user_id=owner_id, kind="created"
        )
        async_session.add_all([child, comment, event])
        await async_session.commit()
        parent_id, child_id, comment_id, event_id = parent.id, child.id, comment.id, event.id

        await async_session.execute(delete(User).where(User.id == owner_id))
        await async_session.commit()
        async_session.expire_all()

        assert await async_session.get(WorkboardTicket, parent_id) is None
        assert await async_session.get(WorkboardTicket, child_id) is None
        assert await async_session.get(WorkboardComment, comment_id) is None
        assert await async_session.get(WorkboardTicketEvent, event_id) is None


class TestPurgeRelease:
    """Account deletion SCRUBS the users row, so no FK action fires: the
    explicit release is the only thing that hands the ticket back."""

    async def test_release_touches_the_held_ticket_and_not_the_owned_one(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        peer_id = peer.id
        held = _ticket(owner, assignee=peer, follow_assignee=True, title="Held by the peer")
        own = _ticket(peer, title="The peer's own ticket")
        async_session.add_all([held, own])
        await async_session.commit()
        held_id, own_id = held.id, own.id

        result = await async_session.execute(build_workboard_release(peer_id))
        await async_session.commit()
        async_session.expire_all()

        assert result.rowcount == 1
        released = await async_session.get(WorkboardTicket, held_id)
        assert released is not None
        assert released.assignee_user_id is None
        assert released.assignee_kind == AssigneeKind.HUMAN.value
        assert released.follow_assignee is False
        untouched = await async_session.get(WorkboardTicket, own_id)
        assert untouched is not None
        assert untouched.owner_user_id == peer_id


class TestConstraints:
    """The invariants the database itself refuses to break."""

    async def test_a_child_cannot_outlive_its_parent(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _peer = pair
        parent = _ticket(owner)
        async_session.add(parent)
        await async_session.commit()
        child = _ticket(owner, parent_id=parent.id, title="child")
        async_session.add(child)
        await async_session.commit()
        child_id = child.id

        await async_session.delete(parent)
        await async_session.commit()
        async_session.expire_all()

        assert await async_session.get(WorkboardTicket, child_id) is None

    async def test_a_ticket_needs_an_owner_that_exists(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _peer = pair
        orphan = _ticket(owner)
        orphan.owner_user_id = uuid.uuid4()
        async_session.add(orphan)
        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()

    async def test_the_sweep_index_exists_on_the_server(self, async_session: AsyncSession) -> None:
        """A partial index the planner cannot find is a sweep that seq-scans
        every board on the instance, once a minute, forever."""
        from sqlalchemy import text

        found = (
            await async_session.execute(
                text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
                {"name": "ix_workboard_tickets_lia_todo"},
            )
        ).scalar()
        assert found == 1

    async def test_the_partial_index_is_the_one_the_sweep_scan_uses(
        self, async_session: AsyncSession
    ) -> None:
        """Read the PLAN, not the catalogue: an index that exists but is never
        chosen protects nothing. ``enable_seqscan=off`` removes the small-table
        bias so the planner states which index it CAN use for this predicate."""
        from sqlalchemy import text

        await async_session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row
            for row in (
                await async_session.execute(
                    text(
                        "EXPLAIN SELECT id FROM workboard_tickets "
                        "WHERE assignee_kind = 'lia' AND status = 'todo' "
                        "AND run_claimed_at IS NULL "
                        "AND (start_at IS NULL OR start_at <= now()) "
                        "ORDER BY start_at"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "ix_workboard_tickets_lia_todo" in plan, plan


class TestSelectByBoard:
    """Visibility is « owner = U or assignee = U », on the server too."""

    async def test_both_sides_see_the_same_row(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        owner_id, peer_id = owner.id, peer.id
        shared = _ticket(owner, assignee=peer)
        mine_only = _ticket(owner, title="Mine alone")
        async_session.add_all([shared, mine_only])
        await async_session.commit()
        shared_id, mine_only_id = shared.id, mine_only.id

        def board(user_id: uuid.UUID) -> Select[tuple[uuid.UUID]]:
            return select(WorkboardTicket.id).where(
                or_(
                    WorkboardTicket.owner_user_id == user_id,
                    WorkboardTicket.assignee_user_id == user_id,
                )
            )

        owner_board = set((await async_session.execute(board(owner_id))).scalars().all())
        peer_board = set((await async_session.execute(board(peer_id))).scalars().all())
        assert owner_board == {shared_id, mine_only_id}
        assert peer_board == {shared_id}
