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
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.workboard.router import (
    add_comment,
    board_summary,
    create_ticket,
    delete_ticket,
    get_ticket,
    list_board,
    move_ticket,
    needs_me,
    run_ticket_now,
    update_ticket,
)
from src.domains.workboard.schemas import (
    BoardSummary,
    CommentCreate,
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
        "last_run_cost_eur": None,
        "execution_mode": "react",
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "total_tokens_cache": 0,
        "total_google_requests": 0,
        "total_cost_eur": 0.0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _service() -> Any:
    """Patch the service the router constructs, and hand back the instance."""
    return patch("src.domains.workboard.router.WorkboardService")


class TestBoard:
    async def test_it_returns_the_page_the_total_and_the_counts(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(
                return_value=([_row()], 7, {"todo": 7, "done": 0})
            )
            page = await list_board(
                status=None,
                assignee="all",
                priority=None,
                overdue=False,
                due_before=None,
                q=None,
                closed_days=None,
                sort="position",
                limit=50,
                offset=0,
                user=_user(),
                db=db,
            )
        assert page.total == 7
        assert page.counts_by_status["todo"] == 7
        assert len(page.tickets) == 1

    async def test_a_read_never_commits(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await list_board(
                status=None,
                assignee="all",
                priority=None,
                overdue=False,
                due_before=None,
                q=None,
                closed_days=None,
                sort="position",
                limit=50,
                offset=0,
                user=_user(),
                db=db,
            )
        db.commit.assert_not_awaited()

    async def test_closed_days_becomes_an_instant_the_repository_can_compare(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await list_board(
                status=None,
                assignee="all",
                priority=None,
                overdue=False,
                due_before=None,
                q=None,
                closed_days=30,
                sort="position",
                limit=50,
                offset=0,
                user=_user(),
                db=db,
            )
            filters = service_cls.return_value.board.await_args.args[1]
        assert filters.include_closed_before is not None
        assert filters.include_closed_before.tzinfo is not None, "UTC-aware, never naive"

    async def test_zero_closed_days_still_bounds_the_read(self) -> None:
        """0 means « hide everything already closed », not « no filter »."""
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await list_board(
                status=None,
                assignee="all",
                priority=None,
                overdue=False,
                due_before=None,
                q=None,
                closed_days=0,
                sort="position",
                limit=50,
                offset=0,
                user=_user(),
                db=db,
            )
            filters = service_cls.return_value.board.await_args.args[1]
        assert filters.include_closed_before is not None

    async def test_the_filters_reach_the_service_verbatim(self) -> None:
        db = AsyncMock()
        with _service() as service_cls:
            service_cls.return_value.board = AsyncMock(return_value=([], 0, {}))
            await list_board(
                status=["todo", "waiting"],
                assignee="lia",
                priority=["high"],
                overdue=True,
                due_before=datetime(2026, 9, 30, tzinfo=UTC),
                q="venue",
                closed_days=None,
                sort="due",
                limit=10,
                offset=20,
                user=_user(),
                db=db,
            )
            filters = service_cls.return_value.board.await_args.args[1]
            kwargs = service_cls.return_value.board.await_args.kwargs
        assert filters.statuses == ("todo", "waiting")
        assert filters.assignee == "lia"
        assert filters.priorities == ("high",)
        assert filters.overdue is True
        assert filters.query == "venue"
        assert filters.sort == "due"
        assert kwargs == {"limit": 10, "offset": 20}


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
            await update_ticket(
                ticket_id=uuid.uuid4(), payload=TicketUpdate(priority="high"), user=_user(), db=db
            )
        db.commit.assert_awaited_once()

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
            page = await needs_me(limit=20, offset=0, user=_user(), db=db)
        assert page.total == 4
        assert len(page.tickets) == 1
        db.commit.assert_not_awaited()


class TestSummary:
    async def test_it_hands_the_caller_down_and_never_commits(self) -> None:
        db = AsyncMock()
        user = _user()
        figures = BoardSummary(
            total=5,
            counts_by_status={"todo": 4, "done": 1},
            overdue=1,
            held_by_lia=2,
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
