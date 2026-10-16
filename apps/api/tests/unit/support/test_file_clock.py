"""The rewrite a stat identity always sees, whatever the filesystem's clock tick."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.file_transfer import LocalFileRead
from tests.support.file_clock import PAST_ANY_TICK_NS, rewrite_later

pytestmark = pytest.mark.unit

#: Rounds per test. A plain same-size rewrite kept its stat identity in 3 rounds
#: of 4 on Windows (2026-10-16), so a single passing round would prove nothing.
ROUNDS = 200


async def _identity(path: Path) -> str:
    """The identity the stored-file checks compare: ``LocalFileRead.identity_digest``."""
    reader = LocalFileRead.open(path)
    try:
        return reader.identity_digest
    finally:
        await reader.close()


async def test_a_same_size_rewrite_changes_the_identity_every_time(tmp_path: Path) -> None:
    """Same path, same size, new bytes: the identity moves on every round."""
    path = tmp_path / "stored.txt"
    for round_ in range(ROUNDS):
        path.write_bytes(b"data")
        observed = await _identity(path)
        rewrite_later(path, b"new!")
        assert path.read_bytes() == b"new!"
        assert await _identity(path) != observed, f"identity unchanged at round {round_}"


def test_the_rewrite_lands_past_any_tick_of_the_observed_write(tmp_path: Path) -> None:
    """The modification time moves forward by at least the coarsest tick, never back."""
    path = tmp_path / "stored.txt"
    path.write_bytes(b"data")
    observed = path.stat().st_mtime_ns
    rewrite_later(path, b"new!")
    assert path.stat().st_mtime_ns - observed >= PAST_ANY_TICK_NS
