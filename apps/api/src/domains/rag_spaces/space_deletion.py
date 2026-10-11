"""Source post-commit file cleanup and deletion telemetry, shared by GUI and native tools."""

import asyncio
import shutil
from pathlib import Path
from uuid import UUID

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_documents_total_count,
    rag_spaces_active_count,
    rag_spaces_total_count,
)

logger = get_logger(__name__)


def _cleanup_space_files(user_id: UUID, space_id: UUID) -> bool:
    root = Path(settings.rag_spaces_storage_path).resolve()
    account = root / str(user_id)
    directory = account / str(space_id)
    # Links/junctions to another account/space are not the selected directory.
    if account.is_symlink() or directory.is_symlink():
        return False
    target = directory.resolve()
    if target != directory or not target.is_relative_to(root) or target == root:
        return False
    try:
        if target.exists():
            shutil.rmtree(target)
        return not target.exists()
    except OSError:
        return False


async def cleanup_space_files(user_id: UUID, space_id: UUID) -> bool:
    """Best-effort source cleanup after an acknowledged database deletion only."""
    return await asyncio.to_thread(_cleanup_space_files, user_id, space_id)


def publish_space_deletion(active: bool, document_statuses: tuple[str, ...]) -> None:
    rag_spaces_total_count.dec()
    if active:
        rag_spaces_active_count.dec()
    for status in document_statuses:
        rag_documents_total_count.labels(status=status).dec()
