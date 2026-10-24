"""The publication fence moves the archive off the event loop and never half-publishes it (AC-035).

``publish_archive`` holds the account's and the job's rows locked while it renames
the built archive into place. The rename, the existence check and the cleanup are
disk calls: they run in a worker thread, a cancellation waits for the one in
flight, and whatever stops the fence after the rename — a cancellation, a failed
flush — takes the published file back rather than leave an archive no row points to.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.account_export.publication import publish_archive

pytestmark = pytest.mark.unit

REVISION = 3


def _fence() -> tuple[AsyncMock, SimpleNamespace]:
    """A session whose two locked reads find the live account, then its running job."""
    actor = SimpleNamespace(is_active=True, is_deleted=False, extraction_revision=REVISION)
    job = SimpleNamespace(status="running", file_path=None)
    db = AsyncMock()
    db.scalar.side_effect = [actor, job]
    return db, job


@pytest.fixture
def archive(tmp_path: Path) -> tuple[Path, Path]:
    built = tmp_path / ".job.building.zip"
    built.write_bytes(b"PK built archive")
    return built, tmp_path / "job.zip"


async def test_no_disk_call_of_the_publication_runs_on_the_loop(
    archive: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    built, final = archive
    db, job = _fence()
    calls: list[tuple[str, int]] = []
    for name in ("exists", "replace", "unlink"):
        real = getattr(Path, name)

        def recording(
            path: Path, *args: Any, _real: Any = real, _name: str = name, **kw: Any
        ) -> Any:
            if path in archive:
                calls.append((_name, threading.get_ident()))
            return _real(path, *args, **kw)

        monkeypatch.setattr(Path, name, recording)

    await publish_archive(db, uuid4(), uuid4(), REVISION, built, final)

    seen = list(calls)
    assert [name for name, _ in seen] == ["exists", "replace"]
    assert threading.get_ident() not in {thread for _, thread in seen}
    assert job.file_path == str(final)


async def test_a_cancellation_during_the_rename_publishes_nothing(
    archive: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    built, final = archive
    db, job = _fence()
    renaming, release = threading.Event(), threading.Event()
    real_replace = Path.replace

    def slow_replace(path: Path, target: Path) -> Path:
        renaming.set()
        assert release.wait(5), "the test never released the rename"
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", slow_replace)
    publication = asyncio.create_task(publish_archive(db, uuid4(), uuid4(), REVISION, built, final))
    try:
        assert await asyncio.to_thread(renaming.wait, 5), "the rename never started"
        publication.cancel()
        await asyncio.sleep(0.05)
        assert not publication.done(), "a cancellation abandoned the rename in flight"
    finally:
        release.set()
        (outcome,) = await asyncio.gather(publication, return_exceptions=True)

    assert isinstance(outcome, asyncio.CancelledError)
    assert not final.exists(), "a cancelled publication left an archive no row points to"
    assert job.file_path is None
    db.flush.assert_not_awaited()


async def test_a_failed_flush_takes_the_published_archive_back(archive: tuple[Path, Path]) -> None:
    built, final = archive
    db, job = _fence()
    db.flush.side_effect = RuntimeError("the pointer could not be written")

    with pytest.raises(RuntimeError, match="pointer"):
        await publish_archive(db, uuid4(), uuid4(), REVISION, built, final)

    assert not final.exists() and not built.exists()
