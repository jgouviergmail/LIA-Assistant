"""Where an upload lands and the one local writer that puts it there, both off the event loop.

The writer finishes before cleaning a failed, newly minted upload file.
"""

import asyncio
import uuid
from contextlib import suppress
from pathlib import Path

from src.infrastructure.async_utils import write_through_cancellation


async def prepare_space_directory(root: str, user_id: uuid.UUID, space_id: uuid.UUID) -> Path:
    """The space's storage directory under ``root``, resolved inside it and created (AC-035).

    ``user_id`` and ``space_id`` are typed UUIDs upstream, so the segments cannot
    carry traversal sequences; the resolve + containment check is defense in
    depth that survives a future signature change. Resolving and creating are
    disk calls: they run in a worker thread.

    Raises:
        RuntimeError: The resolved directory escapes the storage root.
    """
    return await asyncio.to_thread(_space_directory, root, user_id, space_id)


def _space_directory(root: str, user_id: uuid.UUID, space_id: uuid.UUID) -> Path:
    storage_root = Path(root).resolve()
    storage_dir = (storage_root / str(user_id) / str(space_id)).resolve()
    if not storage_dir.is_relative_to(storage_root):
        raise RuntimeError(
            "RAG storage path integrity violation: resolved directory escapes the storage root"
        )
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


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
