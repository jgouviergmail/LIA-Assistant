"""A kept answer reaches the « Kept answers » knowledge space (2026-09-16 design, part A).

The bookmark is the RECORD, its RAG document a PROJECTION — the shape the
meeting minutes took in ADR-258: a space found by ROLE (``rag_spaces.kind``),
created on first use in the person's language; a Markdown rendering written
under the space's storage tree; a PENDING document the durable pipeline
(``process_document``) claims, embeds, counts and prices. Everything below the
rendering is reused: storage-path safety, chunking, embedding with cost
attribution, the atomic chunk swap, the reaper's recovery, the generational
reindex.

Four rules that are not conventions:

- **A projection is CLAIMED before any effect** (``claim_for_projection``,
  one conditional UPDATE): a click schedules a projection and the sweep may
  select the same row, and two projections would leave an orphaned document.
- **Every gate leaves an honest, terminal state**: a capability off is
  ``disabled``, a refused spend is ``deferred`` (ADR-272, the non-raising
  sibling), a failure is ``error`` — never a silent return.
- **The document is the authority on its own lifecycle while it exists**
  (``projection.derived_index_state``): a crash between processing and the
  settle loses nothing, the reaper re-drives the document and the state reads
  from it.
- **This module never raises into a caller.** The state carries the failure;
  the logs carry counts and ids, never a line of the answer.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    BOOKMARKS_DOCUMENT_CONTENT_TYPE,
    BOOKMARKS_DOCUMENT_EXTENSION,
    BOOKMARKS_DOCUMENT_NAME_EXCERPT_CHARS,
    BOOKMARKS_SPACE_KIND,
)
from src.core.i18n_bookmarks import get_document_labels, get_space_description, get_space_name
from src.core.time_utils import format_datetime_for_display, resolve_user_timezone
from src.domains.agents.display.plain_text import looks_like_html
from src.domains.bookmarks.models import BookmarkIndexState, MessageBookmark
from src.domains.bookmarks.repository import BookmarkRepository
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.rag_spaces.document_access import document_file_path
from src.domains.rag_spaces.document_names import sanitize_document_name
from src.domains.rag_spaces.drive_ingest import create_pending_document
from src.domains.rag_spaces.models import RAGDocument, RAGDocumentSourceType, RAGSpace
from src.domains.rag_spaces.processing import html_to_markdown, process_document
from src.domains.rag_spaces.repository import (
    RAGChunkRepository,
    RAGDocumentRepository,
    RAGSpaceRepository,
)
from src.domains.usage_limits.enforcement import spend_blocked
from src.domains.users.repository import UserRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_rag_spaces import bookmark_index_total

logger = structlog.get_logger(__name__)

#: Suffix tried when the localized default name is already taken by a space
#: the person created by hand (the meetings precedent).
_NAME_RETRY_LIMIT = 5


# ============================================================================
# The space, found by role
# ============================================================================


async def ensure_bookmarks_space(db: AsyncSession, user_id: UUID, language: str) -> RAGSpace:
    """The person's « Kept answers » space, created on first use.

    Exempt from the per-user space cap on purpose: it is a managed projection
    the person did not ask for as a quota item. A name clash with a space the
    person created by hand is resolved by suffixing, never by adopting theirs.

    Args:
        db: Caller-owned session (committed here on creation).
        user_id: Owner.
        language: The person's language, for the default name.

    Returns:
        The space row.

    Raises:
        RuntimeError: When no name could be found in ``_NAME_RETRY_LIMIT`` tries.
    """
    repo = RAGSpaceRepository(db)
    existing = await repo.get_by_kind_for_user(user_id, BOOKMARKS_SPACE_KIND)
    if existing is not None:
        return existing
    base_name = get_space_name(language)
    description = get_space_description(language)
    for attempt in range(_NAME_RETRY_LIMIT):
        name = base_name if attempt == 0 else f"{base_name} ({attempt + 1})"
        try:
            space = await repo.create(
                {
                    "user_id": user_id,
                    "name": name,
                    "description": description,
                    "is_active": True,
                    "is_system": False,
                    "kind": BOOKMARKS_SPACE_KIND,
                }
            )
            await db.commit()
        except IntegrityError:
            await db.rollback()
            # Lost a race with a concurrent projection: the kind is unique per
            # user, so the winner's space is the one to use.
            existing = await repo.get_by_kind_for_user(user_id, BOOKMARKS_SPACE_KIND)
            if existing is not None:
                return existing
            continue
        logger.info("bookmark_space_created", user_id=str(user_id), space_id=str(space.id))
        return space
    raise RuntimeError("could not create the kept-answers knowledge space")


# ============================================================================
# Rendering (pure)
# ============================================================================


class KeptAnswer(Protocol):
    """What the renderer reads on a bookmark row (ADR-282's copied fields)."""

    content: str
    request_content: str | None
    answered_at: datetime


def _answer_as_markdown(content: str) -> str:
    """The answer's text: Markdown verbatim, an HTML document converted."""
    return html_to_markdown(content) if looks_like_html(content) else content


def render_bookmark(bookmark: KeptAnswer, *, language: str, timezone: str) -> str:
    """The Markdown document a kept answer becomes — pure.

    A dated title, the request quoted line by line (or the notification line
    when none produced the answer), the answer's date, then the answer itself.
    The date is the ANSWER's, in the person's zone: a bookmark is dated by its
    answer, not by the click (ADR-282).

    Args:
        bookmark: The row (``content``, ``request_content``, ``answered_at``).
        language: The person's language.
        timezone: The person's IANA zone.

    Returns:
        The document text.
    """
    labels = get_document_labels(language)
    day = format_datetime_for_display(
        bookmark.answered_at, timezone, language, include_time=False, include_day_name=False
    )
    stamp = format_datetime_for_display(
        bookmark.answered_at, timezone, language, include_time=True, include_day_name=False
    )
    lines = [f"# {labels['title'].format(date=day)}", ""]
    request = (bookmark.request_content or "").strip()
    if request:
        lines.append(f"**{labels['request']}**")
        lines.append("")
        lines.extend(f"> {line}" for line in request.splitlines())
    else:
        lines.append(f"_{labels['no_request']}_")
    lines.extend(["", f"**{labels['answered_on']}** {stamp}", "", "---", ""])
    lines.append(_answer_as_markdown(bookmark.content).strip())
    return "\n".join(lines) + "\n"


def document_name(bookmark: KeptAnswer, *, language: str, timezone: str) -> str:
    """The display name: the space's word, the local date, a bounded excerpt of the request.

    A person's request travels into headers, archives and the interface, so
    it goes through the sanitiser every display name shares (``document_names``).

    Args:
        bookmark: The row.
        language: The person's language.
        timezone: The person's IANA zone.

    Returns:
        A bounded, control-character-free ``.md`` name, never an identifier.
    """
    local_day = bookmark.answered_at.astimezone(ZoneInfo(timezone)).date().isoformat()
    base = f"{get_document_labels(language)['name']} {local_day}"
    excerpt = " ".join((bookmark.request_content or "").split())[
        :BOOKMARKS_DOCUMENT_NAME_EXCERPT_CHARS
    ].strip()
    if excerpt:
        base = f"{base} — {excerpt}"
    return sanitize_document_name(base, fallback=local_day, extension=BOOKMARKS_DOCUMENT_EXTENSION)


# ============================================================================
# Projection
# ============================================================================


async def _capabilities_allow() -> bool:
    """Both capabilities, read AT CALL TIME (ceiling AND operator switch, ADR-280)."""
    return await is_capability_enabled(PlatformCapability.RAG_SPACES) and (
        await is_capability_enabled(PlatformCapability.BOOKMARKS)
    )


async def _settle(
    bookmark_id: UUID,
    state: BookmarkIndexState,
    *,
    rag_document_id: UUID | None = None,
    indexed_at: datetime | None = None,
) -> None:
    """Write a state in its own session; a failure here is logged, never raised."""
    try:
        async with get_db_context() as db:
            await BookmarkRepository(db).set_index_state(
                bookmark_id,
                state=state.value,
                rag_document_id=rag_document_id,
                indexed_at=indexed_at,
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — the projection must not raise into its caller
        logger.exception("bookmark_index_settle_failed", bookmark_id=str(bookmark_id))


def _count(outcome: str) -> None:
    with suppress(Exception):  # metrics never break the projection
        bookmark_index_total.labels(outcome=outcome).inc()


async def _take_back_document(db: AsyncSession, document_id: UUID) -> None:
    """Delete a committed PENDING document no bookmark points at, row then file."""
    document = await RAGDocumentRepository(db).get_by_id(document_id)
    if document is None:
        return
    path = document_file_path(document)
    await RAGDocumentRepository(db).delete(document)
    await db.commit()
    await asyncio.to_thread(unlink_quietly, path)


async def _prepare(bookmark_id: UUID) -> dict[str, Any] | None:
    """Claim, gate, render and create the PENDING document; the ``process_document`` kwargs.

    Returns None when nothing is to be processed — the state already says why.
    """
    grace = settings.rag_job_reaper_grace_seconds
    async with get_db_context() as db:
        bookmarks = BookmarkRepository(db)
        if not await bookmarks.claim_for_projection(bookmark_id, grace_seconds=grace):
            _count("contended")
            logger.debug("bookmark_index_claim_contended", bookmark_id=str(bookmark_id))
            return None
        await db.commit()

    if not await _capabilities_allow():
        await _settle(bookmark_id, BookmarkIndexState.DISABLED)
        _count("disabled")
        return None

    async with get_db_context() as db:
        bookmark = await BookmarkRepository(db).get_by_id(bookmark_id)
        if bookmark is None:
            return None
        user_id = bookmark.user_id
        if await spend_blocked(user_id):
            await _settle(bookmark_id, BookmarkIndexState.DEFERRED)
            _count("deferred")
            logger.info("bookmark_index_skipped", bookmark_id=str(bookmark_id), reason="quota")
            return None
        user = await UserRepository(db).get_by_id(user_id)
        language = str(getattr(user, "language", None) or settings.default_language)
        zone = resolve_user_timezone(user).key
        # Rendered BEFORE the space is resolved: a name clash with a space the
        # person created by hand rolls the session back, and a rollback expires
        # every row it loaded — read afterwards, the bookmark would need a
        # refresh the sync renderer cannot await (measured on PostgreSQL:
        # ``MissingGreenlet``, the projection settling ``error``).
        content = render_bookmark(bookmark, language=language, timezone=zone).encode("utf-8")
        name = document_name(bookmark, language=language, timezone=zone)
        space = await ensure_bookmarks_space(db, user_id, language)
        kwargs = await create_pending_document(
            db,
            space_id=space.id,
            user_id=user_id,
            content=content,
            extension=BOOKMARKS_DOCUMENT_EXTENSION,
            original_name=name,
            content_type=BOOKMARKS_DOCUMENT_CONTENT_TYPE,
            source_fields={"source_type": RAGDocumentSourceType.BOOKMARK},
        )
        try:
            linked = await BookmarkRepository(db).set_index_state(
                bookmark_id,
                state=BookmarkIndexState.PENDING.value,
                rag_document_id=kwargs["document_id"],
            )
            await db.commit()
        except Exception:
            # The document row is already committed: a bookmark that does not
            # point at it would leave an orphan in the space, and the sweep
            # would project a second one. Take it back, then let the caller
            # settle ``error``.
            await db.rollback()
            await _take_back_document(db, kwargs["document_id"])
            raise
        if linked == 0:
            # The second click landed between the document's commit and the
            # link's: the bookmark is gone, and a document nobody points at
            # would be one the sweep cannot see and the person cannot delete.
            await _take_back_document(db, kwargs["document_id"])
            _count("vanished")
            logger.info("bookmark_index_vanished", bookmark_id=str(bookmark_id))
            return None
    return kwargs


async def index_bookmark(bookmark_id: UUID) -> bool:
    """Project one kept answer into the knowledge space and embed it.

    Owns its sessions. Never raises: every exit writes a state the API can
    show, and the return value says whether the document reached READY.

    Args:
        bookmark_id: The bookmark.

    Returns:
        True when the projection is indexed.
    """
    try:
        kwargs = await _prepare(bookmark_id)
    except Exception:  # noqa: BLE001 — the state carries the failure
        logger.exception("bookmark_index_prepare_failed", bookmark_id=str(bookmark_id))
        await _settle(bookmark_id, BookmarkIndexState.ERROR)
        _count("error")
        return False
    if kwargs is None:
        return False

    # process_document owns its own session and never raises.
    ready = await process_document(**kwargs)
    await _settle(
        bookmark_id,
        BookmarkIndexState.INDEXED if ready else BookmarkIndexState.ERROR,
        indexed_at=datetime.now(UTC) if ready else None,
    )
    _count("indexed" if ready else "error")
    logger.info(
        "bookmark_indexed",
        bookmark_id=str(bookmark_id),
        document_id=str(kwargs["document_id"]),
        ready=ready,
    )
    return ready


# ============================================================================
# Discarding
# ============================================================================


async def discard_index(db: AsyncSession, bookmark: MessageBookmark) -> Path | None:
    """Delete the projection's chunks and row INSIDE the caller's transaction.

    No commit here: the caller deletes the bookmark and commits once, then
    unlinks the returned file (best effort — a stale file is harmless and the
    storage tree goes with the account).

    Args:
        db: The caller's session.
        bookmark: The bookmark being removed.

    Returns:
        The stored file's path, or None when there was no projection.
    """
    if bookmark.rag_document_id is None:
        return None
    document: RAGDocument | None = await RAGDocumentRepository(db).get_by_id(
        bookmark.rag_document_id
    )
    if document is None:
        return None
    path = document_file_path(document)
    await RAGChunkRepository(db).delete_by_document(document.id)
    await RAGDocumentRepository(db).delete(document)
    return path


def unlink_quietly(path: Path | None) -> None:
    """Remove a stored file after the caller's commit; a missing file is not an event."""
    if path is None:
        return
    with suppress(OSError):
        path.unlink(missing_ok=True)


# ============================================================================
# Reconciliation — the backfill and the safety net
# ============================================================================


async def reconcile_bookmark_index(
    *, limit: int, concurrency: int, grace_seconds: int
) -> dict[str, int]:
    """Project every bookmark still without a projection, bounded per pass.

    Args:
        limit: Batch bound (the remainder drains at the next tick).
        concurrency: Concurrent projections.
        grace_seconds: How long a ``pending`` claim is trusted.

    Returns:
        ``selected``, ``indexed`` and ``not_indexed`` counts.
    """
    if not await _capabilities_allow():
        # Read once per pass: with the switch off, a pass would otherwise claim
        # and rewrite ``disabled`` on up to ``limit`` rows at every tick.
        logger.debug("bookmark_reconcile_skipped", reason="disabled")
        return {"selected": 0, "indexed": 0, "not_indexed": 0}
    async with get_db_context() as db:
        ids = await BookmarkRepository(db).unprojected_ids(limit=limit, grace_seconds=grace_seconds)
    if not ids:
        return {"selected": 0, "indexed": 0, "not_indexed": 0}
    if len(ids) >= limit:
        # The backlog exceeded one tick's bound — said, never silenced.
        logger.info("bookmark_reconcile_batch_capped", batch=len(ids))
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(bookmark_id: UUID) -> bool:
        async with semaphore:
            return await index_bookmark(bookmark_id)

    results = await asyncio.gather(*(bounded(bookmark_id) for bookmark_id in ids))
    indexed = sum(1 for result in results if result is True)
    counts = {"selected": len(ids), "indexed": indexed, "not_indexed": len(ids) - indexed}
    logger.info("bookmark_reconcile_complete", **counts)
    return counts


__all__ = [
    "discard_index",
    "document_name",
    "ensure_bookmarks_space",
    "index_bookmark",
    "reconcile_bookmark_index",
    "render_bookmark",
    "unlink_quietly",
]
