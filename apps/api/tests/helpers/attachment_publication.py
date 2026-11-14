"""A typed SQL stub for file-content units; publication/thread ownership stays real.

Real transaction, ownership and cancellation cases live in integration/attachments.
This stub replaces only the repository, never the disk worker or its publisher.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.conversation_target import ConversationRef
from src.domains.attachments.file_contracts import FileWriteResult, FileWriteTicket, UploadMetadata
from src.domains.attachments.models import Attachment, AttachmentStatus


class AttachmentWriterStub:
    """Capture the metadata the real file worker publishes, with a stage-failure seam."""

    def __init__(self, created: list[dict[str, object]], *, fail_stage: bool) -> None:
        self.created = created
        self.fail_stage = fail_stage
        self.rows: dict[UUID, Attachment] = {}

    async def stage_upload(
        self, owner_id: UUID, metadata: UploadMetadata, target: ConversationRef | None
    ) -> FileWriteTicket:
        if self.fail_stage:
            raise RuntimeError("Injected stage failure")
        identity, worker, token = uuid4(), uuid4(), uuid4()
        stored = f"{identity}{metadata.suffix}"
        path = f"{owner_id}/{stored}"
        self.rows[identity] = Attachment(
            id=identity,
            user_id=owner_id,
            original_filename=metadata.filename,
            stored_filename=stored,
            mime_type=metadata.mime_type,
            file_path=path,
            content_type=metadata.content_type,
            origin=metadata.origin.value,
            title=metadata.title,
            conversation_id=metadata.conversation_id,
            file_size=0,
            status=AttachmentStatus.UPLOADED,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.attachments_ttl_hours),
        )
        return FileWriteTicket(identity, owner_id, worker, token, path)

    async def publish_upload(
        self, ticket: FileWriteTicket, result: FileWriteResult, target: ConversationRef | None
    ) -> Attachment:
        row = self.rows[ticket.attachment_id]
        row.status = AttachmentStatus.READY
        row.file_size, row.extracted_text = result.file_size, result.extracted_text
        self.created.append(
            {
                "id": row.id,
                "user_id": row.user_id,
                "original_filename": row.original_filename,
                "stored_filename": row.stored_filename,
                "mime_type": row.mime_type,
                "file_path": row.file_path,
                "content_type": row.content_type,
                "origin": row.origin,
                "title": row.title,
                "conversation_id": row.conversation_id,
                "file_size": row.file_size,
                "extracted_text": row.extracted_text,
                "status": row.status,
                "expires_at": row.expires_at,
            }
        )
        return row

    async def abandon_upload(self, ticket: FileWriteTicket) -> bool:
        self.rows[ticket.attachment_id].status = AttachmentStatus.DELETING
        return True


class CapturingAttachmentRepository(AttachmentWriterStub):
    """Repository-shaped SQL seam shared by document and page file-content units."""

    snapshot: dict[str, object] = {}

    def __init__(self, db: AsyncSession) -> None:
        self.records: list[dict[str, object]] = []
        super().__init__(self.records, fail_stage=False)

    async def publish_upload(
        self, ticket: FileWriteTicket, result: FileWriteResult, target: ConversationRef | None
    ) -> Attachment:
        row = await super().publish_upload(ticket, result, target)
        type(self).snapshot = self.records[-1]
        return row


class PublicationSessionStub:
    """Only the SQL transaction boundary is substituted, never disk work."""

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


@asynccontextmanager
async def publication_session() -> AsyncIterator[PublicationSessionStub]:
    """Open the unit's SQL seam with the real publisher still running."""
    yield PublicationSessionStub()


@contextmanager
def stub_publication(
    storage: Path,
    created: list[dict[str, object]] | None = None,
    *,
    fail_stage: bool = False,
) -> Iterator[AttachmentWriterStub]:
    """Substitute SQL only; the real publisher allocates and joins a real disk task."""
    stub = AttachmentWriterStub(created if created is not None else [], fail_stage=fail_stage)
    with (
        patch(
            "src.domains.attachments.file_publication.AttachmentFileRepository", return_value=stub
        ),
        patch.object(settings, "attachments_storage_path", str(storage)),
    ):
        yield stub
