"""One bounded skill archive for original UI and confirmed native transfers."""

import os
import stat
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from src.core.config import settings
from src.domains.skills.import_service import validate_skill_name


def _scope_directory(skill: dict[str, Any]) -> Path:
    name = skill["name"]
    validate_skill_name(name)
    if skill.get("scope") == "admin" and skill.get("owner_id") is None:
        allowed = Path(settings.skills_system_path)
    elif skill.get("scope") == "user" and isinstance(skill.get("owner_id"), str):
        owner = skill["owner_id"]
        if Path(owner).name != owner or owner in {".", ".."} or "/" in owner or "\\" in owner:
            raise ValueError("Invalid skill scope")
        allowed = Path(settings.skills_users_path) / owner
    else:
        raise ValueError("Invalid skill scope")
    return allowed


def _root(skill: dict[str, Any]) -> Path:
    allowed = _scope_directory(skill)
    source = Path(skill["source_path"])
    if source.name != "SKILL.md" or not source.resolve().is_relative_to(allowed.resolve()):
        raise ValueError("Skill path outside its scope")
    for ancestor in (source, *source.parents):
        if ancestor.is_symlink() or ancestor.is_junction():
            raise ValueError("Linked skill paths are not exportable")
        if ancestor == allowed:
            break
    return source.parent


def _open_resource(path: Path) -> int:
    """Open POSIX components without following links; validate Windows identity on return."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if os.open not in os.supports_dir_fd:
        return os.open(path, flags)
    absolute = path.absolute()
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(absolute.anchor, directory_flags)
    try:
        for part in absolute.parts[1:-1]:
            next_parent = os.open(part, directory_flags, dir_fd=parent)
            os.close(parent)
            parent = next_parent
        return os.open(absolute.name, flags, dir_fd=parent)
    finally:
        os.close(parent)


def _resources(root: Path) -> list[Path]:
    pending = [root]
    paths: list[Path] = []
    visited = 0
    while pending:
        current = pending.pop()
        with os.scandir(current) as children:
            for entry in children:
                visited += 1
                if visited > settings.skills_zip_max_files * 4:
                    raise ValueError("Skill archive has too many entries")
                path = Path(entry.path)
                if entry.is_symlink() or path.is_junction():
                    raise ValueError("Linked skill resources are not exportable")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    paths.append(path)
                    if len(paths) > settings.skills_zip_max_files:
                        raise ValueError("Skill archive has too many files")
                else:
                    raise ValueError("Skill archive contains a nonregular resource")
    if root / "SKILL.md" not in paths:
        raise ValueError("Skill manifest unavailable")
    return sorted(paths, key=lambda item: item.relative_to(root).as_posix())


def _file_version(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_resource(skill: dict[str, Any], path: Path, root: Path, remaining: int) -> bytes:
    _root(skill)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Skill resource changed scope")
    descriptor = _open_resource(path)
    with os.fdopen(descriptor, "rb") as resource:
        before = os.fstat(resource.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > remaining:
            raise ValueError("Skill archive exceeds its size limit")
        linked = path.stat(follow_symlinks=False)
        if (linked.st_dev, linked.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("Skill resource identity changed")
        _root(skill)
        data = resource.read(remaining + 1)
        after = os.fstat(resource.fileno())
        if _file_version(before) != _file_version(after) or len(data) != before.st_size:
            raise ValueError("Skill resource changed during export")
        linked = path.stat(follow_symlinks=False)
        if (linked.st_dev, linked.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("Skill resource identity changed")
        _root(skill)
    return data


def create_skill_archive(skill: dict[str, Any]) -> bytes:
    root = _root(skill)
    paths = _resources(root)
    budget = settings.skills_zip_max_decompressed_kb * 1024
    total = 0
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            data = _read_resource(skill, path, root, budget - total)
            total += len(data)
            if total > budget:
                raise ValueError("Skill archive exceeds its size limit")
            info = ZipInfo(
                (Path(skill["name"]) / path.relative_to(root)).as_posix(),
                date_time=(2000, 1, 1, 0, 0, 0),
            )
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()
