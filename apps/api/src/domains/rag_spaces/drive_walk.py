"""The Drive tree under a linked folder, walked once and bounded.

Google Drive lists ONE level per call (``'{id}' in parents``), so a source
that read its root folder alone never saw a sub-folder's files. The walk is a
breadth-first traversal over the folders, bounded by a file cap and a folder
cap, and it is the ONE reading the synchronisation and the preflight share:
the count a person is shown is computed by the code that indexes.

Three rules the tests pin:

- a shortcut (``application/vnd.google-apps.shortcut``) is neither listed nor
  followed — it may point outside the tree, or back into it;
- a folder reached twice is walked once (legacy multi-parent items, loops);
- a sub-folder the account cannot read is COUNTED and skipped, never fatal —
  the root being unreadable is the one error, because then there is no tree.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME, GOOGLE_DRIVE_SHORTCUT_MIME
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: Page size ``files.list`` accepts at most.
_PAGE_SIZE = 100


class DriveWalkError(RuntimeError):
    """The root folder itself could not be listed: there is no tree to walk."""


@dataclass
class DriveTree:
    """What the walk found under the root.

    Attributes:
        files: The non-folder, non-shortcut file resources, breadth-first.
        folder_ids: The root first, then every sub-folder reached, in walk
            order — the set the push path routes a change on.
        truncated: A bound stopped the walk; the lists above are a PREFIX of
            the tree, and a count derived from them is a floor, never a total.
        unreadable_folders: Sub-folders the account could not list.
    """

    files: list[dict[str, Any]] = field(default_factory=list)
    folder_ids: list[str] = field(default_factory=list)
    truncated: bool = False
    unreadable_folders: int = 0


async def _list_level(
    client: Any, folder_id: str, *, content_type: str, remaining: int | None
) -> tuple[list[dict[str, Any]], bool]:
    """Every child of one kind under one folder, paginated; capped at ``remaining``.

    Returns the items and whether the cap stopped the listing short of a
    further page (``more``) — a cap reached exactly is not a cut.
    """
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while remaining is None or len(items) < remaining:
        page_size = _PAGE_SIZE if remaining is None else min(_PAGE_SIZE, remaining - len(items))
        page = await client.list_files(
            folder_id=folder_id,
            max_results=page_size,
            page_token=page_token,
            content_type=content_type,
        )
        items.extend(page.get("files", []))
        page_token = page.get("nextPageToken")
        if not page_token:
            return items, False
    return items, bool(page_token)


def _keep_files(
    level_files: list[dict[str, Any]], files: list[dict[str, Any]], *, max_files: int
) -> bool:
    """Append a level's files (shortcuts skipped) up to the cap; True when the cap cut."""
    for item in level_files:
        if item.get("mimeType") == GOOGLE_DRIVE_SHORTCUT_MIME:
            continue
        if len(files) >= max_files:
            return True
        files.append(item)
    return False


def _child_folders(folders: list[dict[str, Any]]) -> list[str]:
    """The ids of the real folders of a level — a shortcut to a folder has another MIME."""
    return [
        str(folder["id"])
        for folder in folders
        if folder.get("mimeType") == GOOGLE_DRIVE_FOLDER_MIME and folder.get("id")
    ]


async def walk_drive_tree(
    client: Any, root_folder_id: str, *, max_files: int, max_folders: int
) -> DriveTree:
    """Walk the folders under ``root_folder_id`` breadth-first, bounded.

    Args:
        client: A Drive client bound to the account (``list_files``).
        root_folder_id: The linked folder.
        max_files: Files past which the walk stops (``truncated``).
        max_folders: Folders (root included) past which the walk stops.

    Returns:
        The tree, its bounds stated.

    Raises:
        DriveWalkError: When the root folder cannot be listed.
    """
    files: list[dict[str, Any]] = []
    folder_ids: list[str] = []
    truncated = False
    unreadable_folders = 0
    queue: deque[str] = deque([root_folder_id])
    seen: set[str] = {root_folder_id}

    while queue:
        if len(folder_ids) >= max_folders or len(files) >= max_files:
            truncated = True
            break
        folder_id = queue.popleft()
        folder_ids.append(folder_id)
        try:
            level_files, more_files = await _list_level(
                client, folder_id, content_type="files_only", remaining=max_files - len(files)
            )
            folders, _ = await _list_level(
                client, folder_id, content_type="folders_only", remaining=None
            )
        except Exception as exc:
            if folder_id == root_folder_id:
                raise DriveWalkError(f"Folder not accessible: {exc}") from exc
            unreadable_folders += 1
            logger.warning("rag_drive_walk_folder_unreadable", folder_id=folder_id, error=str(exc))
            continue
        cut = _keep_files(level_files, files, max_files=max_files)
        truncated = truncated or more_files or cut
        for child_id in _child_folders(folders):
            if child_id not in seen:
                seen.add(child_id)
                queue.append(child_id)

    if queue:
        truncated = True
    return DriveTree(
        files=files,
        folder_ids=folder_ids,
        truncated=truncated,
        unreadable_folders=unreadable_folders,
    )


__all__ = ["DriveTree", "DriveWalkError", "walk_drive_tree"]
