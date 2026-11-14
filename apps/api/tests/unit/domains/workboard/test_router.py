"""The routes hand the caller down, commit on success only (ADR-276).

A router in this codebase owns three things and nothing else: the HTTP shape,
the dependency wiring, and the transaction boundary. So that is what is pinned
here — the rights and the bounds belong to ``test_service.py``, and their
behaviour against a server to ``tests/integration``.

The transaction assertions matter more than they look: a route that commits on
the way to an exception leaves half a change behind, and every refusal in this
domain is raised from the service AFTER it has already mutated the row it
loaded.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.core.exceptions import ResourceNotFoundError
from src.domains.shared.display_query import DisplayQuery
from src.domains.workboard.category_router import (
    create_category,
    delete_category,
    list_categories,
    update_category,
)
from src.domains.workboard.router import (
    add_comment,
    board_summary,
    create_ticket,
    delete_ticket,
    get_ticket,
    list_board,
    move_ticket,
    needs_me,
    router,
    run_ticket_now,
    update_ticket,
)
from src.domains.workboard.schemas import (
    BoardSummary,
    CategoryCreate,
    CategoryList,
    CategoryRow,
    CategoryUpdate,
    CommentCreate,
    LaneRow,
    MoveRequest,
    TicketCreate,
    TicketUpdate,
)
from src.domains.workboard.service import TicketBundle

pytestmark = pytest.mark.unit


def _user() -> Any:
    return SimpleNamespace(id=uuid.uuid4())


def _row(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "owner_user_id": uuid.uuid4(),
        "parent_id": None,
        "title": "Book the venue",
        "description": None,
        "status": "todo",
        "priority": "medium",
        "start_at": None,
        "due_at": None,
        "assignee_kind": "human",
        "assignee_user_id": None,
        "effective_assignee_id": uuid.uuid4(),
        "position": 0,
        "follow_owner": False,
        "follow_assignee": False,
        "created_by": "user",
        "status_changed_at": datetime.now(UTC),
        "run_count": 0,
        "run_claimed_at": None,
        "last_run_at": None,
        "last_run_outcome": None,
        "last_run_error": None,
        "last_run_tokens_in": None,
        "last_run_tokens_out": None,
        "last_run_tokens_cache": None,
        "last_run_google_requests": None,
        "last_run_cost_eur": None,
        "execution_mode": "react",
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "total_tokens_cache": 0,
        "total_google_requests": 0,
        "total_cost_eur": 0.0,
        "category_id": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service() -> Any:
    """Patch the service the router constructs, and hand back the instance."""
    return patch("src.domains.workboard.router.WorkboardService")


@contextmanager
def _lanes(lanes: list[LaneRow] | None = None) -> Iterator[AsyncMock]:
    """Patch the category service the board read asks for its lanes.

    Yields:
        The ``lanes`` call, so a test can read what it was asked with.
    """
    with patch("src.domains.workboard.router.WorkboardCategoryService") as service_cls:
        service_cls.return_value.lanes = AsyncMock(return_value=lanes or [])
        yield service_cls.return_value.lanes


async def _read_board(db: Any, **overrides: Any) -> Any:
    """Call the board read as FastAPI would, every parameter stated.

    The route's defaults are ``Query(...)`` objects, which only FastAPI
    resolves: a direct call has to name each one, so they are named once here.
    """
    arguments: dict[str, Any] = {
        "status": None,
        "assignee": "all",
        "priority": None,
        "overdue": False,
        "due_before": None,
        "q": None,
        "closed_days": None,
        "sort": "position",
        "limit": 50,
        "offset": 0,
        "category": None,
        "uncategorized": False,
        "user": _user(),
        "db": db,
    }
    arguments.update(overrides)
    return await list_board(**arguments)


class TestBoard:
    @pytest.fixture(autouse=True)
    def _no_lane(self) -> Iterator[None]:
        with _lanes():
            yield

    async def test_it_returns_the_page_the_total_and_the_counts(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(
                return_value=([_row()], 7, {"todo": 7, "done": 0})
            )
            page = await _read_board(db)
        assert page.total == 7
        assert page.counts_by_status["todo"] == 7
        assert len(page.tickets) == 1
        assert page.lanes == []

    async def test_a_read_never_commits(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await _read_board(db)
        db.commit.assert_not_awaited()

    async def test_closed_days_becomes_an_instant_the_repository_can_compare(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await _read_board(db, closed_days=30)
            filters = service_cls.return_value.board.await_args.args[1]
        assert filters.include_closed_before is not None
        assert filters.include_closed_before.tzinfo is not None, "UTC-aware, never naive"

    async def test_zero_closed_days_still_bounds_the_read(self) -> None:
        """0 means « hide everything already closed », not « no filter »."""
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await _read_board(db, closed_days=0)
            filters = service_cls.return_value.board.await_args.args[1]
        assert filters.include_closed_before is not None

    async def test_the_filters_reach_the_service_verbatim(self) -> None:
        db = AsyncMock()
        wanted = uuid.uuid4()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await _read_board(
                db,
                status=["todo", "waiting"],
                assignee="lia",
                priority=["high"],
                overdue=True,
                due_before=datetime(2026, 9, 30, tzinfo=UTC),
                q="venue",
                sort="due",
                limit=10,
                offset=20,
                category=[wanted],
                uncategorized=True,
            )
            filters = service_cls.return_value.board.await_args.args[1]
            kwargs = service_cls.return_value.board.await_args.kwargs
        assert filters.statuses == ("todo", "waiting")
        assert filters.assignee == "lia"
        assert filters.priorities == ("high",)
        assert filters.overdue is True
        assert filters.query == "venue"
        assert filters.sort == "due"
        assert filters.categories == (wanted,)
        assert filters.uncategorized is True
        assert kwargs == {"limit": 10, "offset": 20}


class TestBoardLanes:
    async def test_the_lanes_are_counted_over_the_pages_own_filter(self) -> None:
        """One filter object, handed to both reads: a lane's header and the
        cards under it cannot then disagree about what was asked (ADR-185)."""
        db = AsyncMock()
        lane = LaneRow(category_id=None, name=None, owner_user_id=None, counts_by_status={})
        with _lanes([lane]) as lanes_call, _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            page = await _read_board(db, overdue=True)
            page_filters = service_cls.return_value.board.await_args.args[1]
        assert page.lanes == [lane]
        assert lanes_call.await_args.args[1] is page_filters


class TestCategoryRoutes:
    def test_they_are_mounted_under_the_board_and_behind_its_switch(self) -> None:
        """A category is part of the board: same prefix, same operator switch.

        Proved by a REQUEST, never by reading the route table: this FastAPI
        resolves an included router lazily, so the table holds a wrapper and
        says nothing of what a nested route inherits. The switch is replaced
        by a refusal with a status nothing else on the path answers — were it
        not applied, the unauthenticated request would reach the session
        dependency and answer 401 instead.
        """
        app = FastAPI()
        app.include_router(router)

        def switched_off() -> None:
            raise HTTPException(status_code=418)

        app.dependency_overrides[router.dependencies[0].dependency] = switched_off
        client = TestClient(app)
        one = f"/workboard/categories/{uuid.uuid4()}"
        answers = {
            "control: the board itself": client.get("/workboard/tickets"),
            "list": client.get("/workboard/categories"),
            "create": client.post("/workboard/categories", json={"name": "Home"}),
            "update": client.patch(one, json={"name": "Work"}),
            "delete": client.delete(one),
        }
        assert {name: answer.status_code for name, answer in answers.items()} == dict.fromkeys(
            answers, 418
        )

    async def test_a_listing_never_commits(self) -> None:
        db = AsyncMock()
        listing = CategoryList(categories=[], max_categories=20, name_max_chars=40)
        with patch("src.domains.workboard.category_router.WorkboardCategoryService") as cls:
            cls.return_value.listing = AsyncMock(return_value=listing)
            assert await list_categories(user=_user(), db=db) is listing
        db.commit.assert_not_awaited()

    async def test_every_write_commits_once(self) -> None:
        row = CategoryRow(
            id=uuid.uuid4(), owner_user_id=uuid.uuid4(), name="Home", position=0, ticket_count=0
        )
        with patch("src.domains.workboard.category_router.WorkboardCategoryService") as cls:
            cls.return_value.create = AsyncMock(return_value=row)
            cls.return_value.update = AsyncMock(return_value=row)
            cls.return_value.delete = AsyncMock(return_value=3)
            created_db, updated_db, deleted_db = AsyncMock(), AsyncMock(), AsyncMock()
            await create_category(payload=CategoryCreate(name="Home"), user=_user(), db=created_db)
            await update_category(
                category_id=row.id, payload=CategoryUpdate(name="Work"), user=_user(), db=updated_db
            )
            result = await delete_category(category_id=row.id, user=_user(), db=deleted_db)
        for db in (created_db, updated_db, deleted_db):
            db.commit.assert_awaited_once()
        assert result.released == 3

    async def test_a_refused_write_commits_nothing(self) -> None:
        db = AsyncMock()
        with patch("src.domains.workboard.category_router.WorkboardCategoryService") as cls:
            cls.return_value.delete = AsyncMock(
                side_effect=ResourceNotFoundError("category", str(uuid.uuid4()))
            )
            with pytest.raises(ResourceNotFoundError):
                await delete_category(category_id=uuid.uuid4(), user=_user(), db=db)
        db.commit.assert_not_awaited()


class TestDetail:
    async def test_it_bundles_children_comments_and_history(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.get = AsyncMock(
                return_value=TicketBundle(ticket=_row(), children=[_row()], comments=[], events=[])
            )
            detail = await get_ticket(ticket_id=uuid.uuid4(), user=_user(), db=db)
        assert len(detail.children) == 1
        db.commit.assert_not_awaited()


class TestWrites:
    async def test_create_commits(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.create = AsyncMock(return_value=_row())
            await create_ticket(payload=TicketCreate(title="t"), user=_user(), db=db)
        db.commit.assert_awaited_once()

    async def test_update_commits(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.update = AsyncMock(return_value=_row())
            service_cls.return_value.assignment_notices = []
            await update_ticket(
                ticket_id=uuid.uuid4(), payload=TicketUpdate(priority="high"), user=_user(), db=db
            )
        db.commit.assert_awaited_once()

    @pytest.mark.parametrize("route", ["update", "comment"])
    async def test_a_handover_notice_leaves_only_after_the_commit(self, route: str) -> None:
        """Sent under the mutation fence, a notice's own claim waited for the
        accounts' rows the request held: production deadlock, 2026-10-21."""
        order: list[str] = []
        db = AsyncMock()
        db.commit.side_effect = lambda: order.append("commit")
        notices = [SimpleNamespace(recipient_id=uuid.uuid4())]

        async def dispatched(collected: list[Any]) -> bool:
            assert collected is notices
            order.append("dispatch")
            return True

        comment = SimpleNamespace(
            id=uuid.uuid4(),
            author_kind="user",
            author_user_id=uuid.uuid4(),
            body="OK",
            run_id=None,
            created_at=datetime.now(UTC),
        )
        with (
            _service() as service_cls,
            patch(
                "src.domains.workboard.router.dispatch_committed_assignment_notices",
                side_effect=dispatched,
            ),
        ):
            service_cls.return_value.update = AsyncMock(return_value=_row())
            service_cls.return_value.comment = AsyncMock(return_value=comment)
            service_cls.return_value.assignment_notices = notices
            if route == "update":
                await update_ticket(
                    ticket_id=uuid.uuid4(),
                    payload=TicketUpdate(assignee_user_id=uuid.uuid4()),
                    user=_user(),
                    db=db,
                )
            else:
                await add_comment(
                    ticket_id=uuid.uuid4(), payload=CommentCreate(body="OK"), user=_user(), db=db
                )
        assert order == ["commit", "dispatch"]

    async def test_move_commits_and_returns_the_moved_row(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.move = AsyncMock(return_value=_row(status="done"))
            row = await move_ticket(
                ticket_id=uuid.uuid4(),
                payload=MoveRequest(status="done", position=0),
                user=_user(),
                db=db,
            )
        assert row.status == "done"
        db.commit.assert_awaited_once()

    async def test_run_now_commits(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.run_now = AsyncMock(return_value=_row())
            await run_ticket_now(ticket_id=uuid.uuid4(), user=_user(), db=db)
        db.commit.assert_awaited_once()

    async def test_comment_commits(self) -> None:
        db = AsyncMock()
        comment = SimpleNamespace(
            id=uuid.uuid4(),
            author_kind="user",
            author_user_id=uuid.uuid4(),
            body="Noted.",
            run_id=None,
            created_at=datetime.now(UTC),
        )
        with _service() as service_cls:
            service_cls.return_value.comment = AsyncMock(return_value=comment)
            service_cls.return_value.assignment_notices = []
            await add_comment(
                ticket_id=uuid.uuid4(), payload=CommentCreate(body="Noted."), user=_user(), db=db
            )
        db.commit.assert_awaited_once()

    async def test_delete_reports_what_it_removed(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.delete = AsyncMock(return_value=3)
            result = await delete_ticket(ticket_id=uuid.uuid4(), user=_user(), db=db)
        assert result.removed == 3
        db.commit.assert_awaited_once()


class TestFailuresCommitNothing:
    """Every refusal in this domain is raised AFTER the service mutated the row
    it loaded, so a commit on the way out would persist half a change."""

    @pytest.mark.parametrize(
        ("method", "call"),
        [
            (
                "create",
                lambda db, user: create_ticket(payload=TicketCreate(title="t"), user=user, db=db),
            ),
            (
                "update",
                lambda db, user: update_ticket(
                    ticket_id=uuid.uuid4(), payload=TicketUpdate(status="done"), user=user, db=db
                ),
            ),
            (
                "move",
                lambda db, user: move_ticket(
                    ticket_id=uuid.uuid4(),
                    payload=MoveRequest(status="done", position=0),
                    user=user,
                    db=db,
                ),
            ),
            ("run_now", lambda db, user: run_ticket_now(ticket_id=uuid.uuid4(), user=user, db=db)),
            (
                "comment",
                lambda db, user: add_comment(
                    ticket_id=uuid.uuid4(), payload=CommentCreate(body="x"), user=user, db=db
                ),
            ),
            ("delete", lambda db, user: delete_ticket(ticket_id=uuid.uuid4(), user=user, db=db)),
        ],
    )
    async def test_an_unknown_ticket_commits_nothing(self, method: str, call: Any) -> None:
        db = AsyncMock()
        user = _user()
        with _service() as service_cls:
            setattr(
                service_cls.return_value,
                method,
                AsyncMock(side_effect=ResourceNotFoundError("ticket", uuid.uuid4())),
            )
            with pytest.raises(ResourceNotFoundError):
                await call(db, user)
        db.commit.assert_not_awaited()


class TestNeedsMe:
    async def test_it_carries_the_exact_total(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.needs_me = AsyncMock(
                return_value=([_row(status="waiting")], 4)
            )
            user = _user()
            criteria = DisplayQuery(q="ticket", sort="name")
            page = await needs_me(limit=20, offset=0, criteria=criteria, user=user, db=db)
        service_cls.return_value.needs_me.assert_awaited_once_with(
            user, limit=20, offset=0, criteria=criteria
        )
        assert page.total == 4
        assert len(page.tickets) == 1
        assert page.categories == {}
        db.commit.assert_not_awaited()

    async def test_it_names_the_categories_its_tickets_are_filed_under(self) -> None:
        """The hub shows the lane as a badge: the name travels with the page."""
        db = AsyncMock()
        home = uuid.uuid4()
        row = _row(status="waiting", category_id=home)
        user = _user()
        with (
            _service() as service_cls,
            patch("src.domains.workboard.router.WorkboardCategoryService") as categories_cls,
        ):
            service_cls.return_value.needs_me = AsyncMock(return_value=([row], 1))
            categories_cls.return_value.names_for = AsyncMock(return_value={home: "Home"})
            page = await needs_me(limit=20, offset=0, criteria=DisplayQuery(), user=user, db=db)
        categories_cls.return_value.names_for.assert_awaited_once_with(user.id, [row])
        assert page.categories == {home: "Home"}
        assert page.tickets[0].category_id == home


class TestSummary:
    async def test_it_hands_the_caller_down_and_never_commits(self) -> None:
        db = AsyncMock()
        user = _user()
        figures = BoardSummary(
            total=5,
            counts_by_status={"todo": 4, "done": 1},
            overdue=1,
            held_by_lia=2,
            held_by_me=3,
            needs_me=1,
            owned=4,
            max_tickets=200,
            max_runs_per_ticket=10,
            runs_total=6,
            tokens_in=1000,
            tokens_out=200,
            tokens_cache=50,
            google_requests=3,
            cost_eur=0.42,
        )
        with _service() as service_cls:
            service_cls.return_value.summary = AsyncMock(return_value=figures)
            payload = await board_summary(user=user, db=db)

        assert payload == figures
        service_cls.return_value.summary.assert_awaited_once_with(user)
        db.commit.assert_not_awaited()
