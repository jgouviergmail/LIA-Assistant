"""Bounded no-link witnesses for complete plugin/skill directories, never public contents."""

import hashlib
import json
import os
import stat
from pathlib import Path

from src.domains.plugins.removal_disk import _checked
from src.domains.skills.archive import _file_version, _open_resource


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def tree_state(root: Path, *, max_files: int, max_bytes: int) -> str:
    _checked(root, root.parent)
    if not root.exists():
        return _digest({"absent": True})
    before = root.stat(follow_symlinks=False)
    pending = [root]
    entries: dict[str, str] = {}
    remaining = max_bytes
    visited = 0
    file_count = 0
    while pending:
        directory = pending.pop()
        _checked(directory, root.parent)
        with os.scandir(directory) as children:
            for entry in children:
                visited += 1
                if visited > max_files * 4:
                    raise ValueError("Plugin directory witness exceeds entry budget")
                path = Path(entry.path)
                _checked(path, root.parent)
                key = path.relative_to(root).as_posix()
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    entries[key + "/"] = "directory"
                    continue
                file_count += 1
                if file_count > max_files:
                    raise ValueError("Plugin directory witness exceeds file budget")
                digest, spent = _file_state(path, remaining)
                entries[key] = digest
                remaining -= spent
    after = root.stat(follow_symlinks=False)
    if _file_version(before) != _file_version(after):
        raise ValueError("Plugin directory changed during observation")
    return _digest({"identity": [after.st_dev, after.st_ino], "entries": entries})


def _file_state(path: Path, remaining: int) -> tuple[str, int]:
    descriptor = _open_resource(path)
    digest = hashlib.sha256()
    spent = 0
    with os.fdopen(descriptor, "rb") as resource:
        before = os.fstat(resource.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > remaining:
            raise ValueError("Plugin directory witness exceeds byte budget")
        linked = path.stat(follow_symlinks=False)
        if (linked.st_dev, linked.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("Plugin file identity changed")
        while chunk := resource.read(min(65536, remaining - spent + 1)):
            spent += len(chunk)
            if spent > remaining:
                raise ValueError("Plugin directory witness exceeds byte budget")
            digest.update(chunk)
        if spent != before.st_size or _file_version(os.fstat(resource.fileno())) != _file_version(
            before
        ):
            raise ValueError("Plugin file changed during observation")
        linked = path.stat(follow_symlinks=False)
        if (linked.st_dev, linked.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("Plugin file replaced during observation")
    return (
        _digest({"identity": [before.st_dev, before.st_ino], "bytes": digest.hexdigest()}),
        spent,
    )
