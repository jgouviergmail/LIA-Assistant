"""A group quarantine is reversible, scope-safe and never overwrites a replacement."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.plugins.removal import _restore
from src.domains.plugins.removal_disk import (
    RemovalMove,
    cleanup_quarantine,
    restore_moves,
    stage_moves,
)
from src.domains.user_mcp.service import UserMCPServerService

pytestmark = pytest.mark.unit


def _move(tmp_path: Path) -> RemovalMove:
    source = tmp_path / "account" / "plugin"
    source.mkdir(parents=True)
    (source / "file").write_bytes(b"original")
    stat = source.stat()
    return RemovalMove(
        source, source.parent / ".lia-removal" / "attempt" / source.name, (stat.st_dev, stat.st_ino)
    )


def test_refused_restore_preserves_both_old_and_new_trees(tmp_path: Path) -> None:
    move = _move(tmp_path)
    stage_moves((move,))
    move.source.mkdir()
    (move.source / "file").write_bytes(b"replacement")
    with pytest.raises(ValueError):
        restore_moves((move,))
    assert (move.source / "file").read_bytes() == b"replacement"
    assert (move.destination / "file").read_bytes() == b"original"


@pytest.mark.parametrize("operation", [stage_moves, restore_moves, cleanup_quarantine])
def test_outside_account_destination_is_refused(tmp_path: Path, operation) -> None:
    move = _move(tmp_path)
    outside = tmp_path / "other"
    outside.mkdir()
    (outside / "file").write_bytes(b"other account")
    unsafe = RemovalMove(move.source, outside, move.identity)
    with pytest.raises(ValueError):
        operation((unsafe,))
    assert (outside / "file").read_bytes() == b"other account"
    assert (move.source / "file").read_bytes() == b"original"


@pytest.mark.asyncio
async def test_strict_pool_cleanup_does_not_hide_a_real_disconnect_failure() -> None:
    pool = MagicMock()
    pool.disconnect = AsyncMock(side_effect=ConnectionError("transport unavailable"))
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        with pytest.raises(ConnectionError):
            await UserMCPServerService._disconnect_from_pool(uuid4(), uuid4(), strict=True)
        await UserMCPServerService._disconnect_from_pool(uuid4(), uuid4())
    assert pool.disconnect.await_count == 2


@pytest.mark.asyncio
async def test_cancellation_during_sql_rollback_still_restores_the_files(tmp_path: Path) -> None:
    move = _move(tmp_path)
    stage_moves((move,))
    started = asyncio.Event()

    async def rollback() -> None:
        started.set()
        await asyncio.Event().wait()

    db = MagicMock()
    db.rollback = AsyncMock(side_effect=rollback)
    task = asyncio.create_task(_restore(db, (move,)))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (move.source / "file").read_bytes() == b"original"
    assert not move.destination.exists()
