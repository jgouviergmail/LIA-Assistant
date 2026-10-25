"""Meeting and projection rows share one commit; files are removed only after ACK."""

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.domains.meetings.deletion_confirmation import deletion_snapshot
from src.domains.meetings.models import MeetingStatus
from src.domains.meetings.repository import LIVE_STATUSES
from src.domains.rag_spaces.document_access import document_file_path
from src.domains.rag_spaces.document_deletion_cleanup import (
    cleanup_deleted_document_file,
)
from src.domains.rag_spaces.repository import RAGDocumentRepository
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.repository import UserRepository
from src.infrastructure.confirmed_commit import commit_confirmed_write
from src.infrastructure.file_transfer import LocalFileRead
from src.infrastructure.meeting_deletions import MeetingDeletionConfirmation
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_meetings import (
    meeting_imports_total,
    meetings_total,
)
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_documents_total_count,
)

if TYPE_CHECKING:
    from src.domains.meetings.models import Meeting
    from src.domains.meetings.service import MeetingService

logger = get_logger(__name__)


@dataclass(frozen=True)
class ProjectionRemoval:
    space_id: UUID
    document_id: UUID
    filename: str
    status: str
    file_digest: str | None


async def remove_projection_rows(
    service: MeetingService, meeting: Meeting
) -> ProjectionRemoval | None:
    if meeting.rag_document_id is None:
        return None
    document = await RAGDocumentRepository(service.db).get_by_id(meeting.rag_document_id)
    if document is None:
        return None
    if document.user_id != meeting.user_id or document.source_type != "meeting":
        from src.domains.meetings.service import raise_meeting_not_found

        raise_meeting_not_found(meeting.id)
    digest = None
    with suppress(FileNotFoundError):
        reader = LocalFileRead.open(document_file_path(document))
        try:
            digest = reader.identity_digest
        finally:
            await reader.close()
    selected = ProjectionRemoval(
        space_id=document.space_id,
        document_id=document.id,
        filename=document.filename,
        status=document.status,
        file_digest=digest,
    )
    await RAGSpaceService(service.db).delete_document(
        document.space_id, document.id, meeting.user_id, commit=False
    )
    return selected


async def delete_meeting(
    service: MeetingService,
    actor_id: UUID,
    meeting_id: UUID,
    *,
    confirmation: MeetingDeletionConfirmation | None = None,
) -> None:
    from src.domains.meetings.service import (
        raise_meeting_conflict,
        raise_meeting_not_found,
        worker_stale,
    )

    actor = await UserRepository(service.db).get_by_id_for_preference_update(actor_id)
    if actor is None:
        raise_meeting_not_found(meeting_id)
    meeting = await service._owned(meeting_id, actor_id, lock=True)
    if confirmation is not None:
        await confirmation.validate(await deletion_snapshot(service, meeting, lock_projection=True))
        await confirmation.check()
    if meeting.status is MeetingStatus.PROCESSING and not worker_stale(meeting):
        raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
    was_live = meeting.status in (*LIVE_STATUSES, MeetingStatus.UPLOADING)
    projection = await remove_projection_rows(service, meeting)
    if not await service.repo.delete_unless_leased(meeting_id):
        raise_meeting_conflict("meeting_in_progress", status=meeting.status.value)
    await commit_confirmed_write(
        service.db,
        confirmation,
        {
            "meeting_delete": {
                "meeting_id": str(meeting_id),
                "database_deleted": True,
                "files_cleanup_completed": False,
                "derived_minutes_deleted": False,
            }
        },
    )
    projection_cleaned = True
    if projection is not None:
        projection_cleaned = await cleanup_deleted_document_file(
            actor_id, projection.space_id, projection.filename, projection.file_digest
        )
        rag_documents_total_count.labels(status=projection.status).dec()
    audio_cleaned = await service.store.purge_meeting(actor_id, meeting_id)
    if confirmation is not None:
        confirmation.receipt.values = {
            "meeting_delete": {
                "meeting_id": str(meeting_id),
                "database_deleted": True,
                "files_cleanup_completed": bool(projection_cleaned and audio_cleaned),
                "derived_minutes_deleted": False,
            }
        }
    meetings_total.labels(status="discarded" if was_live else "deleted").inc()
    if meeting.status is MeetingStatus.UPLOADING:
        meeting_imports_total.labels(format=meeting.audio_format.value, outcome="cancelled").inc()
    logger.info("meeting_deleted", meeting_id=str(meeting_id), user_id=str(actor_id))
