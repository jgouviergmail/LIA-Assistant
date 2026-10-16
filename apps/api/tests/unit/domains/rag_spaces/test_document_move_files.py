"""Confirmed file staging never overwrites a neighbor and keeps originals until SQL ACK."""

import asyncio
import os
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.rag_spaces import document_move_files
from src.infrastructure.file_transfer import LocalFileRead
from tests.support.file_clock import rewrite_later

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "obstacle",
    [
        "none",
        "missing",
        "changed",
        "missing_appeared",
        "collision",
        "copy_failed",
        "copy_cancelled",
    ],
)
async def test_document_move_staging_keeps_original_and_exact_destination(
    monkeypatch, tmp_path, obstacle
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, source, target = uuid4(), uuid4(), uuid4()
    original = tmp_path / str(owner) / str(source) / "original.txt"
    destination = tmp_path / str(owner) / str(target) / "original.txt"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    reader = LocalFileRead.open(original)
    digest = reader.identity_digest
    await reader.close()
    if obstacle in {"missing", "missing_appeared"}:
        original.unlink()
        digest = None
    if obstacle == "missing_appeared":
        original.write_bytes(b"more")
    if obstacle == "changed":
        rewrite_later(original, b"more")
    if obstacle == "collision":
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"kept")
    if obstacle in {"copy_failed", "copy_cancelled"}:

        async def interrupted(self, output):
            output.write(b"partial")
            raise (
                asyncio.CancelledError()
                if obstacle == "copy_cancelled"
                else OSError("Controlled partial copy")
            )

        monkeypatch.setattr(LocalFileRead, "copy_to", interrupted)
    if obstacle in {"none", "missing"}:
        staged = await document_move_files.stage_document_file(
            owner, source, target, "original.txt", digest, 4
        )
        if obstacle == "missing":
            assert staged is None and not original.exists() and not destination.exists()
        else:
            assert original.read_bytes() == b"data" and destination.read_bytes() == b"data"
            assert await document_move_files.rollback_staged_file(staged)
            assert original.read_bytes() == b"data" and not destination.exists()
    else:
        with pytest.raises((ValueError, OSError, asyncio.CancelledError)):
            await document_move_files.stage_document_file(
                owner, source, target, "original.txt", digest, 4
            )
        assert original.exists()
        if obstacle == "collision":
            assert destination.read_bytes() == b"kept"
        else:
            assert not destination.exists()


async def test_cancelled_staging_waits_for_the_real_copy_worker_before_closing_or_removing(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, source, target = uuid4(), uuid4(), uuid4()
    original = tmp_path / str(owner) / str(source) / "controlled.txt"
    destination = tmp_path / str(owner) / str(target) / "controlled.txt"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    reader = LocalFileRead.open(original)
    digest = reader.identity_digest
    await reader.close()
    started, release = Event(), Event()
    outputs = []

    async def delayed(self, output):
        outputs.append(output)

        def worker():
            output.write(b"partial")
            started.set()
            assert release.wait(5)
            assert not output.closed
            output.write(b"completed")

        await self._io(worker)

    monkeypatch.setattr(LocalFileRead, "copy_to", delayed)
    operation = asyncio.create_task(
        document_move_files.stage_document_file(owner, source, target, "controlled.txt", digest, 4)
    )
    try:
        assert await asyncio.to_thread(started.wait, 5)
        operation.cancel()
        await asyncio.sleep(0)
        assert not outputs[0].closed and not operation.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
    finally:
        release.set()
        if not operation.done():
            await asyncio.gather(operation, return_exceptions=True)
    assert outputs[0].closed and original.read_bytes() == b"data" and not destination.exists()


async def test_failed_destination_flush_does_not_leave_a_new_unapproved_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, source, target = uuid4(), uuid4(), uuid4()
    original = tmp_path / str(owner) / str(source) / "flush.txt"
    destination = tmp_path / str(owner) / str(target) / "flush.txt"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    reader = LocalFileRead.open(original)
    digest = reader.identity_digest
    await reader.close()
    actual_open = Path.open

    class FailFlush:
        def __init__(self, file):
            self.file = file

        def __getattr__(self, name):
            return getattr(self.file, name)

        def flush(self):
            raise OSError("Controlled failed flush")

    def open_file(path, *args, **kwargs):
        opened = actual_open(path, *args, **kwargs)
        return FailFlush(opened) if path == destination and args[0] == "xb" else opened

    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(OSError):
        await document_move_files.stage_document_file(owner, source, target, "flush.txt", digest, 4)
    assert original.read_bytes() == b"data" and not destination.exists()


async def test_rollback_refuses_an_unrelated_replacement_of_the_staged_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, source, target = uuid4(), uuid4(), uuid4()
    original = tmp_path / str(owner) / str(source) / "kept.txt"
    destination = tmp_path / str(owner) / str(target) / "kept.txt"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    reader = LocalFileRead.open(original)
    digest = reader.identity_digest
    await reader.close()
    staged = await document_move_files.stage_document_file(
        owner, source, target, "kept.txt", digest, 4
    )
    replacement = destination.with_name("replacement.txt")
    replacement.write_bytes(b"keep")
    os.replace(replacement, destination)
    assert not await document_move_files.rollback_staged_file(staged)
    assert destination.read_bytes() == b"keep" and original.read_bytes() == b"data"


@pytest.mark.parametrize(
    "filename",
    ["../outside.txt", "nested/file.txt", "", "/absolute.txt", "file.txt:stream", "file\x00.txt"],
)
async def test_staging_refuses_nonliteral_stored_names_without_writing(
    monkeypatch, tmp_path, filename
):
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    with pytest.raises(ValueError):
        await document_move_files.stage_document_file(uuid4(), uuid4(), uuid4(), filename, None, 4)
    assert list(tmp_path.iterdir()) == []
