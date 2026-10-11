"""Bounded local byte transfer from an opened regular-file descriptor, without publishing paths."""

import asyncio
import hashlib
import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import IO, BinaryIO

import anyio

from src.infrastructure.async_utils import write_through_cancellation


def _identity(file: BinaryIO | SpooledTemporaryFile[bytes], path: Path) -> tuple[int, str]:
    metadata = os.fstat(file.fileno())
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Only regular stored files can be transferred")
    identity = (
        str(path),
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )
    return metadata.st_size, hashlib.sha256(repr(identity).encode("utf-8")).hexdigest()


class LocalFileRead:
    def __init__(self, file: BinaryIO | SpooledTemporaryFile[bytes], path: Path) -> None:
        self._file: BinaryIO | SpooledTemporaryFile[bytes] = file
        self._path = path
        self.file_size_bytes, self.identity_digest = _identity(file, path)
        metadata = os.fstat(file.fileno())
        self.creation_identity = (metadata.st_dev, metadata.st_ino)
        self._frozen = False
        self._pending: set[asyncio.Task[bytes | None]] = set()

    @property
    def closed(self) -> bool:
        return self._file.closed

    @classmethod
    def open(cls, path: Path) -> LocalFileRead:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(path, flags)
        try:
            file = os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
        try:
            return cls(file, path)
        except BaseException:
            file.close()
            raise

    @classmethod
    def from_bytes(cls, data: bytes) -> LocalFileRead:
        """An already frozen export uses the same bounded transfer/cleanup owner."""
        file = SpooledTemporaryFile[bytes](max_size=512 * 1024, mode="w+b")
        try:
            file.write(data)
            file.seek(0)
            reader = cls(file, Path("lia-export"))
            reader._frozen = True
            return reader
        except BaseException:
            file.close()
            raise

    @classmethod
    async def async_open(cls, path: Path) -> LocalFileRead:
        """An interrupted thread opening still owns and closes its eventual descriptor."""
        return await cls._async_create(lambda: cls.open(path))

    @classmethod
    async def async_from_bytes(cls, data: bytes) -> LocalFileRead:
        return await cls._async_create(lambda: cls.from_bytes(data))

    @classmethod
    async def _async_create(cls, factory: Callable[[], LocalFileRead]) -> LocalFileRead:
        task = asyncio.create_task(asyncio.to_thread(factory))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:

            async def close_opened() -> None:
                reader = await task
                await reader.close()

            await write_through_cancellation(
                close_opened, attempts=3, label="local_file_open_cancel_cleanup"
            )
            raise

    async def _io(self, operation: Callable[[], bytes | None]) -> bytes | None:
        task = asyncio.create_task(anyio.to_thread.run_sync(operation))
        self._pending.add(task)
        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                self._pending.discard(task)

    def _freeze(self, max_bytes: int) -> None:
        if self.file_size_bytes > max_bytes:
            raise ValueError("Stored file exceeds the approved size")
        if self._frozen:
            return
        frozen = SpooledTemporaryFile[bytes](max_size=512 * 1024, mode="w+b")
        try:
            self._file.seek(0)
            total = 0
            while chunk := self._file.read(64 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Stored file grew beyond the approved size")
                frozen.write(chunk)
            if (
                total != self.file_size_bytes
                or _identity(self._file, self._path)[1] != self.identity_digest
            ):
                raise ValueError("Stored file changed during confirmed transfer preparation")
            frozen.seek(0)
        except BaseException:
            frozen.close()
            raise
        self._file.close()
        self._file = frozen
        self._frozen = True

    async def freeze(self, *, max_bytes: int) -> None:
        await self._io(lambda: self._freeze(max_bytes))

    async def read_chunk(self) -> bytes:
        chunk = await self._io(lambda: self._file.read(64 * 1024))
        assert isinstance(chunk, bytes)
        return chunk

    async def copy_to(self, target: IO[bytes]) -> None:
        """Copy approved frozen bytes into a local container such as a ZIP entry."""
        if not self._frozen:
            raise ValueError("Only frozen approved files may be copied")

        def copy() -> None:
            self._file.seek(0)
            shutil.copyfileobj(self._file, target, length=64 * 1024)

        await self._io(copy)

    async def close(self) -> None:
        cancelled = await write_through_cancellation(
            self._close_after_io, attempts=3, label="local_file_transfer_close"
        )
        if cancelled:
            raise asyncio.CancelledError()

    async def _close_after_io(self) -> None:
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
            self._pending.clear()
        await anyio.to_thread.run_sync(self._file.close)
