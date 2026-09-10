"""What the heartbeat's nudge query really returns, on a real server (lot 6).

The narrowing lives in SQL because a board may hold thousands of tickets and
the decision wants a handful: filtering in Python would make the cap a
formality. That choice moves the oracle here — a unit test that stubs the
repository proves the fetcher's wording and nothing about the rows.

Two things only a real server can settle: that the cap keeps the RIGHT rows
rather than whichever ones PostgreSQL felt like returning (a `LIMIT` with no
`ORDER BY` hands back the oldest, measured in production under ADR-273), and
that the cooldown stamp is arithmetic the database does rather than a read and
a rewrite two ticks could lose.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.domains.workboard.constants import (
    ActorKind,
    AssigneeKind,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardComment, WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)
DUE_BEFORE = NOW + timedelta(hours=24)
WAITING_SINCE = NOW - timedelta(hours=48)
COOLDOWN_BEFORE = NOW - timedelta(days=2)


def _user(label: str) -> User:
    return User(
        email=f"wb_nudge_{label}_{uuid.uuid4().hex[:6]}@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name=label,
    )


def _ticket(
    owner: User,
    title: str,
    *,
    status: str = TicketStatus.TODO.value,
    priority: str = TicketPriority.MEDIUM.value,
    due_at: datetime | None = None,
    status_changed_at: datetime | None = None,
    last_nudged_at: datetime | None = None,
    assignee: User | None = None,
    assignee_kind: str = AssigneeKind.HUMAN.value,
) -> WorkboardTicket:
    return WorkboardTicket(
        owner_user_id=owner.id,
        title=title,
        status=status,
        priority=priority,
        assignee_kind=assignee_kind,
        assignee_user_id=None if assignee is None else assignee.id,
        position=0,
        created_by="user",
        status_changed_at=status_changed_at or NOW,
        due_at=due_at,
        last_nudged_at=last_nudged_at,
        run_attempts=0,
        run_count=0,
        nudge_count=0,
        follow_assignee=True,
    )


async def _owner(db: AsyncSession, label: str = "Alice") -> User:
    person = _user(label)
    db.add(person)
    await db.flush()
    return person


async def _worthy(db: AsyncSession, user_id: uuid.UUID, *, limit: int = 8) -> list[str]:
    rows = await WorkboardRepository(db).list_nudge_worthy(
        user_id,
        due_before=DUE_BEFORE,
        waiting_since=WAITING_SINCE,
        cooldown_before=COOLDOWN_BEFORE,
        limit=limit,
    )
    return [row.title for row in rows]


class TestWhichTicketsQualify:
    async def test_the_three_reasons_come_back_and_nothing_else(
        self, async_session: AsyncSession
    ) -> None:
        alice = await _owner(async_session)
        async_session.add_all(
            [
                _ticket(alice, "overdue", due_at=NOW - timedelta(hours=5)),
                _ticket(alice, "due soon", due_at=NOW + timedelta(hours=3)),
                _ticket(
                    alice,
                    "waiting",
                    status=TicketStatus.WAITING.value,
                    status_changed_at=NOW - timedelta(days=5),
                ),
                # Due far beyond the window.
                _ticket(alice, "later", due_at=NOW + timedelta(days=10)),
                # Waiting, but only since this morning.
                _ticket(
                    alice,
                    "just stopped",
                    status=TicketStatus.WAITING.value,
                    status_changed_at=NOW - timedelta(hours=1),
                ),
                # No due date and not waiting: nothing makes it late.
                _ticket(alice, "no deadline"),
            ]
        )
        await async_session.commit()

        assert sorted(await _worthy(async_session, alice.id)) == [
            "due soon",
            "overdue",
            "waiting",
        ]

    async def test_a_closed_or_merely_noted_ticket_never_qualifies(
        self, async_session: AsyncSession
    ) -> None:
        """« done » has no future, and an « idea » is a note
        nobody committed to — none of the three can be late."""
        alice = await _owner(async_session)
        overdue = NOW - timedelta(days=1)
        async_session.add_all(
            [
                _ticket(alice, "done", status=TicketStatus.DONE.value, due_at=overdue),
                _ticket(alice, "validating-late", status=TicketStatus.VALIDATING.value),
                _ticket(alice, "idea", status=TicketStatus.IDEA.value, due_at=overdue),
                _ticket(alice, "real", due_at=overdue),
            ]
        )
        await async_session.commit()

        assert await _worthy(async_session, alice.id) == ["real"]

    async def test_a_ticket_still_cooling_down_stays_quiet(
        self, async_session: AsyncSession
    ) -> None:
        alice = await _owner(async_session)
        overdue = NOW - timedelta(days=1)
        async_session.add_all(
            [
                _ticket(
                    alice, "just nudged", due_at=overdue, last_nudged_at=NOW - timedelta(hours=2)
                ),
                _ticket(
                    alice, "cooled off", due_at=overdue, last_nudged_at=NOW - timedelta(days=9)
                ),
                _ticket(alice, "never nudged", due_at=overdue),
            ]
        )
        await async_session.commit()

        assert sorted(await _worthy(async_session, alice.id)) == ["cooled off", "never nudged"]

    async def test_a_shared_ticket_is_on_BOTH_boards(self, async_session: AsyncSession) -> None:
        """The board of U is « U owns it or U holds it » — a peer holding a
        late ticket should hear about it too."""
        alice = await _owner(async_session, "Alice")
        bob = await _owner(async_session, "Bob")
        async_session.add(
            _ticket(alice, "shared and late", due_at=NOW - timedelta(hours=2), assignee=bob)
        )
        await async_session.commit()

        assert await _worthy(async_session, alice.id) == ["shared and late"]
        assert await _worthy(async_session, bob.id) == ["shared and late"]

    async def test_another_persons_board_never_leaks(self, async_session: AsyncSession) -> None:
        alice = await _owner(async_session, "Alice")
        bob = await _owner(async_session, "Bob")
        async_session.add(_ticket(bob, "bob's own", due_at=NOW - timedelta(hours=2)))
        await async_session.commit()

        assert await _worthy(async_session, alice.id) == []


class TestTheCapKeepsTheRightRows:
    async def test_the_most_pressing_survive_the_limit(self, async_session: AsyncSession) -> None:
        """A `LIMIT` with no `ORDER BY` hands back whatever the server likes,
        which in production meant the OLDEST rows (ADR-273). The order is
        priority first, then the nearest deadline, then the key."""
        alice = await _owner(async_session)
        overdue = NOW - timedelta(days=1)
        async_session.add_all(
            [
                _ticket(alice, "low", priority=TicketPriority.LOW.value, due_at=overdue),
                _ticket(alice, "medium", priority=TicketPriority.MEDIUM.value, due_at=overdue),
                _ticket(alice, "urgent", priority=TicketPriority.URGENT.value, due_at=overdue),
                _ticket(alice, "high", priority=TicketPriority.HIGH.value, due_at=overdue),
            ]
        )
        await async_session.commit()

        assert await _worthy(async_session, alice.id, limit=2) == ["urgent", "high"]

    async def test_at_equal_priority_the_nearest_deadline_wins(
        self, async_session: AsyncSession
    ) -> None:
        alice = await _owner(async_session)
        async_session.add_all(
            [
                _ticket(alice, "later", due_at=NOW + timedelta(hours=20)),
                _ticket(alice, "sooner", due_at=NOW - timedelta(days=3)),
            ]
        )
        await async_session.commit()

        assert await _worthy(async_session, alice.id) == ["sooner", "later"]


class TestStartingTheCooldown:
    async def test_it_stamps_and_counts_server_side(self, async_session: AsyncSession) -> None:
        alice = await _owner(async_session)
        ticket = _ticket(alice, "named", due_at=NOW - timedelta(days=1))
        async_session.add(ticket)
        await async_session.commit()
        ticket_id = ticket.id

        stamped = await WorkboardRepository(async_session).bump_nudged(
            [ticket_id], user_id=alice.id
        )
        await async_session.commit()
        async_session.expire_all()

        row = (
            await async_session.execute(
                select(WorkboardTicket).where(WorkboardTicket.id == ticket_id)
            )
        ).scalar_one()
        assert stamped == 1
        assert row.last_nudged_at is not None
        assert row.nudge_count == 1

    async def test_two_ticks_add_up_rather_than_overwriting(
        self, async_session: AsyncSession
    ) -> None:
        """The count is column arithmetic, not a read and a rewrite: the second
        shape loses an increment the moment two ticks overlap."""
        alice = await _owner(async_session)
        ticket = _ticket(alice, "twice", due_at=NOW - timedelta(days=1))
        async_session.add(ticket)
        await async_session.commit()
        ticket_id = ticket.id

        repo = WorkboardRepository(async_session)
        await repo.bump_nudged([ticket_id], user_id=alice.id)
        await repo.bump_nudged([ticket_id], user_id=alice.id)
        await async_session.commit()
        async_session.expire_all()

        row = (
            await async_session.execute(
                select(WorkboardTicket).where(WorkboardTicket.id == ticket_id)
            )
        ).scalar_one()
        assert row.nudge_count == 2

    async def test_an_id_from_another_board_stamps_nothing(
        self, async_session: AsyncSession
    ) -> None:
        """`user_id` is the clause, not decoration."""
        alice = await _owner(async_session, "Alice")
        bob = await _owner(async_session, "Bob")
        ticket = _ticket(bob, "bob's", due_at=NOW - timedelta(days=1))
        async_session.add(ticket)
        await async_session.commit()
        ticket_id = ticket.id

        stamped = await WorkboardRepository(async_session).bump_nudged(
            [ticket_id], user_id=alice.id
        )
        await async_session.commit()
        async_session.expire_all()

        row = (
            await async_session.execute(
                select(WorkboardTicket).where(WorkboardTicket.id == ticket_id)
            )
        ).scalar_one()
        assert stamped == 0
        assert row.last_nudged_at is None
        assert row.nudge_count == 0

    async def test_an_empty_list_touches_nothing(self, async_session: AsyncSession) -> None:
        alice = await _owner(async_session)
        await async_session.commit()

        assert await WorkboardRepository(async_session).bump_nudged([], user_id=alice.id) == 0


class TestWhoHoldsIt:
    async def test_a_deadline_on_a_ticket_LIA_holds_is_not_the_persons(
        self, async_session: AsyncSession
    ) -> None:
        """LIA's backlog is LIA's: the sweep runs it, and its own failure
        notification speaks when it cannot. The person hears only about the
        deadlines THEY are holding."""
        alice = await _owner(async_session)
        overdue = NOW - timedelta(days=1)
        async_session.add_all(
            [
                _ticket(alice, "mine, late", due_at=overdue),
                _ticket(alice, "LIA's, late", due_at=overdue, assignee_kind=AssigneeKind.LIA.value),
            ]
        )
        await async_session.commit()

        assert await _worthy(async_session, alice.id) == ["mine, late"]

    async def test_a_question_LIA_asked_reaches_the_person_whoever_holds_it(
        self, async_session: AsyncSession
    ) -> None:
        alice = await _owner(async_session)
        async_session.add_all(
            [
                _ticket(
                    alice,
                    "LIA asked",
                    status=TicketStatus.WAITING.value,
                    status_changed_at=NOW - timedelta(days=4),
                    assignee_kind=AssigneeKind.LIA.value,
                ),
                _ticket(
                    alice,
                    "LIA delivered",
                    status=TicketStatus.VALIDATING.value,
                    status_changed_at=NOW - timedelta(days=4),
                    assignee_kind=AssigneeKind.LIA.value,
                ),
                _ticket(
                    alice,
                    "LIA just delivered",
                    status=TicketStatus.VALIDATING.value,
                    status_changed_at=NOW - timedelta(hours=1),
                    assignee_kind=AssigneeKind.LIA.value,
                ),
            ]
        )
        await async_session.commit()

        assert sorted(await _worthy(async_session, alice.id)) == ["LIA asked", "LIA delivered"]


class TestWhatLIAWrote:
    async def test_the_latest_LIA_comment_per_ticket_and_nothing_else(
        self, async_session: AsyncSession
    ) -> None:
        alice = await _owner(async_session)
        first = _ticket(alice, "first", status=TicketStatus.WAITING.value)
        second = _ticket(alice, "second", status=TicketStatus.WAITING.value)
        silent = _ticket(alice, "silent", status=TicketStatus.WAITING.value)
        async_session.add_all([first, second, silent])
        await async_session.flush()

        def comment(
            ticket: WorkboardTicket, kind: str, body: str, at: datetime
        ) -> WorkboardComment:
            return WorkboardComment(
                ticket_id=ticket.id,
                author_kind=kind,
                author_user_id=None if kind == ActorKind.LIA.value else alice.id,
                body=body,
                run_id=None,
                created_at=at,
            )

        async_session.add_all(
            [
                comment(first, ActorKind.LIA.value, "older question", NOW - timedelta(days=2)),
                comment(first, ActorKind.LIA.value, "latest question", NOW - timedelta(days=1)),
                # The person's own answer must never be quoted as LIA's words.
                comment(first, ActorKind.USER.value, "my reply", NOW),
                comment(second, ActorKind.LIA.value, "only one", NOW - timedelta(days=1)),
                comment(silent, ActorKind.USER.value, "nobody from LIA", NOW),
            ]
        )
        await async_session.commit()
        ids = [first.id, second.id, silent.id]

        said = await WorkboardRepository(async_session).latest_lia_comments(ids)

        assert said == {first.id: "latest question", second.id: "only one"}

    async def test_no_ticket_reads_nothing(self, async_session: AsyncSession) -> None:
        assert await WorkboardRepository(async_session).latest_lia_comments([]) == {}
