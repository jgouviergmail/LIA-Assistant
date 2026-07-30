"""Peers error-code contract (Lot 1, Task 8).

The /peers surface reports guard failures as STABLE machine codes in the
error detail (label-key doctrine: the frontend maps codes to localized
strings — Lot 2 owns the 6-language translations). Renaming a code silently
breaks every locale at once, so each code is pinned here by triggering its
guard.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.peers.models import PeerConnectionStatus, PeerShareDomain, PeerShareLevel
from src.domains.peers.service import PeersService

USER = uuid4()
OTHER = uuid4()


def _service() -> PeersService:
    service = PeersService(db=AsyncMock())
    service.repo = AsyncMock()
    service.repo.has_block_between.return_value = False
    service.repo.get_pair.return_value = None
    service._get_discoverable_user = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(id=OTHER, full_name="Peer", email="p@test.local")
    )
    return service


def _row(status: PeerConnectionStatus, requested_by=USER) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_a_id=min(USER, OTHER),
        user_b_id=max(USER, OTHER),
        requested_by_id=requested_by,
        status=status.value,
        context_message=None,
        requested_at=None,
        responded_at=None,
        removed_at=None,
    )


async def _detail_of(coro) -> str:
    with pytest.raises(BaseAPIException) as exc:
        await coro
    detail = exc.value.detail
    assert isinstance(detail, str)
    return detail


@pytest.mark.unit
class TestErrorCodeContract:
    """Each guard reports its pinned machine code (frontend translation keys)."""

    async def test_peers_self_request(self):
        assert await _detail_of(_service().request_connection(USER, USER, None)) == (
            "peers_self_request"
        )

    async def test_peers_context_message_too_long(self):
        from src.core.constants import PEERS_CONTEXT_MESSAGE_MAX_CHARS

        service = _service()
        detail = await _detail_of(
            service.request_connection(USER, OTHER, "x" * (PEERS_CONTEXT_MESSAGE_MAX_CHARS + 1))
        )
        assert detail == "peers_context_message_too_long"

    async def test_peers_already_connected(self):
        service = _service()
        service.repo.get_pair.return_value = _row(PeerConnectionStatus.ACCEPTED)
        detail = await _detail_of(service.request_connection(USER, OTHER, None))
        assert detail == "peers_already_connected"

    async def test_peers_not_pending(self):
        service = _service()
        service.repo.get_by_id = AsyncMock(return_value=_row(PeerConnectionStatus.ACCEPTED))
        detail = await _detail_of(service.respond_request(USER, uuid4(), accept=True))
        assert detail == "peers_not_pending"

    async def test_peers_not_connected_on_remove(self):
        service = _service()
        service.repo.get_by_id = AsyncMock(return_value=_row(PeerConnectionStatus.PENDING))
        detail = await _detail_of(service.remove_connection(USER, uuid4()))
        assert detail == "peers_not_connected"

    async def test_peers_invalid_share_level(self):
        service = _service()
        service.repo.get_by_id = AsyncMock(return_value=_row(PeerConnectionStatus.ACCEPTED))
        detail = await _detail_of(
            service.set_share(USER, uuid4(), PeerShareDomain.TASK, PeerShareLevel.DETAILS)
        )
        assert detail == "peers_invalid_share_level"

    async def test_peers_self_block(self):
        assert await _detail_of(_service().block_peer(USER, USER)) == "peers_self_block"
