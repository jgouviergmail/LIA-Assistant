"""A connection that ends hands its tickets back, on a real server (lot 5).

Until this lot, `release_pair` existed, was tested, and had no production
caller: removing a connection left every shared ticket assigned to somebody who
could no longer reach the board it lived on. These tests drive the REAL
`PeersService.remove_connection` against PostgreSQL — the only place the two
statements (severance and release) are proven to land in one transaction, and
the only place an unexpected foreign-key action would show itself.

The pair is checked in BOTH directions on purpose: a repository double blind to
direction doubled the rows once already (lot 1), and a release that only walks
one way leaves half the work stranded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Importing the adapter is what claims the seam — the boot does it explicitly,
# and so must a test that exercises the path through it.
import src.domains.workboard.release_adapter  # noqa: F401
from src.domains.peers.models import PeerConnection
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.domains.workboard.constants import (
    AssigneeKind,
    TicketEventKind,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardTicket, WorkboardTicketEvent
from src.domains.workboard.service import WorkboardService

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


def _ticket(owner: User, assignee: User | None, title: str) -> WorkboardTicket:
    return WorkboardTicket(
        owner_user_id=owner.id,
        title=title,
        status=TicketStatus.IN_PROGRESS.value,
        priority=TicketPriority.MEDIUM.value,
        assignee_kind=AssigneeKind.HUMAN.value,
        assignee_user_id=None if assignee is None else assignee.id,
        position=0,
        created_by="user",
        status_changed_at=datetime.now(UTC),
        run_attempts=0,
        run_count=0,
        nudge_count=0,
        follow_assignee=True,
    )


@pytest.fixture
async def connected(async_session: AsyncSession) -> tuple[User, User, PeerConnection]:
    """Two accounts and the ACCEPTED connection between them."""
    left = _user(f"wb_rel_a_{uuid.uuid4().hex[:6]}@test.local", "Alice")
    right = _user(f"wb_rel_b_{uuid.uuid4().hex[:6]}@test.local", "Bob")
    async_session.add_all([left, right])
    await async_session.flush()
    # `ck_peer_connections_pair_order` keeps ONE row per pair by storing the
    # two ids in a canonical order; the release must work whichever side of
    # that ordering an account lands on, so the fixture sorts rather than
    # assuming.
    first, second = sorted((left, right), key=lambda user: user.id)
    connection = PeerConnection(
        user_a_id=first.id,
        user_b_id=second.id,
        requested_by_id=left.id,
        status="accepted",
        requested_at=datetime.now(UTC),
        responded_at=datetime.now(UTC),
    )
    async_session.add(connection)
    await async_session.commit()
    return left, right, connection


class TestRemovingAConnection:
    async def test_it_hands_back_the_tickets_of_BOTH_sides(
        self, async_session: AsyncSession, connected: tuple[User, User, PeerConnection]
    ) -> None:
        """The pair IS the connection: work usually flows both ways, and a
        release that walks one direction leaves half of it stranded."""
        left, right, connection = connected
        async_session.add_all(
            [
                _ticket(left, right, "Alice's, held by Bob"),
                _ticket(left, right, "Alice's second, held by Bob"),
                _ticket(right, left, "Bob's, held by Alice"),
                # A ticket nobody shares must not be touched.
                _ticket(left, None, "Alice's own"),
            ]
        )
        await async_session.commit()

        service = PeersService(async_session)
        await service.remove_connection(left.id, connection.id)
        await async_session.commit()

        rows = (await async_session.execute(select(WorkboardTicket))).scalars().all()
        shared = [row for row in rows if row.title != "Alice's own"]
        assert all(row.assignee_user_id is None for row in shared)
        assert all(row.assignee_kind == AssigneeKind.HUMAN.value for row in shared)
        # The subscription of the side that no longer holds it goes with it.
        assert all(row.follow_assignee is False for row in shared)

    async def test_each_owner_is_told_their_OWN_number(
        self, async_session: AsyncSession, connected: tuple[User, User, PeerConnection]
    ) -> None:
        left, right, connection = connected
        async_session.add_all(
            [
                _ticket(left, right, "one"),
                _ticket(left, right, "two"),
                _ticket(right, left, "three"),
            ]
        )
        await async_session.commit()

        service = PeersService(async_session)
        await service.remove_connection(left.id, connection.id)

        released = dict(service.pending_events[-1].released)
        assert released == {left.id: 2, right.id: 1}

    async def test_the_severance_and_the_release_commit_together(
        self, async_session: AsyncSession, connected: tuple[User, User, PeerConnection]
    ) -> None:
        """A connection that is gone while its tickets stay assigned is worse
        than either alone — so both writes belong to one transaction."""
        left, right, connection = connected
        # The ids are captured BEFORE any commit: `expire_all` expires the
        # FIXTURE objects too, and reading one of them afterwards raises
        # `MissingGreenlet` instead of the assertion the test is about.
        left_id, connection_id = left.id, connection.id
        ticket = _ticket(left, right, "shared")
        async_session.add(ticket)
        await async_session.commit()
        ticket_id = ticket.id

        service = PeersService(async_session)
        await service.remove_connection(left_id, connection_id)
        await async_session.commit()
        async_session.expire_all()

        row = (
            await async_session.execute(
                select(WorkboardTicket).where(WorkboardTicket.id == ticket_id)
            )
        ).scalar_one()
        pair = (
            await async_session.execute(
                select(PeerConnection).where(PeerConnection.id == connection_id)
            )
        ).scalar_one()
        assert row.assignee_user_id is None
        assert pair.status == "removed"

    async def test_every_released_ticket_says_WHY_in_its_history(
        self, async_session: AsyncSession, connected: tuple[User, User, PeerConnection]
    ) -> None:
        # The event log is what a person reads to understand a ticket that came
        # back on its own.
        left, right, connection = connected
        async_session.add(_ticket(left, right, "shared"))
        await async_session.commit()

        service = PeersService(async_session)
        await service.remove_connection(left.id, connection.id)
        await async_session.commit()

        events = (
            (
                await async_session.execute(
                    select(WorkboardTicketEvent).where(WorkboardTicketEvent.kind == "assigned")
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].payload is not None
        assert events[0].payload.get("reason") == "connection_removed"
        # LIA did not do this, and neither did a person: the actor is nobody.
        assert events[0].actor_user_id is None

    async def test_a_pair_holding_nothing_releases_nothing(
        self, async_session: AsyncSession, connected: tuple[User, User, PeerConnection]
    ) -> None:
        left, _right, connection = connected
        async_session.add(_ticket(left, None, "mine alone"))
        await async_session.commit()

        service = PeersService(async_session)
        await service.remove_connection(left.id, connection.id)

        assert service.pending_events[-1].released == ()


class TestABoardThatDiesHalfWay:
    async def test_it_releases_ALL_of_them_or_NONE(
        self, async_session: AsyncSession, connected: tuple[User, User, PeerConnection]
    ) -> None:
        """The seam answers « nothing moved » when the board fails, and that
        answer is what BOTH sides are told.

        Measured 2026-09-09 without the savepoint: the board died after
        releasing one ticket of two, the seam swallowed, the notification said
        « 0 », and the caller's own commit wrote the half already mutated. A
        count shown to a person is exact or it does not exist (ADR-185), so the
        release is all-or-nothing — and the severance, a server-side UPDATE
        already on the wire, survives it either way.
        """
        left, right, connection = connected
        left_id, right_id, connection_id = left.id, right.id, connection.id
        first, second = _ticket(left, right, "one"), _ticket(left, right, "two")
        async_session.add_all([first, second])
        await async_session.commit()
        ticket_ids = [first.id, second.id]

        async def exploding(
            self: WorkboardService, user_a: uuid.UUID, user_b: uuid.UUID
        ) -> list[WorkboardTicket]:
            for row in (await self.repo.list_held_between(user_a, user_b))[:1]:
                row.assignee_user_id = None
                row.follow_assignee = False
                await self._event(
                    row, None, TicketEventKind.ASSIGNED, {"reason": "connection_removed"}
                )
            raise RuntimeError("the board died half way")

        service = PeersService(async_session)
        with patch.object(WorkboardService, "release_pair", exploding):
            await service.remove_connection(left_id, connection_id)
            announced = service.pending_events[-1].released
        await async_session.commit()
        async_session.expire_all()

        rows = (
            (
                await async_session.execute(
                    select(WorkboardTicket).where(WorkboardTicket.id.in_(ticket_ids))
                )
            )
            .scalars()
            .all()
        )
        events = (await async_session.execute(select(WorkboardTicketEvent))).scalars().all()
        pair = (
            await async_session.execute(
                select(PeerConnection).where(PeerConnection.id == connection_id)
            )
        ).scalar_one()

        assert announced == ()
        assert [row.assignee_user_id for row in rows] == [right_id, right_id]
        # The half-written history goes back with the tickets it described.
        assert events == []
        # The person asked for the severance and got it.
        assert pair.status == "removed"


class TestBlockingSomebody:
    async def test_it_releases_the_tickets_and_notifies_nobody(
        self, async_session: AsyncSession, connected: tuple[User, User, PeerConnection]
    ) -> None:
        """« The blocked user must observe nothing »: handing the work back must
        not become the notification a block refuses to send."""
        left, right, _connection = connected
        left_id, right_id = left.id, right.id
        ticket = _ticket(left, right, "shared")
        async_session.add(ticket)
        await async_session.commit()
        ticket_id = ticket.id

        service = PeersService(async_session)
        await service.block_peer(left_id, right_id)
        await async_session.commit()
        async_session.expire_all()

        row = (
            await async_session.execute(
                select(WorkboardTicket).where(WorkboardTicket.id == ticket_id)
            )
        ).scalar_one()
        assert row.assignee_user_id is None
        assert service.pending_events == []
