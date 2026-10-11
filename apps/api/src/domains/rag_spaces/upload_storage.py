"""Finish the one local writer before cleaning a failed, newly minted upload file."""

import asyncio
from contextlib import suppress
from pathlib import Path

from src.infrastructure.async_utils import write_through_cancellation


async def write_uploaded_file(path: Path, content: bytes) -> None:
    worker = asyncio.create_task(asyncio.to_thread(path.write_bytes, content))
    try:
        written = await asyncio.shield(worker)
        if written != len(content):
            raise OSError("Incomplete local upload write")
    except BaseException:

        async def cleanup() -> None:
            # Cancelling a coroutine cannot stop its already-running thread.
            # Joining this SAME worker prevents a late write recreating the orphan.
            with suppress(Exception):
                await worker
            await asyncio.to_thread(path.unlink, missing_ok=True)

        await write_through_cancellation(
            cleanup, attempts=3, label="rag_upload_failed_file_cleanup"
        )
        raise
