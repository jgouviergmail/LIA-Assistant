"""What the board answers when a pair ends (ADR-276, lot 5).

The adapter is the board's half of the seam: it turns the released tickets into
a count PER OWNER, because a pair usually holds work in both directions and the
pair's total would tell each side something that is not true of them.

It also owns the SAVEPOINT, so the session double below opens one rather than
being a bare object: measured 2026-09-09, a board dying half way left its
already-mutated tickets in the caller's session, which committed them while the
notification said « 0 » (ADR-185).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.workboard.release_adapter import release_tickets_between

pytestmark = pytest.mark.unit

MODULE = "src.domains.workboard.service.WorkboardService"
A = uuid.uuid4()
B = uuid.uuid4()


class _Session:
    """The caller's session, reduced to what the adapter actually uses.

    A bare ``object()`` would pass every assertion below while never entering
    the savepoint — the exact blindness that let the partial-release defect
    live. It counts the savepoints instead, and one test reads that count.
    """

    def __init__(self) -> None:
        self.savepoints = 0
        self.rolled_back = 0

    def begin_nested(self) -> Any:
        self.savepoints += 1

        @asynccontextmanager
        async def _savepoint() -> AsyncIterator[None]:
            try:
                yield None
            except BaseException:
                self.rolled_back += 1
                raise

        return _savepoint()


def _ticket(owner_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), owner_user_id=owner_id)


class TestCountingWhatCameBack:
    async def test_it_counts_per_OWNER_not_per_pair(self) -> None:
        released = [_ticket(A), _ticket(A), _ticket(B)]

        with patch(f"{MODULE}.release_pair", AsyncMock(return_value=released)):
            counts = await release_tickets_between(db=_Session(), user_a=A, user_b=B)

        assert counts == {A: 2, B: 1}

    async def test_a_pair_holding_nothing_answers_an_empty_mapping(self) -> None:
        # Never `{A: 0, B: 0}`: the caller uses « absent » to mean « say
        # nothing », and a zero would read as a fact worth a sentence.
        with patch(f"{MODULE}.release_pair", AsyncMock(return_value=[])):
            assert await release_tickets_between(db=_Session(), user_a=A, user_b=B) == {}

    async def test_it_hands_the_CALLER_session_to_the_board(self) -> None:
        """The release belongs to the same transaction as the severance that
        caused it: a connection gone while its tickets stay assigned is worse
        than either alone."""
        db = _Session()
        service = AsyncMock(return_value=[])

        with patch("src.domains.workboard.service.WorkboardService") as cls:
            cls.return_value.release_pair = service
            await release_tickets_between(db=db, user_a=A, user_b=B)

        cls.assert_called_once_with(db)
        service.assert_awaited_once_with(A, B)


class TestTheReleaseIsAllOrNothing:
    async def test_it_runs_inside_a_savepoint(self) -> None:
        """The seam above answers « nothing moved » on a failure, and that
        answer is what both sides are TOLD."""
        db = _Session()

        with patch(f"{MODULE}.release_pair", AsyncMock(return_value=[_ticket(A)])):
            await release_tickets_between(db=db, user_a=A, user_b=B)

        assert db.savepoints == 1
        assert db.rolled_back == 0

    async def test_a_board_dying_half_way_rolls_its_own_writes_back(self) -> None:
        """Measured 2026-09-09 without it: one ticket of two released, « 0 »
        announced, and the caller's commit wrote the half already mutated."""
        db = _Session()

        with patch(f"{MODULE}.release_pair", AsyncMock(side_effect=RuntimeError("half way"))):
            with pytest.raises(RuntimeError):
                await release_tickets_between(db=db, user_a=A, user_b=B)

        assert db.rolled_back == 1


class TestTheSeamIsClaimedByImportingThisModule:
    def test_the_board_is_installed(self) -> None:
        from src.domains.shared.peer_release_sink import releaser_is_installed

        assert releaser_is_installed() is True
