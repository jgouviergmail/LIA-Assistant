"""Prepared exports bound memory, preserve CSV/JSON semantics and close on failure."""

import asyncio
import csv
import io
import json
import threading
from collections.abc import AsyncGenerator

import pytest

from src.core.management_export_file import ManagementExportFile, prepare_management_export_file

pytestmark = pytest.mark.unit


async def rows() -> AsyncGenerator[dict[str, object]]:
    yield {"topic": "=1+1", "number": -3}
    yield {"topic": "é,你好", "number": 4}


async def content(reader: ManagementExportFile) -> bytes:
    chunks: list[bytes] = []
    while chunk := await reader.read_chunk():
        chunks.append(chunk)
    return b"".join(chunks)


@pytest.mark.parametrize("format", ["json", "csv"])
async def test_export_file_is_exact_spooled_and_closed(format: str) -> None:
    reader = await prepare_management_export_file(
        rows(),
        format=format,
        fieldnames=("topic", "number"),
        metadata={"user_id": "owner", "total_interests": 2},
        collection="interests",
        max_bytes=4096,
        spool_bytes=1,
    )
    try:
        data = await content(reader)
        assert len(data) == reader.file_size_bytes
        assert reader.spooled_to_disk
        if format == "json":
            document = json.loads(data)
            assert document["total_interests"] == 2
            assert document["interests"][0]["topic"] == "=1+1"
        else:
            records = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
            assert records == [
                {"topic": "'=1+1", "number": "-3"},
                {"topic": "é,你好", "number": "4"},
            ]
    finally:
        await reader.close()
    assert reader.closed


async def test_preparation_refuses_oversize_without_returning_a_partial_download() -> None:
    with pytest.raises(ValueError, match="size"):
        await prepare_management_export_file(
            rows(),
            format="json",
            fieldnames=("topic", "number"),
            metadata={},
            collection="interests",
            max_bytes=5,
        )


async def test_empty_csv_retains_headers_and_json_retains_its_empty_collection() -> None:
    async def empty() -> AsyncGenerator[dict[str, object]]:
        if False:
            yield {}

    for format in ["csv", "json"]:
        reader = await prepare_management_export_file(
            empty(),
            format=format,
            fieldnames=("topic", "number"),
            metadata={},
            collection="interests",
            max_bytes=4096,
        )
        try:
            data = await content(reader)
            assert (
                (data.decode("utf-8-sig") == "topic,number\r\n")
                if format == "csv"
                else (json.loads(data) == {"interests": []})
            )
        finally:
            await reader.close()


async def test_cancelled_disk_write_finishes_before_the_owned_file_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = ManagementExportFile(4096, spool_bytes=1)
    started, release, closed = threading.Event(), threading.Event(), threading.Event()
    original_write, original_close = reader._file.write, reader._file.close

    def gated_write(data: bytes) -> int:
        started.set()
        assert release.wait(2)
        return original_write(data)

    def observed_close() -> None:
        closed.set()
        original_close()

    monkeypatch.setattr(reader._file, "write", gated_write)
    monkeypatch.setattr(reader._file, "close", observed_close)
    writing = asyncio.create_task(reader.write("cancelled write"))
    closing: asyncio.Task[None] | None = None
    try:
        assert await asyncio.to_thread(started.wait, 2)
        writing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writing
        closing = asyncio.create_task(reader.close())
        assert not await asyncio.to_thread(closed.wait, 0.05)
    finally:
        release.set()
        if closing is not None:
            await closing
        else:
            await reader.close()
    assert reader.closed


async def test_size_failure_closes_the_active_source_iterator_immediately() -> None:
    released = False

    async def source() -> AsyncGenerator[dict[str, object]]:
        nonlocal released
        try:
            yield {"topic": "x" * 1000}
        finally:
            released = True

    selected = source()
    try:
        with pytest.raises(ValueError, match="size"):
            await prepare_management_export_file(
                selected,
                format="csv",
                fieldnames=("topic",),
                metadata={},
                collection="interests",
                max_bytes=100,
            )
        assert released
    finally:
        await selected.aclose()


async def test_source_json_counts_actual_rows_without_collecting_a_second_list() -> None:
    reader = await prepare_management_export_file(
        rows(),
        format="json",
        fieldnames=("topic", "number"),
        metadata={"user_id": "owner"},
        collection="interests",
        count_key="total_interests",
        max_bytes=4096,
    )
    try:
        assert json.loads(await content(reader))["total_interests"] == 2
    finally:
        await reader.close()
