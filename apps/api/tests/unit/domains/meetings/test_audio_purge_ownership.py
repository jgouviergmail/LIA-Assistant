"""A directory link cannot redirect meeting cleanup to another owned meeting."""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from src.domains.meetings.audio_store import MeetingAudioStore

pytestmark = pytest.mark.unit


async def test_meeting_purge_refuses_another_directory_in_the_same_storage_root(
    tmp_path: Path,
) -> None:
    owner, selected, other = uuid4(), uuid4(), uuid4()
    root = tmp_path.resolve()
    account = root / str(owner)
    target = account / str(other)
    target.mkdir(parents=True)
    kept = target / "private.webm"
    kept.write_bytes(b"private")
    link = account / str(selected)
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True
        )
    else:
        link.symlink_to(target, target_is_directory=True)
    await MeetingAudioStore(root).purge_meeting(owner, selected)
    assert kept.read_bytes() == b"private"


async def test_repeated_cancellation_waits_for_one_owned_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, identity = uuid4(), uuid4()
    target = tmp_path / str(owner) / str(identity)
    target.mkdir(parents=True)
    (target / "audio.webm").write_bytes(b"selected")
    entered, release, finished = Event(), Event(), Event()
    original = shutil.rmtree
    calls: list[Path] = []

    def remove(path: Path) -> None:
        calls.append(path)
        entered.set()
        assert release.wait(3)
        try:
            original(path)
        finally:
            finished.set()

    monkeypatch.setattr(shutil, "rmtree", remove)
    pending = asyncio.create_task(MeetingAudioStore(tmp_path).purge_meeting(owner, identity))
    assert await asyncio.to_thread(entered.wait, 3)
    try:
        for _ in range(2):
            pending.cancel()
            await asyncio.sleep(0)
        assert not pending.done(), "Cleanup owner returned while disk deletion still ran"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert await asyncio.to_thread(finished.wait, 3)
    assert calls == [target] and not target.exists()
