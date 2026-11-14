"""Durable file effects: claim before writing, publish after validation, retain failures."""

from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import ATTACHMENTS_FILE_SUFFIX_MAX_CHARS
from src.core.conversation_execution import ExecutionRevoked
from src.core.conversation_target import ConversationRef
from src.core.repository import BaseRepository
from src.core.worker_identity import WORKER_BOOT_ID
from src.domains.attachments.file_contracts import (
    FileRemovalClaim,
    FileWriteResult,
    FileWriteTicket,
    UploadMetadata,
)
from src.domains.attachments.models import Attachment, AttachmentStatus
from src.domains.users.conversation_authority import hold_conversation_source
from src.infrastructure.observability.metrics_attachments import (
    DELETION_REASON_EXPIRED,
    DELETION_REASON_FAILED_UPLOAD,
)


class AttachmentFileRepository(BaseRepository[Attachment]):
    """Every method stays in the caller's short transaction and performs no disk I/O."""

    def __init__(self, db: AsyncSession) -> None:
        """Compose on the transaction whose caller owns its commit."""
        super().__init__(db, Attachment)

    async def stage_upload(
        self, owner_id: UUID, metadata: UploadMetadata, target: ConversationRef | None
    ) -> FileWriteTicket:
        """Allocate a unique path and durable writer before that path can be touched."""
        await hold_conversation_source(self.db, owner_id, target)
        file_id, token = uuid4(), uuid4()
        # All supplied suffixes come from the MIME table or an owned source.
        # Refuse path characters even in a corrupt source filename.
        suffix = metadata.suffix
        if (
            not suffix.startswith(".")
            or len(suffix) > ATTACHMENTS_FILE_SUFFIX_MAX_CHARS
            or not suffix[1:].isascii()
            or not suffix[1:].isalnum()
        ):
            suffix = ".bin"
        stored_filename = f"{file_id}{suffix.lower()}"
        relative_path = f"{owner_id}/{stored_filename}"
        self.db.add(
            Attachment(
                id=file_id,
                user_id=owner_id,
                original_filename=metadata.filename,
                stored_filename=stored_filename,
                mime_type=metadata.mime_type,
                file_size=0,
                file_path=relative_path,
                content_type=metadata.content_type,
                origin=metadata.origin.value,
                title=metadata.title,
                conversation_id=metadata.conversation_id,
                status=AttachmentStatus.UPLOADED,
                expires_at=datetime.now(UTC) + timedelta(hours=settings.attachments_ttl_hours),
                io_worker_id=WORKER_BOOT_ID,
                io_owner_token=token,
                io_fence=0,
                io_claimed_at=datetime.now(UTC),
            )
        )
        await self.db.flush()
        return FileWriteTicket(file_id, owner_id, WORKER_BOOT_ID, token, relative_path)

    async def publish_upload(
        self,
        ticket: FileWriteTicket,
        result: FileWriteResult,
        target: ConversationRef | None,
    ) -> Attachment:
        """Publish only the joined writer's result, under fresh source/account locks."""
        await hold_conversation_source(self.db, ticket.owner_id, target)
        row = await self.db.scalar(
            select(Attachment)
            .where(
                Attachment.id == ticket.attachment_id,
                Attachment.user_id == ticket.owner_id,
                Attachment.io_worker_id == ticket.worker_id,
                Attachment.io_owner_token == ticket.owner_token,
                Attachment.status == AttachmentStatus.UPLOADED,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ExecutionRevoked()
        row.file_size = result.file_size
        row.extracted_text = result.extracted_text
        row.status = AttachmentStatus.READY
        row.io_worker_id = None
        row.io_owner_token = None
        row.io_claimed_at = None
        await self.db.flush()
        return row

    async def abandon_upload(self, ticket: FileWriteTicket) -> bool:
        """Retire a failed uploader only AFTER its actual disk work was joined."""
        changed = await self.db.scalar(
            update(Attachment)
            .where(
                Attachment.id == ticket.attachment_id,
                Attachment.user_id == ticket.owner_id,
                Attachment.status == AttachmentStatus.UPLOADED,
                Attachment.io_worker_id == ticket.worker_id,
                Attachment.io_owner_token == ticket.owner_token,
            )
            .values(
                status=AttachmentStatus.DELETING,
                deletion_reason=DELETION_REASON_FAILED_UPLOAD,
                io_worker_id=None,
                io_owner_token=None,
                io_claimed_at=None,
            )
            .returning(Attachment.id)
        )
        return changed is not None

    async def retire_expired(self, now: datetime) -> int:
        """Move expired READY files to durable cleanup; never assume an uploader stopped."""
        due = (
            select(Attachment.id)
            .where(Attachment.expires_at <= now, Attachment.status == AttachmentStatus.READY)
            .order_by(Attachment.expires_at, Attachment.id)
            .limit(settings.attachments_cleanup_batch_size)
            .with_for_update(skip_locked=True)
        )
        rows = await self.db.scalars(
            update(Attachment)
            .where(
                Attachment.id.in_(due),
                Attachment.expires_at <= now,
                Attachment.status == AttachmentStatus.READY,
            )
            .values(status=AttachmentStatus.DELETING, deletion_reason=DELETION_REASON_EXPIRED)
            .returning(Attachment.id)
        )
        return len(list(rows))

    async def retire_owned(
        self,
        owner_id: UUID,
        *,
        reason: str,
        ids: Collection[UUID] | None = None,
        origins: Collection[str] | None = None,
    ) -> list[UUID]:
        """Retire available files atomically; an active or unknown writer is never removed.

        The caller owns the commit and may add a confirmed file witness before it.
        This is an explicit user removal, not discussion last-use policy.
        """
        statement = update(Attachment).where(
            Attachment.user_id == owner_id,
            Attachment.status.in_((AttachmentStatus.READY, AttachmentStatus.EXPIRED)),
            Attachment.io_owner_token.is_(None),
        )
        if ids is not None:
            statement = statement.where(Attachment.id.in_(ids))
        if origins is not None:
            statement = statement.where(Attachment.origin.in_(origins))
        rows = await self.db.scalars(
            statement.values(
                status=AttachmentStatus.DELETING,
                deletion_reason=reason,
            ).returning(Attachment.id)
        )
        return list(rows)

    async def bind_removal_identity(
        self,
        owner_id: UUID,
        file_id: UUID,
        expected_digest: str | None,
    ) -> None:
        """Retain the exact approved identity in the same transaction as retirement."""
        changed = await self.db.scalar(
            update(Attachment)
            .where(
                Attachment.id == file_id,
                Attachment.user_id == owner_id,
                Attachment.status == AttachmentStatus.DELETING,
                Attachment.io_owner_token.is_(None),
            )
            .values(deletion_check_identity=True, deletion_expected_digest=expected_digest)
            .returning(Attachment.id)
        )
        if changed is None:
            raise ExecutionRevoked()

    async def retire_stopped_worker(self, worker_id: UUID) -> int:
        """Recover unknown uploads ONLY after an operator attests this worker has stopped.

        No caller may infer that condition from age, Redis, a lease or a missing PID.
        The recovery CLI owns the attestation; this method performs no disk work.
        """
        rows = await self.db.scalars(
            update(Attachment)
            .where(
                Attachment.status == AttachmentStatus.UPLOADED,
                Attachment.io_worker_id == worker_id,
                Attachment.io_owner_token.is_not(None),
            )
            .values(
                status=AttachmentStatus.DELETING,
                deletion_reason=DELETION_REASON_FAILED_UPLOAD,
                io_worker_id=None,
                io_owner_token=None,
                io_claimed_at=None,
            )
            .returning(Attachment.id)
        )
        return len(list(rows))

    async def claim_removal(
        self, *, before: datetime, excluded: set[UUID], attachment_id: UUID | None = None
    ) -> FileRemovalClaim | None:
        """Claim one retry-safe unlink; no lease or age can claim an UPLOADED writer.

        Args:
            before: A prior removal claim older than this may be retried.
            excluded: Files already tried by this bounded sweep, including failures.
            attachment_id: Optional exact file requested by an interactive cleanup.
        """
        query = (
            select(Attachment)
            .where(
                Attachment.status == AttachmentStatus.DELETING,
                or_(
                    Attachment.io_owner_token.is_(None),
                    and_(Attachment.io_owner_token.is_not(None), Attachment.io_claimed_at < before),
                ),
                Attachment.id.not_in(excluded),
            )
            .order_by(Attachment.updated_at, Attachment.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        if attachment_id is not None:
            query = query.where(Attachment.id == attachment_id)
        row = await self.db.scalar(query)
        if row is None:
            return None
        token = uuid4()
        row.io_worker_id = WORKER_BOOT_ID
        row.io_owner_token = token
        row.io_fence += 1
        row.io_claimed_at = datetime.now(UTC)
        assert row.deletion_reason is not None
        await self.db.flush()
        return FileRemovalClaim(
            row.id,
            row.user_id,
            WORKER_BOOT_ID,
            token,
            row.io_fence,
            row.file_path,
            row.deletion_reason,
            row.deletion_check_identity,
            row.deletion_expected_digest,
        )

    async def finish_removal(self, claim: FileRemovalClaim, *, removed: bool) -> bool:
        """Settle only this fenced claimant; failed unlink keeps the path for another try."""
        predicate = (
            Attachment.id == claim.attachment_id,
            Attachment.user_id == claim.owner_id,
            Attachment.status == AttachmentStatus.DELETING,
            Attachment.io_owner_token == claim.owner_token,
            Attachment.io_worker_id == claim.worker_id,
            Attachment.io_fence == claim.fence,
        )
        if removed:
            statement = delete(Attachment).where(*predicate).returning(Attachment.id)
            return await self.db.scalar(statement) is not None
        changed = await self.db.scalar(
            update(Attachment)
            .where(*predicate)
            .values(io_worker_id=None, io_owner_token=None, io_claimed_at=None)
            .returning(Attachment.id)
        )
        return changed is not None
