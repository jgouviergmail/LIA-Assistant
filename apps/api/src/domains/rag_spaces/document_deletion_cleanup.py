"""Post-ACK cleanup of the exact old file only; missing/changed files are never invented."""

import asyncio
from pathlib import Path
from uuid import UUID

from src.core.config import settings
from src.infrastructure.file_transfer import LocalFileRead


async def cleanup_deleted_document_file(
    actor_id: UUID, space_id: UUID, filename: str, expected_digest: str | None
) -> bool:
    root = Path(settings.rag_spaces_storage_path).resolve()
    account = root / str(actor_id)
    scope = account / str(space_id)
    path = scope / filename
    if account.is_symlink() or scope.is_symlink() or path.is_symlink():
        return False
    if scope.resolve() != scope or path.resolve().parent != scope or path.name != filename:
        return False
    try:
        reader = LocalFileRead.open(path)
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
