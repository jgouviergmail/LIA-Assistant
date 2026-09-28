"""Where a session's audio lives, and how it disappears — the radio keeps nothing.

Live only, no replay (owner decision, 2026-09-26): a segment exists to be heard once,
by the one listener whose session produced it. Each session writes its segments in
a directory of its own, named by the session's UUID; the directory goes when the
session ends, and a periodic sweep removes what a crash left behind (any session
directory that no live session claims and that nobody has touched for a while).

Every path is derived from identifiers — the session's UUID and the segment's place,
an integer — never from anything a request carries, so no path can be steered
outside the media root. Disk work runs off the event loop.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Collection
from pathlib import Path
from typing import Final
from uuid import UUID

#: The segment file's name inside its session's directory.
_SEGMENT_NAME: Final[str] = "{seq:04d}.mp3"


def session_dir(root: Path, session_id: UUID) -> Path:
    """The directory of one session's audio."""
    return root / str(session_id)


def segment_path(root: Path, session_id: UUID, seq: int) -> Path:
    """The mixed audio of one segment.

    Raises:
        ValueError: When ``seq`` is not a positive place.
    """
    if seq < 1:
        raise ValueError("a segment's place starts at 1")
    return session_dir(root, session_id) / _SEGMENT_NAME.format(seq=seq)


async def prepare(root: Path, session_id: UUID) -> Path:
    """Create the session's directory (and the root) before its first segment."""
    directory = session_dir(root, session_id)
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    return directory


async def discard(root: Path, session_id: UUID) -> None:
    """Remove everything a session produced (a directory already gone is the goal)."""
    await asyncio.to_thread(shutil.rmtree, session_dir(root, session_id), ignore_errors=True)


def _orphans(root: Path, live: Collection[UUID], older_than_s: float, now: float) -> list[Path]:
    if not root.is_dir():
        return []
    kept = {str(session_id) for session_id in live}
    orphans: list[Path] = []
    for entry in root.iterdir():
        if not entry.is_dir() or entry.name in kept:
            continue
        try:
            UUID(entry.name)
        except ValueError:
            continue  # not a session directory: never ours to remove
        try:
            touched = entry.stat().st_mtime
        except FileNotFoundError:
            continue  # its session ended while the sweep listed: already gone
        if now - touched > older_than_s:
            orphans.append(entry)
    return orphans


async def sweep_orphans(
    root: Path, *, live: Collection[UUID], older_than_s: float, now: float | None = None
) -> int:
    """Remove the session directories no live session claims and nobody touched lately.

    Args:
        root: The media root.
        live: The sessions still running (never swept, however old).
        older_than_s: How long a directory must have been left untouched.
        now: The wall clock in seconds (injected by tests).

    Returns:
        How many directories were removed.
    """
    moment = time.time() if now is None else now
    orphans = await asyncio.to_thread(_orphans, root, live, older_than_s, moment)
    for orphan in orphans:
        await asyncio.to_thread(shutil.rmtree, orphan, ignore_errors=True)
    return len(orphans)


__all__ = ["discard", "prepare", "segment_path", "session_dir", "sweep_orphans"]
