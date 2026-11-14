"""Ticket categories against a real server (ADR-276).

What a stubbed repository cannot prove, and what is checked here:

- deleting a category sends its tickets back to the unfiled lane — the foreign
  key's ``SET NULL`` — and never deletes one;
- the lanes' counts are EXACT, cell by cell, over the page's own filter, and
  add up to the column counts the same read publishes (ADR-185);
- a peer who holds a ticket reads its owner's lane and nothing else of that
  owner's vocabulary, and cannot refile the ticket;
- the order is dense after every move, insertion and removal, read back from
  the table rather than from the objects the service handed out;
- the cap, the uniqueness and « delete while filing » hold under TWO real
  transactions, which is the only place a missing fence shows;
- a category's NAME is read only from the reader's own board, whatever id is
  asked for, and the dashboard's preview rows carry the category without a
  lazy load the async session would refuse.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.peers.models import PeerConnection, PeerConnectionStatus, canonical_pair
from src.domains.users.account_deletion_service import build_purge_statements
from src.domains.users.models import User
from src.domains.workboard.board_queries import BoardFilters
from src.domains.workboard.category_service import WorkboardCategoryService
from src.domains.workboard.constants import STATUS_ORDER, WorkboardError
from src.domains.workboard.models import WorkboardCategory, WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository
from src.domains.workboard.schemas import (
    CategoryCreate,
    CategoryRow,
    CategoryUpdate,
    TicketCreate,
    TicketUpdate,
)
from src.domains.workboard.service import WorkboardService
from src.domains.workboard.summary_queries import read_attention

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


def _code(exc: BaseAPIException) -> str:
    return exc.detail if isinstance(exc.detail, str) else str(exc.detail)


@pytest.fixture(autouse=True)
def peers_feature_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test environment scrubs ``.env``; a peer assignment needs the flag."""
    monkeypatch.setattr(settings, "peers_enabled", True, raising=False)


@pytest.fixture
async def pair(async_session: AsyncSession) -> tuple[User, User]:
    """An owner and a peer joined by an ACCEPTED connection."""
    owner = _user("wb_cat_owner@test.local", "Category Owner")
    peer = _user("wb_cat_peer@test.local", "Category Peer")
    async_session.add_all([owner, peer])
    await async_session.commit()
    user_a, user_b = canonical_pair(owner.id, peer.id)
    async_session.add(
        PeerConnection(
            user_a_id=user_a,
            user_b_id=user_b,
            requested_by_id=owner.id,
            status=PeerConnectionStatus.ACCEPTED.value,
            requested_at=datetime.now(UTC),
            responded_at=datetime.now(UTC),
        )
    )
    await async_session.commit()
    return owner, peer


async def _category(session: AsyncSession, actor: User, name: str) -> CategoryRow:
    row = await WorkboardCategoryService(session).create(actor, CategoryCreate(name=name))
    await session.commit()
    return row


async def _ticket(session: AsyncSession, actor: User, **fields: Any) -> WorkboardTicket:
    ticket = await WorkboardService(session).create(actor, TicketCreate(**fields))
    await session.commit()
    return ticket


async def _stored_order(session: AsyncSession, owner_id: UUID) -> list[tuple[str, int]]:
    """Names and positions as the TABLE holds them, never as an object remembers."""
    rows = await session.execute(
        select(WorkboardCategory.name, WorkboardCategory.position)
        .where(WorkboardCategory.owner_user_id == owner_id)
        .order_by(WorkboardCategory.position, WorkboardCategory.id)
    )
    return [(name, position) for name, position in rows.all()]


async def _stored_category(session: AsyncSession, ticket_id: UUID) -> UUID | None:
    return (
        await session.execute(
            select(WorkboardTicket.category_id).where(WorkboardTicket.id == ticket_id)
        )
    ).scalar_one()


