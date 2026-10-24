"""Building, refusing and sweeping an export make no disk call on the event loop (AC-035).

The export runs on the scheduler's loop, beside every request of the worker. Its
writes already went through ``run_disk_io``; the calls around them — preparing the
account's export directory, reading the archive's final size, removing an archive
its job refused or that expired — ran on the loop. These tests record the thread of
every path call the flow makes under the test's directory.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.account_export import builder, executor
from src.domains.account_export.models import ExportJobStatus

pytestmark = pytest.mark.unit

PATH_CALLS = ("exists", "is_symlink", "is_dir", "mkdir", "stat", "replace", "unlink")


@pytest.fixture
def disk_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Every path call made under ``tmp_path``, with the thread it ran on."""
    calls: list[tuple[str, int]] = []
    for name in PATH_CALLS:
        real = getattr(Path, name)

        def recording(
            path: Path, *args: Any, _real: Any = real, _name: str = name, **kw: Any
        ) -> Any:
            if path.is_relative_to(tmp_path):
                calls.append((_name, threading.get_ident()))
            return _real(path, *args, **kw)

        monkeypatch.setattr(Path, name, recording)
    return calls


def _session(db: AsyncMock) -> Callable[[], AbstractAsyncContextManager[AsyncMock]]:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncMock]:
        yield db

    return session


def _on_the_loop(calls: list[tuple[str, int]]) -> list[str]:
    return [name for name, thread in calls if thread == threading.get_ident()]


def _isolated_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """A build that reads its test directory alone; its fence finds a live account and job."""
    for setting, directory in (
        ("exports_storage_path", "exports"),
        ("attachments_storage_path", "attachments"),
        ("rag_spaces_storage_path", "spaces"),
    ):
        monkeypatch.setattr(settings, setting, str(tmp_path / directory))
    profile = {"language": "en", "extraction_revision": 0}
    monkeypatch.setattr(builder, "_fetch_user_profile", AsyncMock(return_value=profile))
    monkeypatch.setattr(builder, "exportable_tables", lambda: [])
    db = AsyncMock()
    db.scalar.side_effect = [
        SimpleNamespace(is_active=True, is_deleted=False, extraction_revision=0),
        SimpleNamespace(status="running", file_path=None),
    ]
    return db


async def test_building_an_archive_makes_no_disk_call_on_the_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disk_calls: list[tuple[str, int]]
) -> None:
    db = _isolated_build(tmp_path, monkeypatch)
    monkeypatch.setattr(builder, "get_db_context", _session(db))

    archive, size = await builder.build_export_archive(uuid4(), uuid4())

    seen = list(disk_calls)
    assert {"is_symlink", "mkdir", "stat", "replace"} <= {name for name, _ in seen}
    assert _on_the_loop(seen) == []
    assert archive.stat().st_size == size > 0


async def test_a_cancellation_during_the_cleanup_still_takes_the_published_archive_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _isolated_build(tmp_path, monkeypatch)

    @asynccontextmanager
    async def refused_commit() -> AsyncIterator[AsyncMock]:
        yield db
        raise RuntimeError("the commit was refused")

    monkeypatch.setattr(builder, "get_db_context", refused_commit)
    cleaning, release = threading.Event(), threading.Event()
    real_unlink = Path.unlink

    def held_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name.endswith(".building.zip"):
            cleaning.set()
            assert release.wait(5), "the test never released the cleanup"
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", held_unlink)
    owner = uuid4()
    build = asyncio.create_task(builder.build_export_archive(owner, uuid4()))
    try:
        assert await asyncio.to_thread(cleaning.wait, 5), "the cleanup never started"
        build.cancel()
        await asyncio.sleep(0.05)
    finally:
        release.set()
        (outcome,) = await asyncio.gather(build, return_exceptions=True)

    assert isinstance(outcome, asyncio.CancelledError)
    assert (
        list((tmp_path / "exports" / str(owner)).iterdir()) == []
    ), "an archive outlived its build"


async def test_an_archive_its_job_refused_is_removed_off_the_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disk_calls: list[tuple[str, int]]
) -> None:
    archive = tmp_path / "refused.zip"
    archive.write_bytes(b"PK refused")
    claimed = SimpleNamespace(id=uuid4(), user_id=uuid4(), status="pending", started_at=None)
    db = AsyncMock()
    db.execute.return_value = MagicMock(**{"scalar_one_or_none.return_value": claimed})
    monkeypatch.setattr(executor, "get_db_context", _session(db))
    monkeypatch.setattr(executor, "build_export_archive", AsyncMock(return_value=(archive, 10)))
    monkeypatch.setattr(executor, "_finish_job", AsyncMock(return_value=False))

    await executor._build_next_pending()

    seen = list(disk_calls)
    assert [name for name, _ in seen] == ["unlink"] and _on_the_loop(seen) == []
    assert not archive.exists()


async def test_an_expired_archive_is_swept_off_the_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disk_calls: list[tuple[str, int]]
) -> None:
    archive = tmp_path / "expired.zip"
    archive.write_bytes(b"PK expired")
    job = SimpleNamespace(
        id=uuid4(), user_id=uuid4(), status=ExportJobStatus.DONE.value, file_path=str(archive)
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock(**{"scalars.return_value.all.return_value": [job]})
    monkeypatch.setattr(executor, "get_db_context", _session(db))

    await executor._sweep_expired()

    seen = list(disk_calls)
    assert [name for name, _ in seen] == ["unlink"] and _on_the_loop(seen) == []
    assert not archive.exists()
    assert job.status == ExportJobStatus.EXPIRED.value and job.file_path is None
