"""Where a knowledge space's files live on disk, and the one way to name one.

A stored file is ``{root}/{user_id}/{space_id}/{stored_filename}``; the two
identifiers are UUIDs and the file name is minted by the server, so no segment
can carry a traversal. The containment check stays, as defence in depth,
BECAUSE it is cheap and because a future caller may hand in a segment nobody
typed as a UUID — and it lives in exactly one place: ``processing.py`` used to
build the same path by hand, without it, while ``drive_ingest.py`` could not
lend its helper without an import cycle (``drive_ingest`` reads
``processing``). Extracted by ADR-326.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import status

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def safe_storage_path(base_dir: Path, *segments: str) -> Path:
    """Build a storage path and verify it stays within the base directory.

    Prevents path-traversal attacks when segments originate from the database.

    Args:
        base_dir: Trusted root directory (e.g. ``/app/data/rag_uploads``).
        *segments: Untrusted path components (user_id, space_id, filename).

    Returns:
        Resolved absolute path guaranteed to be under *base_dir*.

    Raises:
        BaseAPIException: If the resolved path escapes *base_dir*.
    """
    target = (base_dir / Path(*segments)).resolve()
    if not target.is_relative_to(base_dir.resolve()):
        logger.error(
            "rag_path_traversal_blocked",
            base_dir=str(base_dir),
            segments=segments,
        )
        raise BaseAPIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path",
            log_event="rag_path_traversal_blocked",
        )
    return target


def stored_file_path(user_id: UUID, space_id: UUID, stored_filename: str) -> Path:
    """The absolute path of one stored file of a space, under the configured root.

    Args:
        user_id: The owner.
        space_id: The space.
        stored_filename: The server-minted file name (a UUID plus its suffix).

    Returns:
        The resolved path, guaranteed under ``rag_spaces_storage_path``.

    Raises:
        BaseAPIException: If the resolved path escapes the root.
    """
    return safe_storage_path(
        Path(settings.rag_spaces_storage_path), str(user_id), str(space_id), stored_filename
    )


__all__ = ["safe_storage_path", "stored_file_path"]
