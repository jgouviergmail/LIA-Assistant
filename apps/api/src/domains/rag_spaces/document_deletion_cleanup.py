"""Post-ACK cleanup of the exact old file only; missing/changed files are never invented."""

import asyncio
from uuid import UUID

from src.domains.rag_spaces.document_access import owned_document_path
from src.infrastructure.file_transfer import LocalFileRead


async def cleanup_deleted_document_file(
    actor_id: UUID, space_id: UUID, filename: str, expected_digest: str | None
) -> bool:
    path = await asyncio.to_thread(owned_document_path, actor_id, space_id, filename)
    if path is None:
        return False
    try:
        reader = await LocalFileRead.async_open(path)
    except FileNotFoundError:
        return True
    except OSError, ValueError:
        return False
    try:
        same_file = expected_digest is not None and reader.identity_digest == expected_digest
    finally:
        await reader.close()
    if not same_file:
        return False
    try:
        await asyncio.to_thread(path.unlink)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False