class TestDeletingACategory:
    async def test_its_tickets_go_back_to_the_unfiled_lane_and_none_is_lost(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        home = await _category(async_session, owner, "Home")
        mine = await _ticket(async_session, owner, title="Paint the hall", category_id=home.id)
        held = await _ticket(
            async_session,
            owner,
            title="Order the paint",
            category_id=home.id,
            assignee_user_id=peer.id,
        )

        released = await WorkboardCategoryService(async_session).delete(owner, home.id)
        await async_session.commit()

        assert released == 2, "counted whoever holds them — the peer's included"
        assert await _stored_category(async_session, mine.id) is None
        assert await _stored_category(async_session, held.id) is None
        remaining = await async_session.execute(
            select(func.count())
            .select_from(WorkboardTicket)
            .where(WorkboardTicket.owner_user_id == owner.id)
        )
        assert remaining.scalar() == 2

    async def test_the_database_itself_refuses_two_rows_folding_to_one_name(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        """The backstop of the service's own check, for a writer that skips it."""
        owner, _ = pair
        async_session.add_all(
            [
                WorkboardCategory(owner_user_id=owner.id, name="Home", name_key="home"),
                WorkboardCategory(owner_user_id=owner.id, name="HOME", name_key="home"),
            ]
        )
        with pytest.raises(IntegrityError):
            await async_session.flush()
        await async_session.rollback()

    async def test_two_accounts_may_use_the_same_name(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        await _category(async_session, owner, "Home")
        theirs = await _category(async_session, peer, "home")
        assert theirs.owner_user_id == peer.id


class TestOrder:
    async def test_it_stays_dense_through_a_move_an_insertion_and_a_removal(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _ = pair
        service = WorkboardCategoryService(async_session)
        rows = [await _category(async_session, owner, name) for name in ("a", "b", "c")]

        moved = await service.update(owner, rows[2].id, CategoryUpdate(position=0))
        await async_session.commit()
        assert moved.position == 0
        assert await _stored_order(async_session, owner.id) == [("c", 0), ("a", 1), ("b", 2)]

        inserted = await service.create(owner, CategoryCreate(name="d", position=1))
        await async_session.commit()
        assert inserted.position == 1
        assert await _stored_order(async_session, owner.id) == [
            ("c", 0),
            ("d", 1),
            ("a", 2),
            ("b", 3),
        ]

        await service.delete(owner, rows[0].id)
        await async_session.commit()
        assert await _stored_order(async_session, owner.id) == [("c", 0), ("d", 1), ("b", 2)]

    async def test_a_rename_is_stored_cleaned_with_its_folded_key(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _ = pair
        row = await _category(async_session, owner, "home")
        renamed = await WorkboardCategoryService(async_session).update(
            owner, row.id, CategoryUpdate(name="  Maison   d'Été ")
        )
        await async_session.commit()
        stored = await async_session.execute(
            select(WorkboardCategory.name, WorkboardCategory.name_key).where(
                WorkboardCategory.id == row.id
            )
        )
        assert renamed.name == "Maison d'Été"
        assert stored.one() == ("Maison d'Été", "maison d'ete")


class TestLanes:
    async def test_every_cell_is_exact_over_the_pages_own_filter(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _ = pair
        home = await _category(async_session, owner, "Home")
        work = await _category(async_session, owner, "Work")
        for title, status, priority, category in (
            ("h1", "todo", "high", home.id),
            ("h2", "todo", "low", home.id),
            ("h3", "done", "high", home.id),
            ("w1", "in_progress", "high", work.id),
            ("u1", "todo", "high", None),
            ("u2", "idea", "low", None),
        ):
            await _ticket(
                async_session,
                owner,
                title=title,
                status=status,
                priority=priority,
                category_id=category,
            )
        filters = BoardFilters(priorities=("high",))

        lanes = await WorkboardCategoryService(async_session).lanes(owner, filters)

        cells = {
            (lane.category_id, status): count
            for lane in lanes
            for status, count in lane.counts_by_status.items()
            if count
        }
        assert cells == {
            (None, "todo"): 1,
            (home.id, "todo"): 1,
            (home.id, "done"): 1,
            (work.id, "in_progress"): 1,
        }
        columns = await WorkboardRepository(async_session).counts_by_status(owner.id, filters)
        for status in STATUS_ORDER:
            assert sum(lane.counts_by_status[status] for lane in lanes) == columns[status], status

    async def test_the_category_filter_keeps_named_lanes_the_unfiled_one_or_both(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _ = pair
        home = await _category(async_session, owner, "Home")
        work = await _category(async_session, owner, "Work")
        await _ticket(async_session, owner, title="h", category_id=home.id)
        await _ticket(async_session, owner, title="w", category_id=work.id)
        await _ticket(async_session, owner, title="u")
        service = WorkboardService(async_session)

        async def titles(filters: BoardFilters) -> set[str]:
            rows, total, _ = await service.board(owner, filters, limit=50, offset=0)
            assert total == len(rows)
            return {row.title for row in rows}

        assert await titles(BoardFilters(categories=(home.id,))) == {"h"}
        assert await titles(BoardFilters(uncategorized=True)) == {"u"}
        assert await titles(BoardFilters(categories=(home.id,), uncategorized=True)) == {"h", "u"}
        assert await titles(BoardFilters()) == {"h", "w", "u"}


class TestAPeerWhoHoldsATicket:
    async def test_they_read_its_lane_and_nothing_else_of_the_owners(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        home = await _category(async_session, owner, "Home")
        await _category(async_session, owner, "Private plans")
        own = await _category(async_session, peer, "Mine")
        await _ticket(
            async_session, owner, title="Shared", category_id=home.id, assignee_user_id=peer.id
        )
        service = WorkboardCategoryService(async_session)

        lanes = await service.lanes(peer, BoardFilters())
        listing = await service.listing(peer)

        assert [(lane.category_id, lane.owner_user_id) for lane in lanes] == [
            (None, None),
            (own.id, peer.id),
            (home.id, owner.id),
        ]
        assert [(row.name, row.ticket_count) for row in listing.categories] == [
            ("Mine", 0),
            ("Home", 1),
        ]

    async def test_they_move_it_between_columns_and_cannot_refile_it(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        home = await _category(async_session, owner, "Home")
        own = await _category(async_session, peer, "Mine")
        ticket = await _ticket(
            async_session, owner, title="Shared", category_id=home.id, assignee_user_id=peer.id
        )
        service = WorkboardService(async_session)

        moved = await service.move(peer, ticket.id, "in_progress", 0)
        await async_session.commit()
        assert (moved.status, moved.category_id) == ("in_progress", home.id)

        # No rollback between the two: the refusal comes before anything is
        # written, and a rollback would expire the very rows the next call
        # names — a failure of the harness, not of the rule under test.
        for refiling in (TicketUpdate(clear_category=True), TicketUpdate(category_id=own.id)):
            with pytest.raises(BaseAPIException) as exc:
                await service.update(peer, ticket.id, refiling)
            assert _code(exc.value) == WorkboardError.PEER_CANNOT_EDIT_FIELD.value
        assert await _stored_category(async_session, ticket.id) == home.id

    async def test_an_owner_cannot_file_under_somebody_elses_category(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, peer = pair
        theirs = await _category(async_session, peer, "Mine")
        ticket = await _ticket(async_session, owner, title="Mine to file")
        with pytest.raises(BaseAPIException) as exc:
            await WorkboardService(async_session).update(
                owner, ticket.id, TicketUpdate(category_id=theirs.id)
            )
        assert _code(exc.value) == WorkboardError.CATEGORY_UNKNOWN.value


class TestFiling:
    async def test_a_step_is_born_in_its_parents_lane_and_a_drop_refiles_in_one_write(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _ = pair
        home = await _category(async_session, owner, "Home")
        work = await _category(async_session, owner, "Work")
        parent = await _ticket(async_session, owner, title="Renovate", category_id=home.id)
        step = await _ticket(async_session, owner, title="Buy paint", parent_id=parent.id)
        assert await _stored_category(async_session, step.id) == home.id

        service = WorkboardService(async_session)
        await service.move(owner, step.id, "done", 0, category_id=work.id)
        await async_session.commit()
        stored = await async_session.execute(
            select(WorkboardTicket.status, WorkboardTicket.category_id).where(
                WorkboardTicket.id == step.id
            )
        )
        assert stored.one() == ("done", work.id)

        await service.move(owner, step.id, "todo", 0, clear_category=True)
        await async_session.commit()
        assert await _stored_category(async_session, step.id) is None


class TestNamingACategoryOffTheBoard:
    """The hub, the dashboard and the assistant show the lane as a badge."""

    async def test_a_name_is_read_only_from_the_readers_own_board(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        """An id from somewhere else answers nothing: the name is its owner's text."""
        owner, peer = pair
        home = await _category(async_session, owner, "Home")
        private = await _category(async_session, owner, "Private plans")
        mine = await _category(async_session, peer, "Mine")
        held = await _ticket(
            async_session, owner, title="Shared", category_id=home.id, assignee_user_id=peer.id
        )
        kept = await _ticket(async_session, owner, title="Kept", category_id=private.id)
        service = WorkboardCategoryService(async_session)

        # The owner names both of their categories.
        assert await service.names_for(owner.id, [held, kept]) == {
            home.id: "Home",
            private.id: "Private plans",
        }
        # The peer names the lane of the ticket they hold — and NOT the other
        # one, even when handed a row that points at it.
        assert await service.names_for(peer.id, [held, kept]) == {home.id: "Home"}
        # Their own category is theirs to name; the owner cannot.
        assert await service.repo.names(peer.id, {mine.id}) == {mine.id: "Mine"}
        assert await service.repo.names(owner.id, {mine.id}) == {}

    async def test_a_deleted_category_is_no_longer_named(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _peer = pair
        home = await _category(async_session, owner, "Home")
        service = WorkboardCategoryService(async_session)
        await service.delete(owner, home.id)
        await async_session.commit()

        assert await service.repo.names(owner.id, {home.id}) == {}

    async def test_the_dashboard_previews_carry_the_category_without_a_lazy_load(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        """A column the preview statement does not load raises on an async
        session the moment it is read — the defect this pins."""
        owner, _peer = pair
        home = await _category(async_session, owner, "Home")
        filed = await _ticket(async_session, owner, title="Filed", category_id=home.id)
        await _ticket(async_session, owner, title="Loose")
        # Read back from the server, not from the identity map the writes filled.
        async_session.expunge_all()

        figures = await read_attention(
            WorkboardRepository(async_session), owner.id, datetime.now(UTC), limit=5
        )

        by_title = {ticket.title: ticket for ticket in figures.previews["open_total"]}
        assert by_title["Filed"].category_id == home.id
        assert by_title["Loose"].category_id is None
        names = await WorkboardCategoryService(async_session).names_for(
            owner.id, figures.previews["open_total"]
        )
        assert names == {filed.category_id: "Home"}

    async def test_the_board_at_a_glance_counts_each_lane_over_the_whole_board(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        owner, _peer = pair
        home = await _category(async_session, owner, "Home")
        await _ticket(async_session, owner, title="A", category_id=home.id)
        await _ticket(async_session, owner, title="B", category_id=home.id)
        await _ticket(async_session, owner, title="C")

        summary = await WorkboardService(async_session).summary(owner)

        lanes = {lane.category_id: sum(lane.counts_by_status.values()) for lane in summary.lanes}
        assert lanes == {None: 1, home.id: 2}
        # The lanes and the columns are two cuts of ONE set.
        assert sum(lanes.values()) == summary.total == 3


class TestWhenTheAccountGoes:
    async def test_a_hard_deleted_owner_takes_their_lanes_and_leaves_the_peers(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        """Two foreign-key actions reach the same ticket row — the owner's
        CASCADE and the category's SET NULL — in an order nothing fixes. No
        constraint may tie the two columns, and none does: this must not raise."""
        owner, peer = pair
        home = await _category(async_session, owner, "Home")
        kept = await _category(async_session, peer, "Mine")
        await _ticket(async_session, owner, title="Filed", category_id=home.id)

        await async_session.execute(delete(User).where(User.id == owner.id))
        await async_session.commit()

        left = await async_session.execute(select(WorkboardCategory.id))
        assert [row for (row,) in left.all()] == [kept.id]

    async def test_the_account_purge_removes_the_accounts_own_lanes_only(
        self, async_session: AsyncSession, pair: tuple[User, User]
    ) -> None:
        """Account deletion SCRUBS the users row: no foreign key fires, so the
        purge has to name the table itself."""
        owner, peer = pair
        await _category(async_session, owner, "Home")
        kept = await _category(async_session, peer, "Mine")

        for _, statement in build_purge_statements(owner.id):
            await async_session.execute(statement)
        await async_session.commit()

        left = await async_session.execute(select(WorkboardCategory.id))
        assert [row for (row,) in left.all()] == [kept.id]


# ---------------------------------------------------------------------------
# Two REAL transactions. ``async_session`` keeps everything inside one
# uncommitted transaction, so a second connection would see no account at all
# and every race would « pass » by finding nothing to fight over.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def racing(async_engine: Any, test_database_url: str) -> AsyncIterator[tuple[Any, UUID]]:
    """A sessionmaker whose writes really commit, one account, and its clean-up.

    Depends on ``async_engine`` so the schema exists. What is written here
    outlives the test by construction, so the fixture deletes the account —
    every table under test hangs off it by CASCADE.
    """
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        account = _user(f"wb_cat_race_{uuid4().hex}@test.local", "Race Owner")
        session.add(account)
        await session.commit()
        account_id = account.id
    yield maker, account_id
    async with maker() as session:
        await session.execute(delete(User).where(User.id == account_id))
        await session.commit()
    await engine.dispose()


async def _create_and_hold(maker: Any, account_id: UUID, name: str) -> str:
    """One request's whole life: create, linger inside the transaction, commit."""
    async with maker() as session:
        actor = await session.get(User, account_id)
        assert actor is not None
        try:
            await WorkboardCategoryService(session).create(actor, CategoryCreate(name=name))
            await asyncio.sleep(0.3)
            await session.commit()
        except BaseAPIException as refused:
            await session.rollback()
            return _code(refused)
        return "created"


class TestTwoRequestsAtOnce:
    async def test_the_cap_admits_one_of_two_simultaneous_creations(
        self, racing: tuple[Any, UUID], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        maker, account_id = racing
        monkeypatch.setattr(settings, "workboard_max_categories_per_user", 1)

        outcomes = await asyncio.gather(
            _create_and_hold(maker, account_id, "first"),
            _create_and_hold(maker, account_id, "second"),
        )

        assert sorted(outcomes) == ["created", WorkboardError.TOO_MANY_CATEGORIES.value]

    async def test_one_name_is_given_once_whatever_its_spelling(
        self, racing: tuple[Any, UUID]
    ) -> None:
        maker, account_id = racing

        outcomes = await asyncio.gather(
            _create_and_hold(maker, account_id, "Maison"),
            _create_and_hold(maker, account_id, "MAISON"),
        )

        assert sorted(outcomes) == ["created", WorkboardError.CATEGORY_NAME_TAKEN.value]

    async def test_a_deletion_and_a_filing_never_leave_a_ticket_in_a_dead_lane(
        self, racing: tuple[Any, UUID]
    ) -> None:
        """Whichever wins, the end state is the same and nothing raises a
        foreign-key violation: the category is gone and the ticket is unfiled."""
        maker, account_id = racing
        async with maker() as session:
            actor = await session.get(User, account_id)
            assert actor is not None
            category = await WorkboardCategoryService(session).create(
                actor, CategoryCreate(name="Doomed")
            )
            ticket = await WorkboardService(session).create(actor, TicketCreate(title="t"))
            await session.commit()
            category_id, ticket_id = category.id, ticket.id

        async def delete_and_hold() -> str:
            async with maker() as session:
                actor = await session.get(User, account_id)
                assert actor is not None
                released = await WorkboardCategoryService(session).delete(actor, category_id)
                await asyncio.sleep(0.3)
                await session.commit()
                return f"deleted:{released}"

        async def file_and_hold() -> str:
            async with maker() as session:
                actor = await session.get(User, account_id)
                assert actor is not None
                try:
                    await WorkboardService(session).update(
                        actor, ticket_id, TicketUpdate(category_id=category_id)
                    )
                    await asyncio.sleep(0.3)
                    await session.commit()
                except BaseAPIException as refused:
                    await session.rollback()
                    return _code(refused)
                return "filed"

        outcomes = set(await asyncio.gather(delete_and_hold(), file_and_hold()))

        assert outcomes in (
            {"deleted:0", WorkboardError.CATEGORY_UNKNOWN.value},
            {"deleted:1", "filed"},
        )
        async with maker() as session:
            assert await _stored_category(session, ticket_id) is None
            gone = await session.execute(
                select(func.count())
                .select_from(WorkboardCategory)
                .where(WorkboardCategory.id == category_id)
            )
            assert gone.scalar() == 0
