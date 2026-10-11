"""Confirmed local transfers preserve bytes after their source changes and close every descriptor."""

import asyncio
import os
from threading import Event

import pytest

from src.infrastructure.file_transfer import LocalFileRead

pytestmark = pytest.mark.unit


async def test_cancellation_during_threaded_open_closes_the_late_descriptor(tmp_path, monkeypatch):
    path = tmp_path / "cancelled.bin"
    path.write_bytes(b"owned bytes")
    started, release = Event(), Event()
    original = LocalFileRead.open
    readers = []

    def delayed_open(file):
        started.set()
        assert release.wait(5)
        reader = original(file)
        readers.append(reader)
        return reader

    monkeypatch.setattr(LocalFileRead, "open", delayed_open)
    transfer = asyncio.create_task(LocalFileRead.async_open(path))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        transfer.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await transfer
        assert len(readers) == 1 and readers[0].closed
    finally:
        release.set()


async def test_freezing_retains_approved_bytes_after_source_file_is_overwritten(tmp_path):
    path = tmp_path / "source.bin"
    path.write_bytes(b"approved source bytes")
    reader = LocalFileRead.open(path)
    try:
        await reader.freeze(max_bytes=21)
        path.write_bytes(b"different later bytes")
        assert await reader.read_chunk() == b"approved source bytes"
        assert await reader.read_chunk() == b""
    finally:
        await reader.close()


async def test_cancellation_during_export_creation_closes_the_late_temporary_descriptor(
    monkeypatch,
):
    started, release = Event(), Event()
    original = LocalFileRead.from_bytes
    readers = []

    def delayed_export(data):
        started.set()
        assert release.wait(5)
        reader = original(data)
        readers.append(reader)
        return reader

    monkeypatch.setattr(LocalFileRead, "from_bytes", delayed_export)
    transfer = asyncio.create_task(LocalFileRead.async_from_bytes(b"full export"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        transfer.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await transfer
        assert len(readers) == 1 and readers[0].closed
    finally:
        release.set()


async def test_freezing_refuses_a_source_larger_than_the_approved_bound(tmp_path):
    path = tmp_path / "source.bin"
    path.write_bytes(b"data")
    reader = LocalFileRead.open(path)
    try:
        with pytest.raises(ValueError):
            await reader.freeze(max_bytes=3)
    finally:
        await reader.close()


def test_opening_failure_closes_the_original_os_descriptor(tmp_path, monkeypatch):
    path = tmp_path / "source.bin"
    path.write_bytes(b"data")
    opened = []
    original = os.open

    def record_open(*args):
        descriptor = original(*args)
        opened.append(descriptor)
        return descriptor

    def failed_wrapper(*args):
        raise OSError("Controlled wrapper failure")

    monkeypatch.setattr(os, "open", record_open)
    monkeypatch.setattr(os, "fdopen", failed_wrapper)
    with pytest.raises(OSError):
        LocalFileRead.open(path)
    with pytest.raises(OSError):
        os.fstat(opened[0])
