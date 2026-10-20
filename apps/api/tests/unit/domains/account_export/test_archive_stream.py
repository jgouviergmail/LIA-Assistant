"""Resource and cancellation contracts of a full personal archive."""

import asyncio
import json
import os
import threading
import tracemalloc
import zipfile
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


async def test_cancel_waits_for_disk_writer_before_cleanup():
    from src.domains.account_export.archive_stream import run_disk_io

    entered, released = threading.Event(), threading.Event()

    def blocking_write():
        entered.set()
        released.wait(timeout=5)
        return 42

    task = asyncio.create_task(run_disk_io(blocking_write))
    while not entered.is_set():
        await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done(), "cancellation cannot close a file another thread is still writing"
    released.set()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_large_generator_remains_complete_under_a_bounded_buffer(tmp_path):
    from src.domains.account_export.archive_stream import write_streaming_archive

    async def rows(table, owner):
        for i in range(10000):
            yield {"id": i, "body": "content" * 100}

    path = tmp_path / "archive.zip"
    tracemalloc.start()
    try:
        await write_streaming_archive(
            path, {"language": "en"}, uuid4(), ["synthetic"], rows, lambda *_: None, "en"
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 5_000_000, "a full archive must not accumulate all source rows"
    with zipfile.ZipFile(path) as archive:
        exported = json.loads(archive.read("data/synthetic.json"))
    assert len(exported) == 10000 and [row["id"] for row in exported] == list(range(10000))


async def test_size_failure_closes_source_cursor_immediately(tmp_path, monkeypatch):
    import hashlib

    from src.core.config import settings
    from src.domains.account_export.archive_stream import (
        ExportTooLargeError,
        write_streaming_archive,
    )

    closed = False

    async def rows(table, owner):
        nonlocal closed
        try:
            for i in range(1000):
                yield {
                    "id": i,
                    "body": "".join(
                        hashlib.sha256(f"{i}:{part}".encode()).hexdigest() for part in range(160)
                    ),
                }
        finally:
            closed = True

    source = rows("synthetic", uuid4())
    monkeypatch.setattr(settings, "account_export_max_bytes", 1024)
    with pytest.raises(ExportTooLargeError):
        await write_streaming_archive(
            tmp_path / "partial.zip",
            {},
            uuid4(),
            ["synthetic"],
            lambda *_: source,
            lambda *_: None,
            "en",
        )
    assert closed, "a failed disk write must not leave the database cursor alive"


async def test_cancel_during_archive_acquisition_closes_its_opened_file(tmp_path, monkeypatch):
    from src.domains.account_export import archive_stream

    entered, released, closed = threading.Event(), threading.Event(), threading.Event()
    constructor = archive_stream.StreamingArchive

    def delayed_open(*args):
        sink = constructor(*args)
        original_close = sink.close

        def close():
            original_close()
            closed.set()

        sink.close = close
        entered.set()
        released.wait(timeout=5)
        return sink

    async def rows(table, owner):
        yield {"id": 1}

    monkeypatch.setattr(archive_stream, "StreamingArchive", delayed_open)
    task = asyncio.create_task(
        archive_stream.write_streaming_archive(
            tmp_path / "partial.zip", {}, uuid4(), ["synthetic"], rows, lambda *_: None, "en"
        )
    )
    while not entered.is_set():
        await asyncio.sleep(0)
    task.cancel()
    released.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (
        closed.is_set()
    ), "an acquired archive must be closed even if delivery of the handle was cancelled"


def test_attachment_owner_root_symlink_cannot_export_a_different_directory(tmp_path, monkeypatch):
    from src.core.config import settings
    from src.domains.account_export.archive_stream import StreamingArchive

    owner = uuid4()
    base = tmp_path / "attachments"
    base.mkdir()
    other = tmp_path / "another-account"
    other.mkdir()
    (other / "private.txt").write_text("OTHER ACCOUNT", encoding="utf-8")
    (base / str(owner)).symlink_to(other, target_is_directory=True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(base))
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path / "unused"))
    path = tmp_path / "archive.zip"
    sink = StreamingArchive(path, lambda *_: None, "en")
    try:
        sink.files(owner)
    finally:
        sink.close()
    with zipfile.ZipFile(path) as archive:
        assert (
            not archive.namelist()
        ), "a user directory that is itself a symlink must not be followed"


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX permissions are verified in the production Linux Docker runtime"
)
def test_plaintext_archive_is_private_to_its_process_owner(tmp_path):
    import stat

    from src.domains.account_export.archive_stream import StreamingArchive

    path = tmp_path / "private.zip"
    sink = StreamingArchive(path, lambda *_: None, "en")
    try:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    finally:
        sink.close()


def test_preexisting_archive_symlink_is_never_followed_or_truncated(tmp_path):
    from src.domains.account_export.archive_stream import StreamingArchive

    target = tmp_path / "another-private-file"
    target.write_text("PRESERVE", encoding="utf-8")
    path = tmp_path / "archive.zip"
    path.symlink_to(target)
    sink = None
    try:
        with pytest.raises(FileExistsError):
            sink = StreamingArchive(path, lambda *_: None, "en")
    finally:
        if sink:
            sink.close()
    assert target.read_text(encoding="utf-8") == "PRESERVE"
