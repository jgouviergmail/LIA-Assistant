"""The minutes reach the « Réunions » knowledge space (ADR-258).

The space is found by ROLE (``rag_spaces.kind = 'meetings'``), never by name:
the user may rename it freely and it is created in their language the first
time minutes exist. Each meeting owns ONE RAG document, rewritten in place when
the minutes are edited (the durable reindex requeues it to ``PENDING`` and the
processing pipeline swaps the chunks atomically — nothing is deleted first).

This module never raises into the job: an indexing failure is recorded on the
meeting (``index_state = error``) and the minutes stay READY — the knowledge
space is a projection of the minutes, not their storage.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import MEETINGS_SPACE_KIND
from src.core.i18n_meetings import get_space_description, get_space_name
from src.domains.meetings.models import Meeting, MeetingIndexState
from src.domains.meetings.render import minutes_filename_stem, render_all
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.schemas import MeetingReport
from src.domains.rag_spaces.models import (
    RAGDocument,
    RAGDocumentSourceType,
    RAGDocumentStatus,
    RAGSpace,
)
from src.domains.rag_spaces.repository import RAGDocumentRepository, RAGSpaceRepository
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)

_MARKDOWN_MIME = "text/markdown"
#: Suffix tried when the localized default name is already taken by another space.
_NAME_RETRY_LIMIT = 5


async def ensure_meetings_space(db: AsyncSession, user_id: UUID, language: str) -> RAGSpace:
    """The user's meetings space, created on first use.

    Exempt from the per-user space cap on purpose: the space is a system-managed
    projection the user did not ask for as a quota item. A name clash with a
    space the user created by hand is resolved by suffixing, never by adopting
    the user's space.
    """
    repo = RAGSpaceRepository(db)
    existing = await repo.get_by_kind_for_user(user_id, MEETINGS_SPACE_KIND)
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
                    "kind": MEETINGS_SPACE_KIND,
                }
            )
            await db.commit()
        except IntegrityError:
            await db.rollback()
            # Lost a race with a concurrent job: the kind is unique per user.
            existing = await repo.get_by_kind_for_user(user_id, MEETINGS_SPACE_KIND)
            if existing is not None:
                return existing
            continue
        logger.info("meeting_space_created", user_id=str(user_id), space_id=str(space.id))
        return space
    raise RuntimeError("could not create the meetings knowledge space")


def _document_path(user_id: UUID, space_id: UUID, filename: str) -> Path:
    root = Path(settings.rag_spaces_storage_path).resolve()
    path = (root / str(user_id) / str(space_id) / filename).resolve()
    # The ids are typed UUIDs and the filename is ours (uuid hex + .md), so this
    # is defense in depth — and it covers the whole path, not only the directory.
    if not path.is_relative_to(root / str(user_id) / str(space_id)):
        raise RuntimeError("RAG storage path integrity violation")
    return path


async def _write_markdown(path: Path, markdown: str) -> int:
    def _write() -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = markdown.encode("utf-8")
        path.write_bytes(data)
        return len(data)

    return await asyncio.to_thread(_write)


async def _upsert_document(
    db: AsyncSession,
    *,
    meeting: Meeting,
    space: RAGSpace,
    markdown: str,
    original_filename: str,
) -> RAGDocument:
    """Create the meeting's RAG document or rewrite it and requeue it."""
    doc_repo = RAGDocumentRepository(db)
    document = (
        await doc_repo.get_by_id(meeting.rag_document_id) if meeting.rag_document_id else None
    )
    if document is not None and document.space_id != space.id:
        document = None  # the space was deleted and re-created: start over
    if document is None:
        stored_filename = f"{uuid4().hex}.md"
        size = await _write_markdown(
            _document_path(meeting.user_id, space.id, stored_filename), markdown
        )
        document = await doc_repo.create(
            {
                "space_id": space.id,
                "user_id": meeting.user_id,
                "filename": stored_filename,
                "original_filename": original_filename,
                "file_size": size,
                "content_type": _MARKDOWN_MIME,
                "status": RAGDocumentStatus.PENDING,
                "source_type": RAGDocumentSourceType.MEETING,
            }
        )
    else:
        size = await _write_markdown(
            _document_path(meeting.user_id, space.id, document.filename), markdown
        )
        document = await doc_repo.update(
            document,
            {
                "original_filename": original_filename,
                "file_size": size,
                "status": RAGDocumentStatus.PENDING,
                "error_message": None,
            },
        )
    await db.commit()
    return document


async def index_minutes(meeting_id: UUID) -> bool:
    """Write the CURRENT minutes into the knowledge space and embed them.

    Owns its session. Returns True when the document reached ``READY``; every
    failure is recorded on the meeting and returns False.
    """
    from src.domains.rag_spaces.processing import process_document
    from src.domains.users.repository import UserRepository

    async with get_db_context() as db:
        repo = MeetingRepository(db)
        meeting = await repo.get_by_id(meeting_id)
        if meeting is None or not meeting.report_current:
            return False
        if not settings.rag_spaces_enabled:
            await repo.set_index_state(
                meeting_id,
                state=MeetingIndexState.DISABLED,
                rag_document_id=meeting.rag_document_id,
                indexed_at=None,
            )
            return False
        user = await UserRepository(db).get_by_id(meeting.user_id)
        language = str(getattr(user, "language", None) or settings.default_language)
        try:
            report = MeetingReport.model_validate(meeting.report_current)
            space = await ensure_meetings_space(db, meeting.user_id, language)
            _header, markdown = render_all(meeting, report, language=language)
            document = await _upsert_document(
                db,
                meeting=meeting,
                space=space,
                markdown=markdown,
                original_filename=f"{minutes_filename_stem(meeting, report)}.md",
            )
            await repo.set_index_state(
                meeting_id,
                state=MeetingIndexState.PENDING,
                rag_document_id=document.id,
                indexed_at=None,
            )
        except (OSError, RuntimeError, IntegrityError, ValueError) as exc:
            logger.warning(
                "meeting_index_prepare_failed", meeting_id=str(meeting_id), error=str(exc)
            )
            await repo.set_index_state(
                meeting_id,
                state=MeetingIndexState.ERROR,
                rag_document_id=meeting.rag_document_id,
                indexed_at=None,
            )
            return False
        document_id, space_id, user_id = document.id, space.id, meeting.user_id
        filename, original_filename = document.filename, document.original_filename

    # process_document owns its own session and never raises.
    ready = await process_document(
        document_id=document_id,
        space_id=space_id,
        user_id=user_id,
        filename=filename,
        original_filename=original_filename,
        content_type=_MARKDOWN_MIME,
    )
    async with get_db_context() as db:
        await MeetingRepository(db).set_index_state(
            meeting_id,
            state=MeetingIndexState.INDEXED if ready else MeetingIndexState.ERROR,
            rag_document_id=document_id,
            indexed_at=datetime.now(UTC) if ready else None,
        )
    logger.info("meeting_indexed", meeting_id=str(meeting_id), ready=ready)
    return ready


def schedule_reindex(meeting_id: UUID) -> None:
    """Re-project edited minutes into the knowledge space, in the background."""
    safe_fire_and_forget(index_minutes(meeting_id), name=f"meeting_reindex_{meeting_id}")
