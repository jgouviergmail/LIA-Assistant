"""Cancellation cannot release the capture transaction while its disk write runs."""

import asyncio
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from src.domains.meetings.audio_store import MeetingAudioStore

pytestmark = pytest.mark.unit


async def test_repeated_cancellation_waits_for_one_disk_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = Event(), Event()
    writes: list[Path] = []
    original = Path.write_bytes

    def writing(path: Path, data: bytes) -> int:
        writes.append(path)
        entered.set()
        assert release.wait(3), "The controlled write was never released"
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", writing)
    store = MeetingAudioStore(tmp_path)
    owner, identity = uuid4(), uuid4()
    pending = asyncio.create_task(store.write_segment(owner, identity, 0, b"captured-audio"))
    assert await asyncio.to_thread(entered.wait, 3)
    try:
        for _ in range(2):
            pending.cancel()
            await asyncio.sleep(0)
        assert (
            not pending.done()
        ), "Cancellation released the caller before the disk effect completed"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert len(writes) == 1
    assert store.segment_path(owner, identity, 0).read_bytes() == b"captured-audio"
