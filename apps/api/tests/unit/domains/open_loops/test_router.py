"""Unit tests for the Open Loops router endpoints (P5, Lot 2)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import ResourceNotFoundError
from src.domains.open_loops.models import OpenLoopStatus
from src.domains.open_loops.router import close_open_loop, list_open_loops
from src.domains.open_loops.schemas import CloseLoopRequest


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

    async def test_close_dismissed_action_maps_to_dismissed_reason(self):
        # UXR Lot 7 (B5): "plus d'actualité" records closed_reason=dismissed.
        closed_row = _loop_row(status="closed", closed_reason="dismissed")
        repo = MagicMock()
        repo.close_loop = AsyncMock(return_value=True)
        repo.get_by_id = AsyncMock(return_value=closed_row)
        db = MagicMock()
        db.commit = AsyncMock()
        user = _user()

        with patch("src.domains.open_loops.router.OpenLoopRepository", return_value=repo):
            await close_open_loop(
                closed_row.id,
                payload=CloseLoopRequest(action="dismissed"),
                user=user,
                db=db,
            )

        repo.close_loop.assert_awaited_once_with(closed_row.id, user.id, reason="dismissed")

    async def test_close_request_schema_rejects_foreign_reasons(self):
        # conversational/expired belong to the extractor and the lazy expiry.
        with pytest.raises(ValidationError):
            CloseLoopRequest(action="conversational")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            CloseLoopRequest(action="expired")  # type: ignore[arg-type]
        assert CloseLoopRequest().action == "done"


@pytest.mark.unit
class TestUpdateOpenLoop:
    """Editing a commitment the extractor got wrong (2026-08-02).

    The ledger fills itself from conversation, and conversation is approximate:
    a subject comes out garbled, "d'ici vendredi" lands on the wrong Friday.
    Only `subject` and `due_hint` are editable — changing the direction or the
    counterparty describes a DIFFERENT commitment, not a correction.
    """

    async def test_updates_and_returns_the_fresh_row(self):
        from src.domains.open_loops.router import update_open_loop
        from src.domains.open_loops.schemas import UpdateLoopRequest

        user = _user()
        loop_id = uuid4()
        row = _loop_row(id=loop_id, subject="rappeler le plombier mardi")
        with patch("src.domains.open_loops.router.OpenLoopRepository") as repo_cls:
            repo = repo_cls.return_value
            repo.update_loop = AsyncMock(return_value=True)
            repo.get_by_id = AsyncMock(return_value=row)
            db = MagicMock()
            db.commit = AsyncMock()

            result = await update_open_loop(
                loop_id,
                UpdateLoopRequest(subject="rappeler le plombier mardi"),
                user=user,
                db=db,
            )

        assert result.subject == "rappeler le plombier mardi"
        db.commit.assert_awaited_once()

    async def test_a_loop_that_cannot_be_claimed_is_a_404(self):
        """Closed, expired or someone else's — same answer, existence hidden."""
        from src.domains.open_loops.router import update_open_loop
        from src.domains.open_loops.schemas import UpdateLoopRequest

        with patch("src.domains.open_loops.router.OpenLoopRepository") as repo_cls:
            repo_cls.return_value.update_loop = AsyncMock(return_value=False)
            db = MagicMock()
            db.commit = AsyncMock()

            with pytest.raises(ResourceNotFoundError):
                await update_open_loop(uuid4(), UpdateLoopRequest(subject="x"), user=_user(), db=db)

    async def test_an_empty_subject_is_rejected_by_the_schema(self):
        """A commitment with no wording says nothing to anyone."""
        from src.domains.open_loops.schemas import UpdateLoopRequest

        with pytest.raises(ValidationError):
            UpdateLoopRequest(subject="   ")

    async def test_clearing_the_deadline_is_distinct_from_leaving_it_alone(self):
        """`None` cannot express both "unchanged" and "no deadline after all"."""
        from src.domains.open_loops.schemas import UpdateLoopRequest

        assert UpdateLoopRequest(subject="x").clear_due_hint is False
        assert UpdateLoopRequest(clear_due_hint=True).clear_due_hint is True
