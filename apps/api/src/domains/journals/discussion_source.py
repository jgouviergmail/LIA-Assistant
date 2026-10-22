"""Whole native portrait, dated and controlled independently of its old supports."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.core.read_budget import mark_read_opened
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.journals.management_read import JournalPage, read_journal_page
from src.domains.journals.models import JournalEntryStatus
from src.domains.journals.portrait_builder import _read_current_portrait, _render_block
from src.domains.journals.schemas import JournalEntryResponse
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    semantic_version,
    source_snapshot,
)
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


async def _journal_revision(db: AsyncSession, owner: UUID) -> int | None:
    await require_capability_fresh(db, PlatformCapability.JOURNALS)
    row = (
        await db.execute(
            select(User.journals_enabled, User.journal_revision)
            .where(User.id == owner, User.is_active.is_(True), User.deleted_at.is_(None))
            .with_for_update(read=True)
        )
    ).one_or_none()
    return row.journal_revision if row is not None and row.journals_enabled else None


def journal_evidence(row: JournalEntryResponse, request: SourceReadRequest) -> DiscussionEvidence:
    """Project a journal entry into derived evidence, versioned on all it states.

    Args:
        row: The entry.
        request: The read.

    Returns:
        The evidence.
    """
    frame = f"{row.title}\n{row.content}"
    return DiscussionEvidence(
        reference=f"journals:{row.id}",
        source=SourceKey.JOURNALS,
        object_id=str(row.id),
        version=semantic_version(
            (
                frame,
                row.theme.value,
                row.confidence.value,
                row.level.value,
                str(row.revision),
                str(row.evidence_count),
                str(row.contradiction_count),
                row.source.value,
            )
        ),
        observed_at=request.now,
        recorded_at=row.created_at,
        excerpt=frame[: request.item_max_chars],
        excerpt_truncated=len(frame) > request.item_max_chars,
        category=row.theme.value,
        assertion="inferred",
        derived=True,
        usage_nuance=f"Assistant interpretation; confidence={row.confidence.value}; level={row.level.value}; not a human statement or event date.",
    )


def _detail_id(reference: str | None) -> UUID | None:
    if reference is None:
        return None
    prefix, identifier = reference.split(":", 1)
    if prefix != SourceKey.JOURNALS.value:
        raise ValueError("journal reference source mismatch")
    return UUID(identifier)


def _journal_page_result(
    page: JournalPage, request: SourceReadRequest, revision: int
) -> SourceSnapshot:
    if request.request.operation == "detail" and not page.rows:
        raise ResourceNotFoundError("journal discussion evidence", request.request.reference)
    selected = page.rows[: request.item_limit]
    more = len(page.rows) > request.item_limit
    return source_snapshot(
        request,
        status="truncated" if more else ("ok" if selected else "empty"),
        items=tuple(journal_evidence(row, request) for row in selected),
        total=page.total,
        complete=not (more or request.cursor or request.request.query or request.request.reference),
        coverage_kind="active_facts",
        revision=str(revision),
        cursor=str(selected[-1].id) if more else None,
    )


class JournalDiscussionSource:
    """LIA's journal entries about the person, when the person keeps the journal on."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one page of journal entries, or one by reference.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when the journal is not consented or the person switched it off.

        Raises:
            ValueError: The request or its reference is for another source.
            ResourceNotFoundError: A detail read names nothing the person can see.
        """
        if request.request.source != SourceKey.JOURNALS:
            raise ValueError("journal source mismatch")
        if SourceKey.JOURNALS not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            revision = await _journal_revision(db, request.owner_id)
            if revision is None:
                return closed_source(request, disabled=True, reason="consent")
            history = request.request.operation == "history"
            after_id = UUID(request.cursor) if request.cursor else None
            entry_id = _detail_id(request.request.reference)
            mark_read_opened(request.owner_id)
            page = await read_journal_page(
                db,
                request.owner_id,
                theme=None,
                status=JournalEntryStatus.ACTIVE,
                limit=request.item_limit,
                after_id=after_id,
                query=request.request.query,
                entry_id=entry_id,
                recorded_start=request.window_start if history else None,
                recorded_end=request.window_end if history else None,
            )
        return _journal_page_result(page, request, revision)


class PortraitDiscussionSource:
    """LIA's compiled portrait of the person, used as one indivisible whole."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read the current brief portrait as one dated synthesis.

        Args:
            request: The bounded read.

        Returns:
            The portrait; stale when only an outdated one is stored, empty when none
            exists, closed when not consented, the journal is off, or it does not fit
            the excerpt bound whole.

        Raises:
            ValueError: The request is for another source.
        """
        if request.request.source != SourceKey.PORTRAIT:
            raise ValueError("portrait source mismatch")
        if SourceKey.PORTRAIT not in request.allowed_sources:
            return closed_source(request, disabled=True, reason="consent")
        async with get_db_context() as db:
            if await _journal_revision(db, request.owner_id) is None:
                return closed_source(request, disabled=True, reason="consent")
            mark_read_opened(request.owner_id)
            portrait = await _read_current_portrait(db, request.owner_id, "brief")
            if portrait is None:
                stored = await db.scalar(
                    select(
                        User.journal_portrait_brief.is_not(None)
                        | User.journal_portrait_full.is_not(None)
                    ).where(User.id == request.owner_id)
                )
                if stored:
                    return source_snapshot(
                        request, status="stale", reason="expired", coverage_kind="dated_synthesis"
                    )
        if portrait is None:
            return source_snapshot(
                request, status="empty", complete=True, total=0, coverage_kind="dated_synthesis"
            )
        text, compiled_at = portrait
        frame = _render_block(text, compiled_at)
        if len(frame) > request.item_max_chars:
            return closed_source(request, disabled=False, reason="budget")
        item = DiscussionEvidence(
            reference="portrait:current",
            source=SourceKey.PORTRAIT,
            object_id="compiled_portrait",
            version=semantic_version((frame,)),
            excerpt=frame,
            observed_at=request.now,
            recorded_at=compiled_at,
            assertion="inferred",
            derived=True,
        )
        return source_snapshot(
            request,
            status="ok",
            items=(item,),
            complete=True,
            total=1,
            coverage_kind="dated_synthesis",
        )
