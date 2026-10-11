"""One group row commit, recoverable files and explicit known/unknown completion."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError
from src.domains.plugins.group_scope import PluginGroup, load_plugin_group
from src.domains.plugins.removal_disk import (
    RemovalMove,
    cleanup_quarantine,
    prepare_moves,
    restore_moves,
    stage_moves,
)
from src.domains.skills.cache import SkillsCache
from src.domains.skills.import_disk import finish_disk_step, run_disk_step
from src.domains.user_mcp.service import UserMCPServerService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
BeforeRemovalCommit = Callable[[], Awaitable[None]]
BeforeRemovalStage = Callable[[PluginGroup], Awaitable[None]]
AfterRemovalStage = Callable[[tuple[RemovalMove, ...]], Awaitable[None]]


class PluginRemovalCompletionUnknown(RuntimeError):
    """Retain quarantined bytes; an unacknowledged removal cannot automatically replay."""


@dataclass
class PluginRemovalResult:
    committed: bool = False
    file_cleanup_pending: bool = True
    pool_cleanup_pending: bool = True
    cache_refresh_pending: bool = True


async def remove_plugin(
    db: AsyncSession,
    owner_id: UUID,
    plugin_id: UUID,
    *,
    before_stage: BeforeRemovalStage | None = None,
    after_stage: AfterRemovalStage | None = None,
    before_commit: BeforeRemovalCommit | None = None,
    after_commit: Callable[[], None] | None = None,
) -> PluginRemovalResult:
    try:
        group = await load_plugin_group(db, owner_id, plugin_id, lock=True)
    except ValueError as error:
        raise ValidationError("Plugin component ownership is inconsistent") from error
    if before_stage is not None:
        await before_stage(group)
    moves = await asyncio.to_thread(prepare_moves, group, owner_id)
    try:
        await run_disk_step(partial(stage_moves, moves))
        if after_stage is not None:
            await after_stage(moves)
        for row in (*group.skills, *group.servers, group.plugin):
            await db.delete(row)
        await db.flush()
        if before_commit is not None:
            await before_commit()
    except Exception, asyncio.CancelledError:
        await _restore(db, moves)
        raise
    try:
        await db.commit()
    except IntegrityError:
        await _restore(db, moves)
        raise
    except (Exception, asyncio.CancelledError) as error:
        raise PluginRemovalCompletionUnknown("Plugin removal acknowledgement unknown") from error
    result = PluginRemovalResult(committed=True)
    if after_commit is not None:
        after_commit()
    try:
        await run_disk_step(partial(cleanup_quarantine, moves))
        result.file_cleanup_pending = False
    except (Exception, asyncio.CancelledError) as error:
        logger.warning("plugin_removal_file_cleanup_pending", error_type=type(error).__name__)
    try:
        for server in group.servers:
            await UserMCPServerService._disconnect_from_pool(owner_id, server.id, strict=True)
        result.pool_cleanup_pending = False
    except (Exception, asyncio.CancelledError) as error:
        logger.warning("plugin_removal_pool_cleanup_pending", error_type=type(error).__name__)
    try:
        await SkillsCache.invalidate_and_reload()
        result.cache_refresh_pending = False
    except (Exception, asyncio.CancelledError) as error:
        logger.warning("plugin_removal_cache_refresh_pending", error_type=type(error).__name__)
    return result


async def _restore(db: AsyncSession, moves: tuple[RemovalMove, ...]) -> None:
    try:
        await db.rollback()
    finally:
        await finish_disk_step(partial(restore_moves, moves))
