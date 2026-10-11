"""Bounded, transient exports; the response owns the file after successful preparation."""

import asyncio
import csv
import io
import json
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from contextlib import aclosing
from tempfile import SpooledTemporaryFile

import anyio

from src.core.export_utils import spreadsheet_safe_cell
from src.infrastructure.async_utils import write_through_cancellation

_TRANSFER_CHUNK = 64 * 1024
_SPOOL_MEMORY = 512 * 1024


class ManagementExportFile:
    def __init__(self, max_bytes: int, spool_bytes: int = _SPOOL_MEMORY) -> None:
        self._file = SpooledTemporaryFile[bytes](max_size=spool_bytes, mode="w+b")
        self._max_bytes = max_bytes
        self._spool_bytes = spool_bytes
        self.file_size_bytes = 0
        self._pending: set[asyncio.Task[bytes | int | None]] = set()

    async def _io(self, operation: Callable[[], bytes | int | None]) -> bytes | int | None:
        task = asyncio.create_task(anyio.to_thread.run_sync(operation))
        self._pending.add(task)
        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                self._pending.discard(task)

    @property
    def closed(self) -> bool:
        return self._file.closed

    @property
    def spooled_to_disk(self) -> bool:
        return self.file_size_bytes > self._spool_bytes

    async def write(self, content: str) -> None:
        encoded = content.encode("utf-8")
        if self.file_size_bytes + len(encoded) > self._max_bytes:
            raise ValueError("Export exceeds the configured maximum size")
        await self._io(lambda: self._file.write(encoded))
        self.file_size_bytes += len(encoded)

    async def rewind(self) -> None:
        await self._io(lambda: self._file.seek(0))

    async def read_chunk(self) -> bytes:
        chunk = await self._io(lambda: self._file.read(_TRANSFER_CHUNK))
        assert isinstance(chunk, bytes)
        return chunk

    async def close(self) -> None:
        cancelled = await write_through_cancellation(
            self._close_after_io, attempts=3, label="management_export_close"
        )
        if cancelled:
            raise asyncio.CancelledError()

    async def _close_after_io(self) -> None:
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
            self._pending.clear()
        await anyio.to_thread.run_sync(self._file.close)


def _csv_line(values: Mapping[str, object], fields: Sequence[str], *, header: bool) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields)
    if header:
        writer.writeheader()
    else:
        writer.writerow({key: spreadsheet_safe_cell(value) for key, value in values.items()})
    return buffer.getvalue()


async def prepare_management_export_file(
    rows: AsyncGenerator[Mapping[str, object]],
    *,
    format: str,
    fieldnames: Sequence[str],
    metadata: Mapping[str, object],
    collection: str,
    max_bytes: int,
    spool_bytes: int = _SPOOL_MEMORY,
    count_key: str | None = None,
) -> ManagementExportFile:
    if format not in {"csv", "json"} or collection in metadata:
        raise ValueError("Invalid export format or collection")
    reader = ManagementExportFile(max_bytes, spool_bytes)
    try:
        if format == "csv":
            await reader.write("\ufeff" + _csv_line({}, fieldnames, header=True))
        else:
            prefix = json.dumps(dict(metadata), ensure_ascii=False)[:-1]
            separator = "," if metadata else ""
            await reader.write(prefix + separator + json.dumps(collection) + ":[")
        async with aclosing(rows):
            count = 0
            async for row in rows:
                if format == "csv":
                    await reader.write(_csv_line(row, fieldnames, header=False))
                else:
                    await reader.write(
                        ("" if count == 0 else ",") + json.dumps(dict(row), ensure_ascii=False)
                    )
                count += 1
        if format == "json":
            suffix = "," + json.dumps(count_key) + ":" + str(count) if count_key else ""
            await reader.write("]" + suffix + "}")
        await reader.rewind()
        return reader
    except BaseException:
        await reader.close()
        await rows.aclose()
        raise
