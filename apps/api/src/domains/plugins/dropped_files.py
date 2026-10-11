"""A dropped component's files follow the package's known row commit."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.plugins.removal_disk import (
    RemovalMove,
    cleanup_quarantine,
    prepare_path_moves,
    restore_moves,
    stage_moves,
)
from src.domains.plugins.root_commit import (
    PluginImportCompletionUnknown,
    PluginImportPostCommitFailure,
)
from src.domains.skills.import_disk import finish_disk_step, run_disk_step
from src.domains.skills.import_service import validate_skill_name
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DroppedFileState:
    cleanup_pending: bool = False


@asynccontextmanager
async def retain_dropped_files(
    db: AsyncSession,
    owner_id: UUID,
    base: Path,
    names: set[str],
    *,
    after_stage: Callable[[tuple[RemovalMove, ...]], Awaitable[None]] | None = None,
) -> AsyncIterator[DroppedFileState]:
    for name in names:
        validate_skill_name(name)
    paths = tuple(base / str(owner_id) / name for name in sorted(names))
    moves = await asyncio.to_thread(prepare_path_moves, paths)
    state = DroppedFileState()
    try:
        await run_disk_step(partial(stage_moves, moves))
        if after_stage is not None:
            await after_stage(moves)
        yield state
    except PluginImportCompletionUnknown, PluginImportPostCommitFailure:
        # The row deletion may be durable. Keep bytes outside the skill scanner.
        raise
    except Exception, asyncio.CancelledError:
        try:
            await db.rollback()
        finally:
            await finish_disk_step(partial(restore_moves, moves))
        raise
    try:
        await run_disk_step(partial(cleanup_quarantine, moves))
    except (Exception, asyncio.CancelledError) as error:
        state.cleanup_pending = True
        logger.warning("plugin_update_file_cleanup_pending", error_type=type(error).__name__)
