"""The Drive changes feed, drained under bounds and routed onto linked trees.

ADR-261 P2 turns a Drive push notification into targeted reindexations; ADR-304
bounds it. Measured in production on 2026-09-22: one account's feed was
drained 25 changes at a time — the global item ceiling applied to an internal
pagination — with no page limit and no deadline, for 935 then 1 328 seconds,
while the wake sweep that serves every account sat behind it. ADR-297 had
bounded the folder WALK; the changes DRAIN was the other half.

``iter_change_pages`` reads pages of the size Google allows, stops at a page
count or a wall-clock deadline, refuses a feed that stops moving, and tells
the caller where it stopped (``ChangesPage.resume_token``): a ``nextPageToken``
when it was cut, the feed's new baseline when it was drained.

``ChangeRouter`` keeps what a drain routes onto the linked TREES — never the
whole feed — and carries the routing set across pages: a folder created under
a tree on one page routes the files created inside it on the next.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from src.core.config import settings
from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME


class DriveFeedError(Exception):
    """The changes feed answered something no drain can resume from."""


class ChangesFeedClient(Protocol):
    """What a drain needs of a Drive client."""

    async def list_changes(self, page_token: str, page_size: int = ...) -> dict[str, Any]:
        """One page of the changes feed."""
        ...


@dataclass(frozen=True, slots=True)
class DrainBounds:
    """How much of the feed one wake may read.

    Attributes:
        max_pages: Pages read at most.
        deadline_seconds: Wall-clock budget, read after each page.
    """

    max_pages: int
    deadline_seconds: float

    @classmethod
    def from_settings(cls) -> DrainBounds:
        """The published bounds (``RAG_DRIVE_PUSH_*``)."""
        return cls(
            max_pages=settings.rag_drive_push_max_pages,
            deadline_seconds=float(settings.rag_drive_push_drain_deadline_seconds),
        )


@dataclass(frozen=True, slots=True)
class ChangesPage:
    """One page of the feed and where the feed continues after it.

    Attributes:
        changes: The page's entries.
        resume_token: The token to read the feed from once this page is
            applied — ``nextPageToken``, or ``newStartPageToken`` when drained.
        drained: True when ``resume_token`` is the feed's new baseline.
    """

    changes: list[dict[str, Any]]
    resume_token: str
    drained: bool


def _resume_of(page: dict[str, Any]) -> tuple[str, bool]:
    """Where the feed continues after ``page``, and whether it is drained."""
    next_token = page.get("nextPageToken")
    if next_token:
        return str(next_token), False
    new_start = page.get("newStartPageToken")
    if new_start:
        return str(new_start), True
    raise DriveFeedError("a changes page carried neither nextPageToken nor newStartPageToken")


async def iter_change_pages(
    client: ChangesFeedClient,
    token: str,
    bounds: DrainBounds,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> AsyncIterator[ChangesPage]:
    """The feed's pages from ``token``, until drained or out of bounds.

    Args:
        client: A Drive client bound to the account.
        token: Where the feed is read from (the channel's stored token).
        bounds: Page count and deadline; the deadline is read after each page,
            so a page already read is always handed over.
        clock: Monotonic clock (injected by tests).

    Yields:
        Each page read; the last one says whether the feed was drained.

    Raises:
        DriveFeedError: A page carried no token, or the feed handed back the
            token it was given — a feed that no longer moves.
    """
    deadline = clock() + bounds.deadline_seconds
    for _ in range(bounds.max_pages):
        page = await client.list_changes(token, page_size=settings.rag_drive_changes_page_size)
        resume, drained = _resume_of(page)
        if not drained and resume == token:
            raise DriveFeedError("the changes feed did not move past its page token")
        yield ChangesPage(
            changes=list(page.get("changes", [])), resume_token=resume, drained=drained
        )
        if drained or clock() >= deadline:
            return
        token = resume


# ============================================================================
# Routing onto the linked trees
# ============================================================================


@dataclass(frozen=True, slots=True)
class SourceRoute:
    """What routing needs of a linked source, read in a session closed since.

    Attributes:
        id: The source.
        space_id: Its space.
        folder_id: The linked root.
        folder_ids: The walked tree the last synchronisation persisted.
    """

    id: UUID
    space_id: UUID
    folder_id: str
    folder_ids: tuple[str, ...]

    @classmethod
    def of(cls, source: Any) -> SourceRoute:
        """Snapshot a ``RAGDriveSource`` row."""
        return cls(
            id=source.id,
            space_id=source.space_id,
            folder_id=str(source.folder_id),
            folder_ids=tuple(source.folder_ids or ()),
        )


def routed_folder_ids(source: SourceRoute) -> list[str]:
    """The folders a change is routed on: the walked tree, the root alone before it."""
    walked = list(source.folder_ids)
    return walked if source.folder_id in walked else [source.folder_id, *walked]


@dataclass(slots=True)
class TouchedSource:
    """One linked tree a drain touched, and what it must apply."""

    source: SourceRoute
    changes: list[dict[str, Any]]
    #: The routing set after the feed: sub-folders created under the tree
    #: joined it, trashed ones left it. Persisted with the completion.
    folder_ids: list[str]


@dataclass(frozen=True, slots=True)
class _FeedChange:
    """One entry of the Drive changes feed, read once for every source."""

    file_id: str
    parents: frozenset[str]
    gone: bool
    is_folder: bool
    raw: dict[str, Any]


def _read_change(change: dict[str, Any]) -> _FeedChange:
    """The routing facts of a feed entry: id, parents, removal, kind."""
    file = change.get("file") or {}
    return _FeedChange(
        file_id=str(change.get("fileId") or file.get("id") or ""),
        parents=frozenset(file.get("parents") or []),
        gone=bool(change.get("removed") or file.get("trashed")),
        is_folder=file.get("mimeType") == GOOGLE_DRIVE_FOLDER_MIME,
        raw=change,
    )


def _route_folder_change(entry: TouchedSource, change: _FeedChange) -> None:
    """A folder joins the tree when created under it, leaves it when trashed."""
    known = entry.folder_ids
    if change.gone:
        if change.file_id in known and change.file_id != entry.source.folder_id:
            entry.folder_ids = [f for f in known if f != change.file_id]
        return
    if change.file_id not in known and change.parents & set(known):
        entry.folder_ids = [*known, change.file_id]


def _route_change(entry: TouchedSource, change: _FeedChange) -> None:
    """Route one feed entry on a source: a folder moves the set, a file is kept."""
    if change.is_folder or (change.gone and change.file_id in entry.folder_ids):
        _route_folder_change(entry, change)
    elif change.parents & set(entry.folder_ids):
        entry.changes.append(change.raw)


class ChangeRouter:
    """Routes the pages of one drain onto the linked trees, page after page.

    A change is routed on its file's parents against each source's walked
    folder set. The set grows as the feed is read — a folder created under the
    tree joins it so the files created inside it, later in the same drain,
    route too — and a trashed or removed sub-folder leaves it (its documents
    are pruned by the next full synchronisation: Drive reports the folder, not
    each descendant). Only the ROUTED entries are kept.
    """

    def __init__(self, sources: Sequence[SourceRoute]) -> None:
        """Start from each source's persisted routing set.

        Args:
            sources: The account's linked sources.
        """
        self._entries = [TouchedSource(s, [], routed_folder_ids(s)) for s in sources]
        self._initial = {s.id: routed_folder_ids(s) for s in sources}

    def route(self, changes: Sequence[dict[str, Any]]) -> None:
        """Route one page of the feed.

        Args:
            changes: The page's entries, in feed order.
        """
        for change in map(_read_change, changes):
            for entry in self._entries:
                _route_change(entry, change)

    def touched(self) -> list[TouchedSource]:
        """The sources with a file change to apply or a routing set that moved."""
        return [
            entry
            for entry in self._entries
            if entry.changes or entry.folder_ids != self._initial[entry.source.id]
        ]
