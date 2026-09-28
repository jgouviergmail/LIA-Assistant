"""The radio keeps nothing: a session's audio goes with it, a crash's leftovers go too."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from src.domains.radio.media import (
    discard,
    prepare,
    segment_path,
    session_dir,
    sweep_orphans,
)

pytestmark = pytest.mark.unit


async def test_a_session_writes_under_its_own_directory_and_leaves_nothing(
    tmp_path: Path,
) -> None:
    session = uuid4()
    directory = await prepare(tmp_path / "radio", session)
    path = segment_path(tmp_path / "radio", session, 3)
    assert path.parent == directory and path.name == "0003.mp3"
    path.write_bytes(b"mp3")

    await discard(tmp_path / "radio", session)
    await discard(tmp_path / "radio", session)  # twice is harmless
    assert not directory.exists()


def test_a_place_starts_at_one() -> None:
    with pytest.raises(ValueError):
        segment_path(Path("/media"), uuid4(), 0)


async def test_the_sweep_removes_only_abandoned_session_directories(tmp_path: Path) -> None:
    live, crashed, fresh = uuid4(), uuid4(), uuid4()
    for session in (live, crashed, fresh):
        await prepare(tmp_path, session)
    foreign = tmp_path / "not-a-session"
    foreign.mkdir()
    old = 1_000_000.0
    for directory in (session_dir(tmp_path, live), session_dir(tmp_path, crashed), foreign):
        os.utime(directory, (old, old))
    now = old + 7200

    removed = await sweep_orphans(tmp_path, live={live}, older_than_s=3600, now=now)

    assert removed == 1
    assert not session_dir(tmp_path, crashed).exists()
    assert session_dir(tmp_path, live).exists()  # running: never swept
    assert foreign.exists()  # never ours to remove


async def test_a_directory_that_vanishes_while_the_sweep_lists_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session ending (its loop discards) while the sweep lists: the rest is swept."""
    vanished, crashed = uuid4(), uuid4()
    for session in (vanished, crashed):
        await prepare(tmp_path, session)
    old = 1_000_000.0
    os.utime(session_dir(tmp_path, crashed), (old, old))
    real_stat = Path.stat

    def racing_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self.name == str(vanished):
            raise FileNotFoundError(self)
        return real_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", racing_stat)
    removed = await sweep_orphans(tmp_path, live=set(), older_than_s=3600, now=old + 7200)

    assert removed == 1
    assert not session_dir(tmp_path, crashed).exists()


async def test_a_missing_root_is_nothing_to_sweep(tmp_path: Path) -> None:
    assert await sweep_orphans(tmp_path / "absent", live=(), older_than_s=60) == 0
