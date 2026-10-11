"""Reversible plugin files move below a non-scanned account staging folder."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from src.core.config import settings
from src.domains.plugins.group_scope import PluginGroup
from src.domains.plugins.manifest import is_valid_plugin_name
from src.domains.skills.import_service import validate_skill_name


@dataclass(frozen=True)
class RemovalMove:
    source: Path
    destination: Path
    identity: tuple[int, int]


def _checked(path: Path, account: Path) -> Path:
    absolute = path.absolute()
    allowed = account.absolute()
    if absolute == allowed or not absolute.is_relative_to(allowed):
        raise ValueError("Plugin removal path outside account")
    for parent in (absolute, *absolute.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("Linked plugin removal path")
    if not absolute.resolve().is_relative_to(allowed.resolve()):
        raise ValueError("Plugin removal path changed scope")
    return absolute


def group_paths(group: PluginGroup, owner_id: UUID) -> tuple[Path, ...]:
    if not is_valid_plugin_name(group.plugin.name):
        raise ValueError("Invalid installed plugin name")
    paths = [(Path(settings.plugins_users_path), group.plugin.name)]
    for skill in group.skills:
        validate_skill_name(skill.name)
        paths.append((Path(settings.skills_users_path), skill.name))
    return tuple(
        _checked(base / str(owner_id) / name, base / str(owner_id)) for base, name in paths
    )


def prepare_moves(group: PluginGroup, owner_id: UUID) -> tuple[RemovalMove, ...]:
    return prepare_path_moves(group_paths(group, owner_id))


def prepare_path_moves(paths: tuple[Path, ...]) -> tuple[RemovalMove, ...]:
    """Share the checked, same-account reversible file boundary with updates."""
    token = uuid4().hex
    moves: list[RemovalMove] = []
    for source in paths:
        account = source.parent
        source = _checked(source, account)
        account = source.parent
        destination = _checked(account / ".lia-removal" / token / source.name, account)
        try:
            metadata = source.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        if not source.is_dir():
            raise ValueError("Plugin component is not a directory")
        moves.append(RemovalMove(source, destination, (metadata.st_dev, metadata.st_ino)))
    return tuple(moves)


def _account(move: RemovalMove) -> Path:
    return move.source.parent


def _identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino


def stage_moves(moves: tuple[RemovalMove, ...]) -> None:
    for move in moves:
        _checked(move.source, _account(move))
        _checked(move.destination, _account(move))
        if _identity(move.source) != move.identity or move.destination.exists():
            raise ValueError("Plugin component changed before removal")
        move.destination.parent.mkdir(parents=True, exist_ok=True)
        _checked(move.destination, _account(move))
        os.replace(move.source, move.destination)


def restore_moves(moves: tuple[RemovalMove, ...]) -> None:
    for move in reversed(moves):
        _checked(move.source, _account(move))
        _checked(move.destination, _account(move))
        if not move.destination.exists():
            continue
        if move.source.exists() or _identity(move.destination) != move.identity:
            raise ValueError("Plugin component cannot safely be restored")
        os.replace(move.destination, move.source)


def cleanup_quarantine(moves: tuple[RemovalMove, ...]) -> None:
    for move in moves:
        _checked(move.destination, _account(move))
        if _identity(move.destination) != move.identity:
            raise ValueError("Plugin removal staging changed")
        shutil.rmtree(move.destination)
