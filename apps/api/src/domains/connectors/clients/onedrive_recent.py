"""OneDrive's latest files, which no Graph call lists on a personal drive (ADR-369, lot 11).

Measured on a real drive of 30,960 items (2026-11-05): a search refuses an empty query, ignores
``$orderby`` and stops at 200 items; a folder's date does not follow what changes under it; the
retired ``recent`` answers one item; enumerating the drive takes a minute. A window built from any
of them found none of the ten latest files. The feed alone is exact, so it is what fills this one:
a first read starts from the top of the drive, its folders changed last opened first within a
budget, and every later read costs one call and adds what changed. The window is an approximation
on its first day, and exact for whatever changed since.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

import structlog

from src.core.constants import (
    GOOGLE_DRIVE_FOLDER_MIME,
    ONEDRIVE_RECENT_FEED_PAGES,
    ONEDRIVE_RECENT_SEED_REQUESTS,
    ONEDRIVE_RECENT_TTL_SECONDS,
    ONEDRIVE_RECENT_WINDOW_MAX,
    RAG_DRIVE_CHANGES_PAGE_SIZE_MAX,
    REDIS_KEY_ONEDRIVE_RECENT_PREFIX,
)
from src.domains.connectors.clients.onedrive_changes import ChangesFeedLostError
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

_ROOT: Final = "root"
#: The largest page the listing is asked for: a folder's newest come first.
_SEED_PAGE: Final = 100
_NEWEST_FIRST: Final = "folder,modifiedTime desc"


@dataclass(frozen=True, slots=True)
class _Window:
    """Where the feed stands, and the newest files seen so far."""

    token: str
    files: list[dict[str, Any]]


def _newest(files: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(files, key=lambda item: item.get("modifiedTime") or "", reverse=True)
    return ordered[:ONEDRIVE_RECENT_WINDOW_MAX]


def _is_folder(item: dict[str, Any]) -> bool:
    return item.get("mimeType") == GOOGLE_DRIVE_FOLDER_MIME


async def _from_the_top(drive: Any) -> list[dict[str, Any]]:
    """The files found opening the folders changed last first, within the budget."""
    folders: list[tuple[str, str]] = [("", _ROOT)]
    files: list[dict[str, Any]] = []
    for _ in range(ONEDRIVE_RECENT_SEED_REQUESTS):
        if not folders:
            break
        folders.sort(reverse=True)
        _, folder_id = folders.pop(0)
        page = await drive.list_files(
            folder_id=folder_id,
            max_results=_SEED_PAGE,
            content_type="all",
            order_by=_NEWEST_FIRST,
        )
        for item in page.get("files", []):
            if _is_folder(item):
                folders.append((str(item.get("modifiedTime") or ""), str(item["id"])))
            else:
                files.append(item)
    return _newest(files)


async def _started(drive: Any) -> _Window:
    """A new window. The feed is read first: what changes meanwhile stays in it."""
    token = await drive.get_changes_start_page_token()
    return _Window(token, await _from_the_top(drive))


async def _advanced(drive: Any, window: _Window) -> _Window:
    """The window with what changed; a burst is read a few pages at a time, and resumes."""
    token = window.token
    files = {str(item["id"]): item for item in window.files}
    for _ in range(ONEDRIVE_RECENT_FEED_PAGES):
        page = await drive.list_changes(token, page_size=RAG_DRIVE_CHANGES_PAGE_SIZE_MAX)
        for change in page.get("changes", []):
            file_id = str(change.get("fileId"))
            if change.get("removed"):
                files.pop(file_id, None)
            elif not _is_folder(change.get("file") or {}):
                files[file_id] = change["file"]
        following = page.get("nextPageToken")
        token = following or page.get("newStartPageToken") or token
        if not following:
            break
    return _Window(token, _newest(files.values()))


def _key(drive: Any) -> str:
    return f"{REDIS_KEY_ONEDRIVE_RECENT_PREFIX}{drive.user_id}"


async def _held(drive: Any) -> _Window | None:
    """The window kept for this account; our own bookkeeping never fails a read."""
    try:
        redis = await get_redis_cache()
        raw = await redis.get(_key(drive))
        if raw is None:
            return None
        kept = json.loads(raw)
        return _Window(str(kept["token"]), list(kept["files"]))
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.debug("onedrive_recent_unreadable", error_type=type(exc).__name__)
        return None


async def _keep(drive: Any, window: _Window) -> None:
    """Keep the window; a lost one only costs the next read a new start."""
    try:
        redis = await get_redis_cache()
        value = json.dumps({"token": window.token, "files": window.files})
        await redis.set(_key(drive), value, ex=ONEDRIVE_RECENT_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.debug("onedrive_recent_unkept", error_type=type(exc).__name__)


async def recent_window(drive: Any, limit: int) -> list[dict[str, Any]]:
    """The files changed last on a drive, as far as its feed has told.

    Args:
        drive: The account's open OneDrive client.
        limit: How many files to answer with.

    Returns:
        The files, newest first; never a folder.
    """
    held = await _held(drive)
    try:
        window = await (_started(drive) if held is None else _advanced(drive, held))
    except ChangesFeedLostError:
        window = await _started(drive)
    await _keep(drive, window)
    return window.files[:limit]


__all__ = ["recent_window"]
