"""Unit tests for the Open Loops router endpoints (P5, Lot 2)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.open_loops.models import OpenLoopStatus
from src.domains.open_loops.router import close_open_loop, list_open_loops


def _user():
    return SimpleNamespace(id=uuid4())


def _loop_row(**overrides):
    from datetime import UTC, datetime

    defaults = {
        "id": uuid4(),
        "subject": "rappeler le plombier",
        "counterparty": "le plombier",
        "direction": "user_owes",
        "due_hint": None,
        "status": "open",
        "closed_reason": None,
        "nudge_count": 0,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
class TestListOpenLoops:
    async def test_lists_with_status_filter(self):
        repo = MagicMock()
        repo.list_for_user = AsyncMock(return_value=[_loop_row()])

        with patch("src.domains.open_loops.router.OpenLoopRepository", return_value=repo):
            response = await list_open_loops(
                status=OpenLoopStatus.OPEN, user=_user(), db=MagicMock()
            )

        assert response.total == 1
        assert response.items[0].subject == "rappeler le plombier"
        assert repo.list_for_user.await_args.kwargs["status"] == "open"

    async def test_lists_all_without_filter(self):
        repo = MagicMock()
        repo.list_for_user = AsyncMock(return_value=[])

        with patch("src.domains.open_loops.router.OpenLoopRepository", return_value=repo):
            response = await list_open_loops(status=None, user=_user(), db=MagicMock())

        assert response.total == 0
        assert repo.list_for_user.await_args.kwargs["status"] is None


@pytest.mark.unit
class TestCloseOpenLoop:
    async def test_close_success_returns_closed_loop(self):
        closed_row = _loop_row(status="closed", closed_reason="api")
        repo = MagicMock()
        repo.close_loop = AsyncMock(return_value=True)
        repo.get_by_id = AsyncMock(return_value=closed_row)
        db = MagicMock()
        db.commit = AsyncMock()
        user = _user()

        with patch("src.domains.open_loops.router.OpenLoopRepository", return_value=repo):
            response = await close_open_loop(closed_row.id, user=user, db=db)

        assert response.status == "closed"
        repo.close_loop.assert_awaited_once_with(closed_row.id, user.id, reason="api")
        db.commit.assert_awaited_once()

    async def test_close_missing_or_foreign_returns_404(self):
        repo = MagicMock()
        repo.close_loop = AsyncMock(return_value=False)

        with (
            patch("src.domains.open_loops.router.OpenLoopRepository", return_value=repo),
            pytest.raises(ResourceNotFoundError),
        ):
            await close_open_loop(uuid4(), user=_user(), db=MagicMock())
