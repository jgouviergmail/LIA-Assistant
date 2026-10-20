"""Bounded ZIP writer: one partition and one row's readable rendering in RAM."""

import asyncio
import json
import os
import tempfile
import zipfile
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import ExitStack, aclosing, asynccontextmanager
from pathlib import Path
from typing import IO, ParamSpec, TypeVar
from uuid import UUID

from src.core.config import settings
from src.core.i18n_treatments import render_chain_attestation

Row = dict[str, object]
RowStream = Callable[[str, UUID], AsyncGenerator[Row]]
Markdown = Callable[[str, list[Row], str | None], str | None]


class ExportTooLargeError(Exception):
    """The complete compressed archive cannot fit the existing export cap."""


class StreamingArchive:
    def __init__(self, path: Path, render: Markdown, language: str) -> None:
        self.path = path
        self.render = render
        self.language = language
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        self.raw = os.fdopen(descriptor, "w+b")
        try:
            self.archive = zipfile.ZipFile(self.raw, "w", compression=zipfile.ZIP_DEFLATED)
        except BaseException:
            self.raw.close()
            raise
        self._entry: IO[bytes] | None = None
        self._readable: IO[bytes] | None = None
        self._first = True
        self._table = ""
        self._count = 0
        self._last: Row | None = None

    def check_size(self) -> None:
        if self.raw.tell() > settings.account_export_max_bytes:
            raise ExportTooLargeError("export_too_large")

    def profile(self, profile: Row) -> None:
        self.archive.writestr(
            "profile.json", json.dumps(profile, ensure_ascii=False, default=_scalar)
        )
        self.check_size()

    def begin_table(self, table: str) -> None:
        self._table, self._first, self._count, self._last = table, True, 0, None
        entry = self.archive.open(f"data/{table}.json", "w")
        self._entry = entry
        entry.write(b"[\n")
        self._readable = tempfile.TemporaryFile(mode="w+b")

    def rows(self, rows: list[Row]) -> None:
        if self._entry is None or self._readable is None:
            raise RuntimeError("export_table_not_open")
        for row in rows:
            data = json.dumps(row, ensure_ascii=False, default=_scalar).encode("utf-8")
            self._entry.write((b"" if self._first else b",\n") + data)
            if self._table != "ledger_chain":
                markdown = self.render(self._table, [row], self.language)
                if markdown is not None:
                    text = markdown if self._first else markdown.partition("\n")[2]
                    self._readable.write(text.encode("utf-8"))
            self._first = False
            self._count += 1
            self._last = row
            self.check_size()

    def end_table(self) -> None:
        if self._entry is None or self._readable is None:
            raise RuntimeError("export_table_not_open")
        self._entry.write(b"\n]\n")
        self._entry.close()
        self._entry = None
        self.check_size()
        if self._table == "ledger_chain":
            self._readable.write(_chain(self._count, self._last, self.language).encode("utf-8"))
        elif self._first:
            markdown = self.render(self._table, [], self.language)
            if markdown is not None:
                self._readable.write(markdown.encode("utf-8"))
        if self._readable.tell():
            self._readable.seek(0)
            with self.archive.open(f"readable/{self._table}.md", "w") as destination:
                _copy_chunks(self._readable, destination, self.check_size)
        self._readable.close()
        self._readable = None
        self.check_size()

    def files(self, owner: UUID) -> None:
        for label, base in (
            ("files/attachments", settings.attachments_storage_path),
            ("files/rag_documents", settings.rag_spaces_storage_path),
        ):
            directory = Path(base) / str(owner)
            if directory.is_symlink() or not directory.is_dir():
                continue
            for current, dirs, files in os.walk(directory, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not (Path(current) / d).is_symlink())
                for filename in sorted(files):
                    path = Path(current) / filename
                    if path.is_symlink() or not path.is_file():
                        continue
                    info = zipfile.ZipInfo(f"{label}/{path.relative_to(directory).as_posix()}")
                    info.compress_type = zipfile.ZIP_STORED
                    with path.open("rb") as source, self.archive.open(info, "w") as destination:
                        _copy_chunks(source, destination, self.check_size)
                    self.check_size()

    def close(self) -> None:
        with ExitStack() as stack:
            stack.callback(self.raw.close)
            stack.callback(self.archive.close)
            if self._readable is not None:
                stack.callback(self._readable.close)
            if self._entry is not None:
                stack.callback(self._entry.close)


def _scalar(value: object) -> str:
    return value.hex() if isinstance(value, bytes) else str(value)


def _copy_chunks(source: IO[bytes], destination: IO[bytes], check: Callable[[], None]) -> None:
    while chunk := source.read(65536):
        destination.write(chunk)
        check()


def _chain(count: int, last: Row | None, language: str) -> str:
    row = last or {}
    return render_chain_attestation(
        language,
        entries=count,
        sealed_until=str(row.get("occurred_at", "")),
        head_hash=str(row.get("entry_hash", "")),
    )


async def write_streaming_archive(
    path: Path,
    profile: Row,
    owner: UUID,
    tables: list[str],
    rows: RowStream,
    render: Markdown,
    language: str,
) -> None:
    async with _open_sink(path, render, language) as sink:
        await run_disk_io(sink.profile, profile)
        for table in tables:
            await run_disk_io(sink.begin_table, table)
            batch: list[Row] = []
            async with aclosing(rows(table, owner)) as source:
                async for row in source:
                    batch.append(row)
                    if len(batch) == 64:
                        await run_disk_io(sink.rows, batch)
                        batch = []
            if batch:
                await run_disk_io(sink.rows, batch)
            await run_disk_io(sink.end_table)
        await run_disk_io(sink.files, owner)
    if path.stat().st_size > settings.account_export_max_bytes:
        raise ExportTooLargeError("export_too_large")


_P = ParamSpec("_P")
_T = TypeVar("_T")


async def run_disk_io(function: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> _T:
    """Wait out native cancellation before closing or removing a worker's file."""
    worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    cancelled = False
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled = True
    result = worker.result()
    if cancelled:
        raise asyncio.CancelledError()
    return result


@asynccontextmanager
async def _open_sink(
    path: Path, render: Markdown, language: str
) -> AsyncIterator[StreamingArchive]:
    acquired: list[StreamingArchive] = []

    def open_sink() -> None:
        acquired.append(StreamingArchive(path, render, language))

    try:
        await run_disk_io(open_sink)
        yield acquired[0]
    finally:
        # The acquisition thread records ownership before cancellation is raised.
        if acquired:
            await run_disk_io(acquired[0].close)
