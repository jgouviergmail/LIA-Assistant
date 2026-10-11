"""A cancelled asynchronous copy must await its thread before deleting the file."""

import asyncio
import threading
from pathlib import Path

import pytest

from src.domains.peers import image_share

pytestmark = pytest.mark.unit


async def test_cancelled_copy_waits_for_worker_and_withdraws_file(tmp_path: Path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    source, target = tmp_path / "source.png", tmp_path / "copy.png"
    source.write_bytes(b"source bytes")

    def slow_copy(first: Path, second: Path) -> None:
        started.set()
        assert release.wait(timeout=5)
        second.write_bytes(first.read_bytes())

    monkeypatch.setattr(image_share, "_copy_file", slow_copy)
    copy = asyncio.create_task(image_share._copy_without_abandoning_file(source, target))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        copy.cancel()
        await asyncio.sleep(0)
        assert not copy.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await copy
    assert source.read_bytes() == b"source bytes"
    assert not target.exists()
