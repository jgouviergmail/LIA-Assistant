"""A plugin root swap preserves its predecessor until the SQL acknowledgement is known."""

import asyncio
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.plugins.manifest import is_valid_plugin_name
from src.domains.plugins.removal_disk import _checked
from src.domains.skills.import_disk import finish_disk_step, run_disk_step
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.domains.plugins.import_hooks import PluginImportHooks
    from src.domains.plugins.models import UserPlugin


class PluginImportCompletionUnknown(RuntimeError):
    """Retain new and predecessor roots after an unacknowledged import commit."""


class PluginImportPostCommitFailure(RuntimeError):
    """The row commit is known; an observer failure must never trigger restoration."""


@dataclass
class PluginRootSlot:
    live: Path
    incoming: Path
    previous: Path
    original_identity: tuple[int, int] | None
    incoming_identity: tuple[int, int] | None = None


def _identity(path: Path) -> tuple[int, int] | None:
    try:
        item = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return None
    return item.st_dev, item.st_ino


@dataclass(frozen=True)
class PluginRootCommitResult:
    committed: bool
    cleanup_pending: bool


async def publish_plugin_root(
    db: AsyncSession,
    incoming: Path,
    live: Path,
    plugin: UserPlugin,
    hooks: PluginImportHooks,
) -> PluginRootCommitResult:
    if hooks.preserve_root:
        await hooks.check_commit(db)
        await db.commit()
        return PluginRootCommitResult(committed=True, cleanup_pending=False)
    return await commit_plugin_root(
        db,
        incoming,
        live,
        before_commit=partial(hooks.check_commit, db),
        after_stage=hooks.after_root_stage,
        after_commit=partial(hooks.root_committed, plugin),
    )


def _slot(live: Path) -> PluginRootSlot:
    if not is_valid_plugin_name(live.name):
        raise ValueError("Invalid plugin root name")
    live = _checked(live, live.parent)
    token = uuid4().hex
    return PluginRootSlot(
        live,
        _checked(live.parent / ".lia-importing" / token / live.name, live.parent),
        _checked(live.parent / ".lia-removal" / token / live.name, live.parent),
        _identity(live),
    )


def _remove(path: Path, account: Path) -> None:
    _checked(path, account)
    if path.exists():
        shutil.rmtree(path)


def stage_root(staged: Path, slot: PluginRootSlot) -> None:
    account = slot.live.parent
    for path in (slot.live, slot.incoming, slot.previous):
        _checked(path, account)
    slot.incoming.parent.mkdir(parents=True, exist_ok=True)
    _checked(slot.incoming, account)
    slot.incoming.mkdir()
    slot.incoming_identity = _identity(slot.incoming)
    shutil.copytree(staged, slot.incoming, dirs_exist_ok=True)
    if _identity(slot.live) != slot.original_identity:
        raise ValueError("Plugin root changed during preparation")
    if slot.live.exists():
        slot.previous.parent.mkdir(parents=True, exist_ok=True)
        _checked(slot.previous, account)
        os.replace(slot.live, slot.previous)
    os.replace(slot.incoming, slot.live)


def restore_root(slot: PluginRootSlot) -> None:
    account = slot.live.parent
    for path in (slot.live, slot.incoming, slot.previous):
        _checked(path, account)
    if slot.previous.exists():
        if _identity(slot.previous) != slot.original_identity:
            raise ValueError("Plugin predecessor changed before restoration")
        if slot.live.exists():
            if _identity(slot.live) != slot.incoming_identity:
                raise ValueError("Plugin live root changed before restoration")
            _remove(slot.live, account)
        os.replace(slot.previous, slot.live)
    elif slot.original_identity is None and slot.live.exists():
        if _identity(slot.live) != slot.incoming_identity:
            raise ValueError("Plugin live root changed before restoration")
        _remove(slot.live, account)
    _remove(slot.incoming, account)


def cleanup_previous(slot: PluginRootSlot) -> None:
    if slot.previous.exists() and _identity(slot.previous) != slot.original_identity:
        raise ValueError("Plugin predecessor replaced before cleanup")
    if slot.incoming.exists() and _identity(slot.incoming) != slot.incoming_identity:
        raise ValueError("Plugin staging replaced before cleanup")
    _remove(slot.previous, slot.live.parent)
    _remove(slot.incoming, slot.live.parent)


async def commit_plugin_root(
    db: AsyncSession,
    staged: Path,
    live: Path,
    *,
    before_commit: Callable[[], Awaitable[None]] | None = None,
    after_stage: Callable[[PluginRootSlot], Awaitable[None]] | None = None,
    after_commit: Callable[[], None] | None = None,
) -> PluginRootCommitResult:
    slot = _slot(live)
    try:
        await run_disk_step(partial(stage_root, staged, slot))
        if after_stage is not None:
            await after_stage(slot)
        if before_commit is not None:
            await before_commit()
    except Exception, asyncio.CancelledError:
        try:
            await db.rollback()
        finally:
            await finish_disk_step(partial(restore_root, slot))
        raise
    try:
        await db.commit()
    except IntegrityError:
        try:
            await db.rollback()
        finally:
            await finish_disk_step(partial(restore_root, slot))
        raise
    except (Exception, asyncio.CancelledError) as error:
        raise PluginImportCompletionUnknown("Plugin import acknowledgement unknown") from error
    if after_commit is not None:
        try:
            after_commit()
        except (Exception, asyncio.CancelledError) as error:
            raise PluginImportPostCommitFailure(
                "Plugin import committed; observer failed"
            ) from error
    try:
        await run_disk_step(partial(cleanup_previous, slot))
    except (Exception, asyncio.CancelledError) as error:
        logger.warning("plugin_import_root_cleanup_pending", error_type=type(error).__name__)
        return PluginRootCommitResult(committed=True, cleanup_pending=True)
    return PluginRootCommitResult(committed=True, cleanup_pending=False)
