"""Board reads against a real server (ADR-276).

A statement-shape test proves the SQL says what it should; only a server proves
it MEANS it. Three things are checked here and nowhere else:

- « assigned to me » really returns the tickets a board stores with a NULL
  assignee — the common case of a board where nothing was handed over;
- a page and its column counts really describe the same set (ADR-185);
- reordering a column really writes the order given, in one statement.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.constants import AssigneeKind, TicketPriority, TicketStatus
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    user = User(
        email="wb_repo_owner@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name="Repo Owner",
    )
    async_session.add(user)
    await async_session.commit()
    return user


@pytest.fixture
async def peer(async_session: AsyncSession) -> User:
    user = User(
        email="wb_repo_peer@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name="Repo Peer",
    )
    async_session.add(user)
    await async_session.commit()
    return user


def _ticket(owner_id: object, **overrides: object) -> WorkboardTicket:
    values: dict[str, object] = {
        "owner_user_id": owner_id,
        "title": "Book the venue",
        "status": TicketStatus.TODO.value,
        "priority": TicketPriority.MEDIUM.value,
        "assignee_kind": AssigneeKind.HUMAN.value,
        "assignee_user_id": None,
        "position": 0,
        "created_by": "user",
        "status_changed_at": NOW,
        "run_attempts": 0,
        "run_count": 0,
        "nudge_count": 0,
    }
    values.update(overrides)
    return WorkboardTicket(**values)


class TestAssigneeFilter:
    async def test_assigned_to_me_finds_the_tickets_stored_with_a_null_holder(
        self, async_session: AsyncSession, owner: User, peer: User
    ) -> None:
        """The regression this exists for: a board that never handed anything
        over stores NULL everywhere, and a filter reading only the id would
        return an empty board."""
        owner_id = owner.id
        mine = _ticket(owner_id, title="Mine, never handed over")
        handed = _ticket(owner_id, title="Handed to the peer", assignee_user_id=peer.id)
        by_lia = _ticket(owner_id, title="For LIA", assignee_kind=AssigneeKind.LIA.value)
        async_session.add_all([mine, handed, by_lia])
        await async_session.commit()
        mine_id, handed_id, lia_id = mine.id, handed.id, by_lia.id

        repo = WorkboardRepository(async_session)
        rows, total = await repo.list_board(
            owner_id, BoardFilters(assignee="me"), limit=50, offset=0
        )
        assert {row.id for row in rows} == {mine_id}
        assert total == 1

        lia_rows, _ = await repo.list_board(
            owner_id, BoardFilters(assignee="lia"), limit=50, offset=0
        )
        assert {row.id for row in lia_rows} == {lia_id}

        peer_rows, _ = await repo.list_board(
            owner_id, BoardFilters(assignee="peer"), limit=50, offset=0
        )
        assert {row.id for row in peer_rows} == {handed_id}

    async def test_the_peer_reading_their_own_board_is_not_a_peer_to_themselves(
        self, async_session: AsyncSession, owner: User, peer: User
    ) -> None:
        """« Une connexion » must never hand somebody their OWN work.

        A peer's board carries the tickets they hold, and those store THEIR id
        in ``assignee_user_id``. A filter reading « held by anybody » returned
        them under a label saying a connection holds it, and « Moi » returned
        the very same rows.
        """
        owner_id, peer_id = owner.id, peer.id
        held = _ticket(owner_id, title="Handed to the peer", assignee_user_id=peer_id)
        own = _ticket(peer_id, title="The peer's own ticket")
        async_session.add_all([held, own])
        await async_session.commit()
        held_id, own_id = held.id, own.id

        repo = WorkboardRepository(async_session)
        mine, _ = await repo.list_board(peer_id, BoardFilters(assignee="me"), limit=50, offset=0)
        assert {row.id for row in mine} == {held_id, own_id}

        theirs, total = await repo.list_board(
            peer_id, BoardFilters(assignee="peer"), limit=50, offset=0
        )
        assert theirs == []
        assert total == 0


class TestTitleSearch:
    async def test_a_wildcard_the_person_typed_is_a_character_not_a_pattern(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """Measured on this very server before the fix: a search for « _ »
        returned EVERY ticket on the board, because `LIKE` read it as « any
        character ». A term is a needle; the reader typed text, not SQL."""
        owner_id = owner.id
        async_session.add_all(
            [
                _ticket(owner_id, title="Réserver la salle"),
                _ticket(owner_id, title="Marge 100% garantie"),
                _ticket(owner_id, title="Budget 1000 euros"),
            ]
        )
        await async_session.commit()

        repo = WorkboardRepository(async_session)
        rows, total = await repo.list_board(owner_id, BoardFilters(query="_"), limit=50, offset=0)
        assert rows == []
        assert total == 0

        # And `%` matches the sign, not « anything »: « Budget 1000 euros »
        # contains « 100 » and must NOT come back for « 100% ».
        rows, total = await repo.list_board(
            owner_id, BoardFilters(query="100%"), limit=50, offset=0
        )
        assert [row.title for row in rows] == ["Marge 100% garantie"]
        assert total == 1

    async def test_an_ordinary_term_still_matches_case_insensitively(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        owner_id = owner.id
        async_session.add(_ticket(owner_id, title="Réserver la salle"))
        await async_session.commit()

        repo = WorkboardRepository(async_session)
        rows, _total = await repo.list_board(
            owner_id, BoardFilters(query="salle"), limit=50, offset=0
        )
        assert [row.title for row in rows] == ["Réserver la salle"]


class TestPageAndCounts:
    async def test_the_total_and_the_counts_describe_the_page_set(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        owner_id = owner.id
        async_session.add_all(
            [_ticket(owner_id, position=index, title=f"todo {index}") for index in range(3)]
            + [_ticket(owner_id, status=TicketStatus.DONE.value, title="finished")]
        )
        await async_session.commit()

        repo = WorkboardRepository(async_session)
        rows, total = await repo.list_board(owner_id, BoardFilters(), limit=2, offset=0)
        counts = await repo.counts_by_status(owner_id, BoardFilters())

        assert len(rows) == 2, "the page is capped"
        assert total == 4, "the total is the whole set, not the page"
        assert counts["todo"] == 3
        assert counts["done"] == 1
        assert sum(counts.values()) == total

    async def test_a_closed_ticket_drops_out_past_the_cutoff_and_an_open_one_never_does(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        owner_id = owner.id
        old_open = _ticket(
            owner_id, title="Old but open", status_changed_at=NOW - timedelta(days=400)
        )
        old_closed = _ticket(
            owner_id,
            title="Long finished",
            status=TicketStatus.DONE.value,
            status_changed_at=NOW - timedelta(days=400),
        )
        just_closed = _ticket(
            owner_id,
            title="Just finished",
            status=TicketStatus.DONE.value,
            status_changed_at=NOW - timedelta(days=1),
        )
        async_session.add_all([old_open, old_closed, just_closed])
        await async_session.commit()
        open_id, just_closed_id = old_open.id, just_closed.id

        rows, _ = await WorkboardRepository(async_session).list_board(
            owner_id,
            BoardFilters(include_closed_before=NOW - timedelta(days=30)),
            limit=50,
            offset=0,
        )
        assert {row.id for row in rows} == {open_id, just_closed_id}

    async def test_paging_never_repeats_a_ticket_when_sort_keys_tie(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        """Six tickets at position 0: only the primary-key tiebreak makes the
        two pages a partition instead of an overlap."""
        owner_id = owner.id
        async_session.add_all([_ticket(owner_id, title=f"tied {i}") for i in range(6)])
        await async_session.commit()

        repo = WorkboardRepository(async_session)
        first, total = await repo.list_board(owner_id, BoardFilters(), limit=3, offset=0)
        second, _ = await repo.list_board(owner_id, BoardFilters(), limit=3, offset=3)
        seen = [row.id for row in first] + [row.id for row in second]
        assert total == 6
        assert len(set(seen)) == 6


class TestRenumber:
    async def test_it_writes_exactly_the_order_given(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        owner_id = owner.id
        tickets = [_ticket(owner_id, position=index, title=f"t{index}") for index in range(3)]
        async_session.add_all(tickets)
        await async_session.commit()
        wanted = [tickets[2].id, tickets[0].id, tickets[1].id]

        repo = WorkboardRepository(async_session)
        assert await repo.renumber_column(owner_id, TicketStatus.TODO.value, wanted) == 3
        await async_session.commit()

        ordered = (
            (
                await async_session.execute(
                    select(WorkboardTicket.id)
                    .where(WorkboardTicket.owner_user_id == owner_id)
                    .order_by(WorkboardTicket.position)
                )
            )
            .scalars()
            .all()
        )
        assert list(ordered) == wanted

    async def test_it_leaves_another_column_alone(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        owner_id = owner.id
        todo = _ticket(owner_id, position=7, title="in todo")
        doing = _ticket(owner_id, position=7, status=TicketStatus.IN_PROGRESS.value, title="doing")
        async_session.add_all([todo, doing])
        await async_session.commit()
        doing_id = doing.id

        repo = WorkboardRepository(async_session)
        await repo.renumber_column(owner_id, TicketStatus.TODO.value, [todo.id])
        await async_session.commit()
        async_session.expire_all()

        untouched = await async_session.get(WorkboardTicket, doing_id)
        assert untouched is not None
        assert untouched.position == 7


class TestNeedsMe:
    async def test_waiting_on_me_and_late_on_my_board(
        self, async_session: AsyncSession, owner: User, peer: User
    ) -> None:
        owner_id = owner.id
        waiting_on_me = _ticket(owner_id, title="Waiting", status=TicketStatus.WAITING.value)
        waiting_on_peer = _ticket(
            owner_id,
            title="Peer must answer",
            status=TicketStatus.WAITING.value,
            assignee_user_id=peer.id,
        )
        late = _ticket(owner_id, title="Late", due_at=NOW - timedelta(days=2))
        late_but_done = _ticket(
            owner_id,
            title="Late and finished",
            status=TicketStatus.DONE.value,
            due_at=NOW - timedelta(days=2),
        )
        on_time = _ticket(owner_id, title="Later", due_at=NOW + timedelta(days=2))
        async_session.add_all([waiting_on_me, waiting_on_peer, late, late_but_done, on_time])
        await async_session.commit()
        expected = {waiting_on_me.id, late.id}

        rows, total = await WorkboardRepository(async_session).needs_me(owner_id, NOW)
        assert {row.id for row in rows} == expected
        assert total == 2


class TestTitleResolution:
    async def test_an_accented_title_is_found_without_its_accents(
        self, async_session: AsyncSession, owner: User
    ) -> None:
        owner_id = owner.id
        async_session.add(_ticket(owner_id, title="Réserver la salle"))
        await async_session.commit()

        matches = await WorkboardRepository(async_session).find_by_title(
            owner_id, "reserver la salle"
        )
        assert len(matches) == 1

    async def test_a_stranger_finds_nothing(
        self, async_session: AsyncSession, owner: User, peer: User
    ) -> None:
        """Resolution is scoped by the same visibility predicate as the board."""
        owner_id, peer_id = owner.id, peer.id
        async_session.add(_ticket(owner_id, title="Private matter"))
        await async_session.commit()

        assert (
            await WorkboardRepository(async_session).find_by_title(peer_id, "Private matter") == []
        )


class TestSummary:
    async def test_every_figure_is_an_aggregate_over_its_whole_set(
        self, async_session: AsyncSession, owner: User, peer: User
    ) -> None:
        """Counts run over what the account SEES, sums over what it OWNS: a
        ticket a peer handed me is on my board and in my columns, but its
        runs and its euros are the peer's."""
        from src.domains.workboard.summary_queries import read_board_summary

        owner_id, peer_id = owner.id, peer.id
        async_session.add_all(
            [
                _ticket(owner_id, title="plain", position=0),
                _ticket(owner_id, title="late", position=1, due_at=NOW - timedelta(days=2)),
                _ticket(
                    owner_id,
                    title="with LIA",
                    position=2,
                    assignee_kind=AssigneeKind.LIA.value,
                    run_count=2,
                    total_tokens_in=1000,
                    total_tokens_out=200,
                    total_tokens_cache=50,
                    total_google_requests=3,
                    total_cost_eur=Decimal("0.42"),
                ),
                _ticket(owner_id, title="finished", status=TicketStatus.DONE.value),
                # The peer's own ticket, handed to me: visible, not owned.
                _ticket(
                    peer_id,
                    title="handed to me",
                    assignee_user_id=owner_id,
                    run_count=9,
                    total_cost_eur=Decimal("9.99"),
                ),
            ]
        )
        await async_session.commit()

        figures = await read_board_summary(WorkboardRepository(async_session), owner_id, NOW)

        assert sum(figures.counts_by_status.values()) == 5, "everything visible is counted"
        assert figures.counts_by_status["todo"] == 4
        assert figures.counts_by_status["done"] == 1
        assert figures.overdue == 1
        assert figures.held_by_lia == 1
        assert figures.needs_me == 1, "the late one needs me; nothing waits on me"
        assert figures.owned == 4, "the peer's ticket is on my board, not in my count"
        assert figures.runs_total == 2, "the peer's runs are the peer's"
        assert (figures.tokens_in, figures.tokens_out, figures.tokens_cache) == (1000, 200, 50)
        assert figures.google_requests == 3
        assert figures.cost_eur == Decimal("0.42")
