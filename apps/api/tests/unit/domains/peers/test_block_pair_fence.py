"""Every source block/unblock mutation uses the same canonical pair fence as World games."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.peers import service as peers_module
from src.domains.peers.service import PeersService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("blocked", [True, False])
async def test_canonical_pair_is_locked_before_any_source_block_mutation(
    monkeypatch: pytest.MonkeyPatch, blocked: bool
) -> None:
    events: list[str] = []
    owner, peer = uuid4(), uuid4()
    db, repository = AsyncMock(), AsyncMock()
    repository.get_pair.return_value = None

    async def lock(session, first, second) -> None:
        assert session is db and (first, second) == (owner, peer)
        events.append("lock")

    async def mutate(*_args):
        events.append("mutation")
        return True

    monkeypatch.setattr(peers_module, "lock_peer_pair", lock)
    repository.create_block.side_effect = mutate
    repository.delete_block.side_effect = mutate
    source = PeersService(db)
    source.repo = repository
    if blocked:
        await source.block_peer(owner, peer)
    else:
        assert await source.unblock_peer(owner, peer)
    assert events == ["lock", "mutation"]
    assert source.pending_events == []
