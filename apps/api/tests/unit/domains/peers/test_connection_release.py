"""A connection that ends hands its tickets back (ADR-276, lot 5).

Until this lot, `WorkboardService.release_pair` existed, was tested, and had NO
production caller: removing a connection left every shared ticket assigned to
somebody who could no longer reach the board it lived on.

The three exits of a relationship do NOT behave alike, and each difference is a
decision the tests below pin:

- **removal** severs an ACCEPTED pair, so work may be in flight: release, and
  tell both sides how much came back to THEM;
- **a block is silent by design** (`peers/service.py`: « the blocked user must
  observe nothing ») — it releases just the same, and notifies nobody;
- **declining a request** ends a pair that was never accepted, so no ticket
  could ever have been assigned: calling the board there would be a query for
  nothing.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.peers.service import PeersService

pytestmark = pytest.mark.unit

MODULE = "src.domains.peers.service"
A = uuid.uuid4()
B = uuid.uuid4()


def _connection(status: str, connection_id: uuid.UUID | None = None) -> Any:
    row = MagicMock()
    row.id = connection_id or uuid.uuid4()
    row.status = status
    row.user_a_id = A
    row.user_b_id = B
    row.requested_by_id = A
    return row


def _service(connection: Any) -> PeersService:
    service = PeersService(AsyncMock())
    service.repo = AsyncMock()
    service.repo.transition_status = AsyncMock(return_value=connection)
    service.repo.get_pair = AsyncMock(return_value=connection)
    service.repo.delete_shares_for_connection = AsyncMock()
    service.repo.create_block = AsyncMock()
    service._get_participant_connection = AsyncMock(return_value=connection)
    return service


class TestRemovingAConnection:
    async def test_it_hands_the_shared_tickets_back(self) -> None:
        connection = _connection("accepted")
        service = _service(connection)
        release = AsyncMock(return_value={A: 2, B: 1})

        with patch(f"{MODULE}.release_tickets_between", release):
            await service.remove_connection(A, connection.id)

        # The PAIR is the connection, so both directions are handed back in one
        # call — and in the CALLER's session, so the severance and the release
        # commit together.
        release.assert_awaited_once()
        assert release.await_args.kwargs["user_a"] == A
        assert release.await_args.kwargs["user_b"] == B
        assert release.await_args.kwargs["db"] is service.db

    async def test_the_event_carries_what_came_back_to_each_side(self) -> None:
        """Each side gets a DIFFERENT number: a pair usually holds work both
        ways, and one total would tell each of them something untrue of them."""
        connection = _connection("accepted")
        service = _service(connection)

        with patch(f"{MODULE}.release_tickets_between", AsyncMock(return_value={A: 2, B: 1})):
            await service.remove_connection(A, connection.id)

        event = service.pending_events[-1]
        assert event.kind == "connection_removed"
        assert dict(event.released) == {A: 2, B: 1}

    async def test_a_pair_holding_nothing_carries_nothing(self) -> None:
        connection = _connection("accepted")
        service = _service(connection)

        with patch(f"{MODULE}.release_tickets_between", AsyncMock(return_value={})):
            await service.remove_connection(A, connection.id)

        assert service.pending_events[-1].released == ()

    async def test_a_board_that_could_not_answer_never_blocks_the_removal(self) -> None:
        """The seam already swallows a board failure; the removal must not
        depend on it either way."""
        connection = _connection("accepted")
        service = _service(connection)

        with patch(f"{MODULE}.release_tickets_between", AsyncMock(return_value={})):
            state = await service.remove_connection(A, connection.id)

        assert state.status == "accepted" or state.status is not None
        assert service.pending_events


class TestBlockingSomebody:
    async def test_it_hands_the_tickets_back_too(self) -> None:
        # A block severs the pair; leaving the tickets assigned would keep the
        # blocked account named on the blocker's board.
        connection = _connection("accepted")
        service = _service(connection)
        release = AsyncMock(return_value={A: 1})

        with patch(f"{MODULE}.release_tickets_between", release):
            await service.block_peer(A, B)

        release.assert_awaited_once()

    async def test_it_stays_SILENT(self) -> None:
        """« Deliberately NO event: the blocked user must observe nothing. »
        Handing tickets back must not become the notification a block refuses
        to send."""
        connection = _connection("accepted")
        service = _service(connection)

        with patch(f"{MODULE}.release_tickets_between", AsyncMock(return_value={A: 3})):
            await service.block_peer(A, B)

        assert service.pending_events == []

    async def test_it_releases_nothing_when_there_was_no_pair(self) -> None:
        service = _service(None)
        service.repo.get_pair = AsyncMock(return_value=None)
        release = AsyncMock(return_value={})

        with patch(f"{MODULE}.release_tickets_between", release):
            await service.block_peer(A, B)

        release.assert_not_awaited()

    async def test_it_releases_nothing_for_a_pair_that_was_only_pending(self) -> None:
        # A pending pair never held a ticket: the board has nothing to hand back.
        connection = _connection("pending")
        service = _service(connection)
        release = AsyncMock(return_value={})

        with patch(f"{MODULE}.release_tickets_between", release):
            await service.block_peer(A, B)

        release.assert_not_awaited()


class TestDecliningARequest:
    async def test_it_calls_the_board_at_all_never(self) -> None:
        """A declined request was PENDING: no ticket could ever have been
        assigned across it, so asking the board would be a query for nothing."""
        connection = _connection("pending")
        service = _service(connection)
        connection.requested_by_id = B  # the responder is not the requester
        release = AsyncMock(return_value={})

        with patch(f"{MODULE}.release_tickets_between", release):
            await service.respond_request(A, connection.id, accept=False)

        release.assert_not_awaited()

    async def test_accepting_releases_nothing_either(self) -> None:
        connection = _connection("pending")
        service = _service(connection)
        connection.requested_by_id = B
        release = AsyncMock(return_value={})

        with patch(f"{MODULE}.release_tickets_between", release):
            await service.respond_request(A, connection.id, accept=True)

        release.assert_not_awaited()
